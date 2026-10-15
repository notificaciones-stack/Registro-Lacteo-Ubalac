from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.auditlog.models import AuditEvent
from apps.auditlog.services import record_event
from ..models import MilkReceipt, WeighbridgeRecord, WeighbridgeRevision


LAB_ROLES = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.LABORATORY}
MASTER_ROLES = {User.Role.ADMIN, User.Role.SUPERVISOR}
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")
Q8 = Decimal("0.00000001")


def _allowed(user, roles):
    return user.is_superuser or user.role in roles


@transaction.atomic
def save_weighbridge_draft(*, trip, values, user, request=None):
    if not _allowed(user, LAB_ROLES):
        raise PermissionDenied("No tiene permiso para registrar la báscula.")
    trip = type(trip).objects.select_for_update().get(pk=trip.pk)
    if trip.ended_at is None:
        raise ValidationError("El recorrido debe estar cerrado antes de registrar la báscula.")
    record = WeighbridgeRecord.objects.select_for_update().filter(trip=trip).first()
    if record and record.status == WeighbridgeRecord.Status.VALIDATED:
        raise ValidationError("El registro está validado. Administración debe habilitar una corrección.")
    created = record is None
    record = record or WeighbridgeRecord(trip=trip, created_by=user, updated_by=user)
    for field, value in values.items():
        setattr(record, field, value)
    record.updated_by = user
    record.full_clean()
    record.save()
    record_event(actor=user, action=AuditEvent.Action.CREATE if created else AuditEvent.Action.UPDATE, instance=record, changes={"status": record.status, "gross_weight_kg": str(record.gross_weight_kg), "tare_weight_kg": str(record.tare_weight_kg)}, request=request)
    return record


@transaction.atomic
def validate_weighbridge(*, record, user, request=None):
    if not _allowed(user, LAB_ROLES):
        raise PermissionDenied("No tiene permiso para validar la báscula.")
    locked = WeighbridgeRecord.objects.select_for_update().select_related("trip").get(pk=record.pk)
    if locked.status == WeighbridgeRecord.Status.VALIDATED:
        raise ValidationError("Este registro ya fue validado.")
    if locked.trip.ended_at is None:
        raise ValidationError("El recorrido debe estar cerrado.")
    receipts = MilkReceipt.objects.select_for_update().filter(trip=locked.trip, status=MilkReceipt.Status.CONFIRMED)
    duplicates = receipts.values("producer_id").annotate(total=Count("id")).filter(total__gt=1)
    if duplicates.exists():
        raise ValidationError("Primero revise las alertas de recibidos repetidos de este recorrido.")
    collected = receipts.aggregate(total=Sum("liters"))["total"] or Decimal("0")
    if collected <= 0:
        raise ValidationError("El recorrido no tiene litros confirmados para comparar.")
    net = (locked.gross_weight_kg - locked.tare_weight_kg).quantize(Q2, rounding=ROUND_HALF_UP)
    actual = (net / locked.density_kg_l).quantize(Q2, rounding=ROUND_HALF_UP)
    variance = (actual - collected).quantize(Q2, rounding=ROUND_HALF_UP)
    variance_percent = ((variance / collected) * Decimal("100")).quantize(Q4, rounding=ROUND_HALF_UP)
    threshold = collected * locked.tolerance_percent / Decimal("100")
    result = WeighbridgeRecord.Result.LOSS if variance < -threshold else WeighbridgeRecord.Result.GAIN if variance > threshold else WeighbridgeRecord.Result.BALANCED
    now = timezone.now()
    locked.net_weight_kg = net
    locked.collected_liters = collected
    locked.actual_liters = actual
    locked.variance_liters = variance
    locked.variance_percent = variance_percent
    locked.allocation_factor = (actual / collected).quantize(Q8, rounding=ROUND_HALF_UP)
    locked.result = result
    locked.status = WeighbridgeRecord.Status.VALIDATED
    locked.validated_by = user
    locked.validated_at = now
    locked.updated_by = user
    locked.full_clean()
    locked.save()
    revision_number = (locked.revisions.select_for_update().aggregate(last=Max("revision_number"))["last"] or 0) + 1
    WeighbridgeRevision.objects.create(
        record=locked, revision_number=revision_number, gross_weight_kg=locked.gross_weight_kg,
        tare_weight_kg=locked.tare_weight_kg, density_kg_l=locked.density_kg_l,
        tolerance_percent=locked.tolerance_percent, net_weight_kg=net, collected_liters=collected,
        actual_liters=actual, variance_liters=variance, variance_percent=variance_percent,
        result=result, scale_ticket=locked.scale_ticket, laboratory_notes=locked.laboratory_notes,
        correction_reason=locked.correction_reason, validated_by=user, validated_at=now,
    )
    record_event(actor=user, action=AuditEvent.Action.UPDATE, instance=locked, changes={"status": locked.status, "actual_liters": str(actual), "variance_liters": str(variance), "result": result, "revision": revision_number}, request=request)
    locked.correction_reason = ""
    locked.save(update_fields=["correction_reason", "updated_at"])
    return locked


@transaction.atomic
def reopen_weighbridge(*, record, user, reason, request=None):
    if not _allowed(user, MASTER_ROLES):
        raise PermissionDenied("Solo administración o supervisión puede habilitar una corrección.")
    if len(reason.strip()) < 8:
        raise ValidationError("Indique un motivo de al menos ocho caracteres.")
    locked = WeighbridgeRecord.objects.select_for_update().get(pk=record.pk)
    if locked.status != WeighbridgeRecord.Status.VALIDATED:
        raise ValidationError("El registro ya está habilitado para edición.")
    locked.status = WeighbridgeRecord.Status.DRAFT
    locked.correction_reason = reason.strip()
    locked.updated_by = user
    locked.save(update_fields=["status", "correction_reason", "updated_by", "updated_at"])
    record_event(actor=user, action=AuditEvent.Action.UPDATE, instance=locked, changes={"status": locked.status, "correction_reason": locked.correction_reason}, request=request)
    return locked
