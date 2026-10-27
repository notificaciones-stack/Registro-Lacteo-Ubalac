from __future__ import annotations

import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.auditlog.models import AuditEvent
from apps.auditlog.services import record_event

from ..models import DocumentSequence, MilkReceipt, RouteTrip, default_product
from ..assignments import assigned_producers
from .trips import auto_close_expired_trips


def issue_document_number(*, key: str, prefix: str, at=None) -> str:
    at = at or timezone.now()
    sequence_key = f"{key}:{at.year}"
    try:
        # The inner savepoint keeps the outer transaction usable if two workers
        # try to create the first sequence for the year at the same time.
        with transaction.atomic():
            sequence, _ = DocumentSequence.objects.select_for_update().get_or_create(
                key=sequence_key,
                defaults={"prefix": prefix, "next_value": 1},
            )
    except IntegrityError:
        sequence = DocumentSequence.objects.select_for_update().get(key=sequence_key)
    current = sequence.next_value
    sequence.next_value = current + 1
    sequence.save(update_fields=["next_value", "updated_at"])
    return f"{sequence.prefix}-{at.year}-{current:06d}"


@transaction.atomic
def create_receipt(*, user, request=None, external_id=None, **validated_data) -> MilkReceipt:
    if external_id:
        existing = MilkReceipt.objects.filter(external_id=external_id).first()
        if existing:
            if existing.collected_by_id != user.pk:
                raise ValidationError("El identificador de sincronización ya está en uso.")
            return existing
    from .pricing import terms_at
    from .notifications import enqueue_notification
    from ..models import CollectionProduct
    producer = validated_data["producer"]
    product = validated_data.get("product") or CollectionProduct.objects.filter(pk=default_product()).first()
    if product is None:
        raise ValidationError("Seleccione un producto activo del catálogo.")
    validated_data["product"] = product
    if not product.active:
        raise ValidationError("El producto está inactivo.")
    if not producer.products.filter(pk=product.pk).exists() and not (product.code == "leche" and not producer.product_prices.exists()):
        raise ValidationError("El proveedor no tiene habilitado este producto.")
    price, adjustments = terms_at(producer, product, validated_data["collected_at"])
    validated_data["unit_price"], validated_data["adjustments"] = price, adjustments
    require_trip = not user.is_superuser and (user.role == "DRIVER" or (user.role == "COLLECTOR" and validated_data.get("source") == MilkReceipt.Source.MOBILE))
    profile = getattr(user, "driver_profile", None)
    if require_trip and profile and profile.products.exists() and not profile.products.filter(pk=product.pk).exists():
        raise ValidationError("El producto no está habilitado para este conductor.")
    if require_trip and not assigned_producers(user).filter(pk=validated_data["producer"].pk).exists():
        raise ValidationError("El productor no está asignado a este conductor.")
    if validated_data.get("source", MilkReceipt.Source.WEB) != MilkReceipt.Source.IMPORT:
        auto_close_expired_trips()
        collected_at = validated_data.get("collected_at")
        if require_trip and collected_at and collected_at > timezone.now() + timedelta(minutes=5):
            raise ValidationError("La fecha de captura no puede estar en el futuro.")
        trip = RouteTrip.objects.filter(driver=user, vehicle=validated_data.get("vehicle"), ended_at__isnull=True).first()
        if trip and require_trip and collected_at and collected_at < trip.started_at:
            trip = None
        if not trip and require_trip and collected_at:
            trip = RouteTrip.objects.filter(driver=user, vehicle=validated_data.get("vehicle"), started_at__lte=collected_at, ended_at__gte=collected_at).order_by("-started_at").first()
        if require_trip and not trip:
            raise ValidationError("Abra un recorrido con este vehículo o revise la hora capturada: no hay un recorrido que cubra la fecha de recolección.")
        if trip:
            if hasattr(trip, "weighbridge_record") and trip.weighbridge_record.status == "VALIDATED":
                raise ValidationError("Laboratorio ya validó la báscula de este recorrido. Solicite habilitar una corrección antes de sincronizar nuevos recibidos.")
            if validated_data.get("route") and validated_data["route"].pk != trip.route_id:
                raise ValidationError("La ruta del recibido debe coincidir con el recorrido abierto.")
            validated_data["trip"] = trip
            validated_data["route"] = trip.route
    if not validated_data.get("route") and validated_data.get("vehicle"):
        validated_data["route"] = validated_data["vehicle"].route
    receipt = MilkReceipt(
        external_id=external_id or uuid.uuid4(),
        internal_number=issue_document_number(key="receipt", prefix="REC"),
        collected_by=user,
        source=validated_data.pop("source", MilkReceipt.Source.WEB),
        sync_status=validated_data.pop("sync_status", MilkReceipt.SyncStatus.SYNCED),
        **validated_data,
    )
    receipt.full_clean()
    receipt.save()
    if receipt.trip_id and MilkReceipt.objects.filter(trip=receipt.trip, producer=receipt.producer, product=product, status="CONFIRMED").count() > 1:
        enqueue_notification(key=f"duplicate:{receipt.trip_id}:{receipt.producer_id}:{product.pk}", subject="UBALAC · Alerta de recibidos repetidos", body=f"Revise en la web los recibidos de {producer.name}, producto {product.name}, recorrido {receipt.trip_id}. Los registros permanecen en historial.")
    record_event(
        actor=user,
        action=AuditEvent.Action.CREATE,
        instance=receipt,
        changes={"internal_number": receipt.internal_number, "liters": str(receipt.liters)},
        request=request,
    )
    return receipt


@transaction.atomic
def void_receipt(*, receipt, user, reason: str, request=None) -> MilkReceipt:
    locked = MilkReceipt.objects.select_for_update().get(pk=receipt.pk)
    if locked.status == MilkReceipt.Status.VOIDED:
        return locked
    if not reason.strip():
        raise ValidationError("Debe indicar el motivo de anulación.")
    if locked.trip_id and hasattr(locked.trip, "weighbridge_record") and locked.trip.weighbridge_record.status == "VALIDATED":
        raise ValidationError("La báscula del recorrido ya está validada. Habilite primero una corrección desde el módulo de báscula.")
    locked.mark_void(user=user, reason=reason)
    locked.full_clean()
    locked.save(update_fields=["status", "voided_at", "voided_by", "void_reason", "updated_at"])
    record_event(
        actor=user,
        action=AuditEvent.Action.VOID,
        instance=locked,
        changes={"reason": reason.strip()},
        request=request,
    )
    return locked
