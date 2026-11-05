import base64
import binascii
import io
from decimal import Decimal
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from apps.operations.models import RouteTrip
from apps.operations.services.notifications import enqueue_notification
from apps.auditlog.services import record_event
from apps.auditlog.models import AuditEvent
from .models import FatigueSurvey, FuelEntry

STAFF = {'ADMIN', 'SUPERVISOR', 'ACCOUNTING', 'LABORATORY'}
WRITERS = {'ADMIN', 'SUPERVISOR', 'DRIVER', 'COLLECTOR'}


def visible_trips(user):
    qs = RouteTrip.objects.select_related('driver', 'vehicle', 'route')
    return qs if user.is_superuser or user.role in STAFF else qs.filter(driver=user)


def cycle_for(trip):
    return trip.reopened_at.isoformat() if trip.reopened_at else ''


def normalize_photo(value):
    try:
        if hasattr(value, 'read'):
            raw = value.read(4 * 1024 * 1024 + 1)
        else:
            if not isinstance(value, str) or len(value) > 5600000:
                raise ValueError()
            raw = base64.b64decode(value, validate=True)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ('JPEG', 'PNG', 'WEBP') or im.width * im.height > 24000000:
                raise ValueError()
            im.load()
            im = ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((1600, 1600))
            output = io.BytesIO()
            im.save(output, 'JPEG', quality=82)
            return output.getvalue()
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError('Adjunte una foto JPEG, PNG o WebP válida de máximo 4 MB y 24 megapíxeles.') from exc


@transaction.atomic
def save_record(model, data, user, request=None):
    data = dict(data)
    trip = visible_trips(user).select_for_update().get(pk=data['trip'].pk)
    if not (user.is_superuser or user.role in WRITERS):
        raise PermissionDenied()
    # Serialize retries on the trip: an interrupted upload must not duplicate expenses.
    existing = model.objects.filter(external_id=data['external_id']).first()
    if existing:
        if existing.trip_id != trip.pk:
            raise ValidationError('Identificador ya utilizado en otro recorrido.')
        return existing
    if model is FatigueSurvey:
        from django.utils.dateparse import parse_datetime
        expected = data.pop('expected_cycle', cycle_for(trip))
        if expected and expected != cycle_for(trip):
            stamp = parse_datetime(expected)
            if not stamp or timezone.is_naive(stamp) or not trip.reopened_at or not trip.started_at <= stamp <= trip.reopened_at:
                raise ValidationError('Revisión de recorrido inválida. Sincronice antes de continuar.')
        # Retain late offline surveys in their original cycle, never use them to close a reopened cycle.
        data['cycle'] = expected
        existing = model.objects.filter(trip=trip, cycle=data['cycle']).first()
        if existing:
            return existing
        if not data.get('commitment') or not 0 <= data['sleep_hours'] <= 24:
            raise ValidationError('Confirme el compromiso y registre entre 0 y 24 horas de descanso.')
    else:
        now = timezone.now()
        if data['fueled_at'] > now or data['fueled_at'] < trip.started_at or (trip.ended_at and data['fueled_at'] > trip.ended_at):
            raise ValidationError('El tanqueo debe pertenecer al intervalo del recorrido y no estar en el futuro.')
        previous = FuelEntry.objects.filter(trip__vehicle=trip.vehicle, fueled_at__lte=data['fueled_at']).defer('fuel_photo', 'invoice_photo').order_by('-fueled_at').first()
        following = FuelEntry.objects.filter(trip__vehicle=trip.vehicle, fueled_at__gt=data['fueled_at']).defer('fuel_photo', 'invoice_photo').order_by('fueled_at').first()
        if (previous and previous.odometer_km > data['odometer_km']) or (following and following.odometer_km < data['odometer_km']):
            raise ValidationError('El kilometraje no concuerda con los tanqueos del vehículo.')
        if trip.inspection_id and data['odometer_km'] < trip.inspection.odometer_km:
            raise ValidationError('El kilometraje es menor al registrado en la inspección inicial.')
        data['fuel_photo'] = normalize_photo(data['fuel_photo'])
        data['invoice_photo'] = normalize_photo(data['invoice_photo'])
    item = model(**data)
    item.full_clean()
    item.save()
    record_event(actor=user, action=AuditEvent.Action.CREATE, instance=item, request=request)
    if model is FatigueSurvey and item.has_risk:
        enqueue_notification(key=f'fatigue:{item.pk}', subject='UBALAC · Alerta de fatiga al cierre de turno', body=f'Conductor: {trip.driver}\nPlaca: {trip.vehicle}\nRuta: {trip.route}\nObservaciones: {item.observations}\nRevisar antes de autorizar nueva conducción.')
    return item


def efficiency(entry):
    """Full-to-full interval; include intermediate partial fills, regardless of report filters."""
    if not entry.full_tank:
        return None
    previous = FuelEntry.objects.filter(trip__vehicle=entry.trip.vehicle, full_tank=True, fueled_at__lt=entry.fueled_at).defer('fuel_photo', 'invoice_photo').order_by('-fueled_at').first()
    if not previous or entry.odometer_km <= previous.odometer_km:
        return None
    fills = FuelEntry.objects.filter(trip__vehicle=entry.trip.vehicle, fueled_at__gt=previous.fueled_at, fueled_at__lte=entry.fueled_at)
    gallons = sum(fills.values_list('gallons', flat=True), Decimal(0))
    return round(Decimal(entry.odometer_km - previous.odometer_km) / gallons, 2) if gallons else None
