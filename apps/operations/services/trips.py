from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from datetime import datetime, time

from apps.accounts.models import User
from apps.auditlog.models import AuditEvent
from apps.auditlog.services import record_event
from ..assignments import assigned_routes, driver_profile
from ..models import RouteTrip, VehicleInspection, CollectionProduct, default_product


OPERATORS = {User.Role.ADMIN, User.Role.SUPERVISOR}
DRIVERS = {User.Role.DRIVER, User.Role.COLLECTOR}


def trip_day_cutoff(trip):
    """23:59 local time on the day the trip started, stored as an aware datetime."""
    start_local = timezone.localtime(trip.started_at)
    return max(trip.started_at, timezone.make_aware(datetime.combine(start_local.date(), time(23, 59)), timezone.get_current_timezone()))


def auto_close_expired_trips(*, now=None):
    now = now or timezone.now()
    closed = 0
    for candidate in RouteTrip.objects.filter(ended_at__isnull=True).only("pk", "started_at").iterator():
        cutoff = trip_day_cutoff(candidate)
        if now < cutoff:
            continue
        with transaction.atomic():
            trip = RouteTrip.objects.select_for_update().get(pk=candidate.pk)
            if trip.ended_at or now < trip_day_cutoff(trip):
                continue
            trip.ended_at = trip_day_cutoff(trip)
            trip.save(update_fields=["ended_at", "updated_at"])
            record_event(actor=None, action=AuditEvent.Action.UPDATE, instance=trip, changes={"ended_at": trip.ended_at.isoformat(), "reason": "AUTO_2359"})
            closed += 1
    return closed


@transaction.atomic
def start_trip(*, user, route, vehicle, product=None, inspection=None, request=None):
    auto_close_expired_trips()
    if not (user.is_superuser or user.role in OPERATORS | DRIVERS):
        raise PermissionDenied("No puede abrir recorridos.")
    if not route.active or not vehicle.active:
        raise ValidationError("Ruta y vehículo deben estar activos.")
    if not (user.is_superuser or user.role in OPERATORS):
        if vehicle.driver_id != user.pk:
            raise PermissionDenied("El vehículo debe estar asignado a su usuario.")
        if not assigned_routes(user).filter(pk=route.pk).exists():
            raise PermissionDenied("La ruta no está asignada a este conductor.")
    product = product or CollectionProduct.objects.filter(pk=default_product()).first()
    if product is None:
        raise ValidationError("Seleccione un producto activo del catálogo.")
    if not product.active:
        raise ValidationError("El producto no está activo.")
    profile = driver_profile(user)
    if user.role in DRIVERS and not user.is_superuser:
        if profile and profile.products.exists() and not profile.products.filter(pk=product.pk).exists():
            raise PermissionDenied("Producto no asignado al conductor.")
        inspection = VehicleInspection.objects.filter(pk=inspection.pk, driver=user, vehicle=vehicle, inspected_on=timezone.localdate(), safe_to_operate=True).first() if inspection else None
        if not inspection:
            raise ValidationError("Complete y envíe la inspección vehicular del día antes de abrir el recorrido.")
        latest = VehicleInspection.objects.filter(driver=user, vehicle=vehicle, inspected_on=timezone.localdate()).first()
        if not latest or latest.pk != inspection.pk:
            raise ValidationError("Existe una inspección más reciente. Revise y envíe el estado actual del vehículo.")
        inspection.full_clean()
    if RouteTrip.objects.filter(ended_at__isnull=True).filter(driver=user).exists():
        raise ValidationError("Ya tiene un recorrido abierto.")
    if RouteTrip.objects.filter(ended_at__isnull=True).filter(vehicle=vehicle).exists():
        raise ValidationError("El vehículo ya tiene un recorrido abierto.")
    try:
        with transaction.atomic():
            trip = RouteTrip.objects.create(route=route, vehicle=vehicle, driver=user, product=product, inspection=inspection)
    except IntegrityError:
        raise ValidationError("Ya existe un recorrido abierto para este conductor o vehículo.") from None
    record_event(actor=user, action=AuditEvent.Action.CREATE, instance=trip, changes={"route": route.name, "vehicle": vehicle.plate, "started_at": trip.started_at.isoformat()}, request=request)
    return trip


@transaction.atomic
def close_trip(*, trip, user, request=None):
    auto_close_expired_trips()
    locked = RouteTrip.objects.select_for_update().get(pk=trip.pk)
    if not (user.is_superuser or user.role in OPERATORS or locked.driver_id == user.pk):
        raise PermissionDenied("Solo el conductor o un supervisor pueden cerrar este recorrido.")
    if locked.ended_at:
        raise ValidationError("El recorrido ya está cerrado.")
    locked.ended_at = timezone.now()
    locked.save(update_fields=["ended_at", "updated_at"])
    record_event(actor=user, action=AuditEvent.Action.UPDATE, instance=locked, changes={"ended_at": locked.ended_at.isoformat()}, request=request)
    return locked


@transaction.atomic
def reopen_trip(*, trip, user, reason: str, request=None):
    if not (user.is_superuser or user.role in OPERATORS):
        raise PermissionDenied("Solo un administrador o supervisor puede reabrir el recorrido.")
    if len(reason.strip()) < 8:
        raise ValidationError("Indique un motivo de al menos ocho caracteres.")
    locked = RouteTrip.objects.select_for_update().get(pk=trip.pk)
    if hasattr(locked, "weighbridge_record") and locked.weighbridge_record.status == "VALIDATED":
        raise ValidationError("Primero habilite una corrección del registro de báscula validado.")
    if locked.ended_at is None:
        raise ValidationError("El recorrido ya está abierto.")
    if timezone.localdate(locked.started_at) != timezone.localdate() or timezone.now() >= trip_day_cutoff(locked):
        raise ValidationError("Solo se puede reabrir un recorrido del día actual antes de las 23:59.")
    if RouteTrip.objects.filter(ended_at__isnull=True).exclude(pk=locked.pk).filter(
        models.Q(driver=locked.driver) | models.Q(vehicle=locked.vehicle)
    ).exists():
        raise ValidationError("El conductor o vehículo ya tiene otro recorrido abierto.")
    locked.ended_at = None
    locked.reopened_at = timezone.now()
    locked.reopened_by = user
    locked.reopen_reason = reason.strip()
    locked.save(update_fields=["ended_at", "reopened_at", "reopened_by", "reopen_reason", "updated_at"])
    record_event(actor=user, action=AuditEvent.Action.UPDATE, instance=locked, changes={"reason": "REOPEN", "reopen_reason": locked.reopen_reason}, request=request)
    return locked
