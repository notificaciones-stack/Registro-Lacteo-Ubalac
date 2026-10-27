from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class UUIDTimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Producer(UUIDTimeStampedModel):
    class FiscalCategory(models.TextChoices):
        SMALL = "SMALL", "Cuantías menores"
        SUPPORT = "SUPPORT", "Documento soporte"
        ELECTRONIC = "ELECTRONIC", "Facturación electrónica"

    class DocumentType(models.TextChoices):
        NIT = "NIT", "NIT"
        CC = "CC", "Cédula de ciudadanía"
        CE = "CE", "Cédula de extranjería"
        OTHER = "OTHER", "Otro"

    fiscal_category = models.CharField(max_length=12, choices=FiscalCategory.choices, default=FiscalCategory.SUPPORT)
    document_type = models.CharField(max_length=10, choices=DocumentType.choices, blank=True)
    document_number = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=180)
    farm_name = models.CharField(max_length=180, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    municipality = models.CharField(max_length=120, blank=True)
    village = models.CharField(max_length=120, blank=True)
    notes = models.TextField(max_length=1000, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    products = models.ManyToManyField("CollectionProduct", through="ProducerProduct", related_name="producers")
    deductions = models.ManyToManyField("FiscalParameter", blank=True, related_name="producers")
    assigned_driver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="primary_producers")
    assigned_route = models.ForeignKey("Route", null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_producers")
    assigned_vehicle = models.ForeignKey("Vehicle", null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_producers")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_type", "document_number"],
                name="unique_producer_document",
                condition=~Q(document_number=""),
            )
        ]

    def save(self, *args, **kwargs):
        self.document_number = "".join(self.document_number.split()).upper()
        self.name = " ".join(self.name.split())
        super().save(*args, **kwargs)

    def clean(self):
        self.document_type = (self.document_type or "").upper().strip()
        from .assignment_defaults import complete_producer_assignment
        complete_producer_assignment(self)
        self.document_number = "".join((self.document_number or "").split()).upper()
        if self.fiscal_category != self.FiscalCategory.SMALL:
            errors = {}
            if not self.document_type:
                errors["document_type"] = "El tipo de documento es obligatorio para esta clasificación."
            if not self.document_number.strip():
                errors["document_number"] = "El documento es obligatorio para esta clasificación."
            if errors:
                raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} ({self.document_number})"


class CollectionProduct(UUIDTimeStampedModel):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


def default_product():
    return uuid.UUID("52f00100-0000-4000-8000-000000000001")


class FiscalParameter(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        WITHHOLDING = "WITHHOLDING", "Retención / descuento"
        TAX = "TAX", "Impuesto / adición"

    name = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.WITHHOLDING)
    rate = models.DecimalField(max_digits=7, decimal_places=4, validators=[MinValueValidator(Decimal("0"))])
    description = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.CheckConstraint(condition=Q(rate__gte=0, rate__lte=100), name="fiscal_rate_range")]

    def __str__(self):
        return f"{self.name} ({self.rate} %)"


class ProducerProduct(UUIDTimeStampedModel):
    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name="product_prices")
    product = models.ForeignKey(CollectionProduct, on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["producer", "product"], name="unique_producer_product"), models.CheckConstraint(condition=Q(unit_price__isnull=True) | Q(unit_price__gte=0), name="producer_price_nonnegative")]


class PurchaseTerms(UUIDTimeStampedModel):
    """Effective-dated snapshots, including for delayed offline submissions."""
    producer = models.ForeignKey(Producer, on_delete=models.PROTECT, related_name="purchase_terms")
    product = models.ForeignKey(CollectionProduct, on_delete=models.PROTECT)
    effective_from = models.DateTimeField(default=timezone.now, db_index=True)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    adjustments = models.JSONField(default=list)

    class Meta:
        ordering = ["-effective_from", "-created_at"]


class Vehicle(UUIDTimeStampedModel):
    plate = models.CharField(max_length=12, unique=True)
    name = models.CharField(max_length=100, blank=True)
    route = models.ForeignKey("Route", on_delete=models.PROTECT, related_name="vehicles", null=True, blank=True)
    driver_name = models.CharField(max_length=180, blank=True)
    driver_document = models.CharField(max_length=30, blank=True)
    driver_phone = models.CharField(max_length=30, blank=True)
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="assigned_vehicles", null=True, blank=True)
    notes = models.TextField(max_length=1000, blank=True)
    capacity_liters = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        null=True,
        blank=True,
    )
    active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["plate"]

    def save(self, *args, **kwargs):
        self.plate = "".join(self.plate.split()).upper()
        if self.driver_id:
            profile = getattr(self.driver, "driver_profile", None)
            self.driver_name = self.driver.get_full_name() or self.driver.username
            self.driver_document = profile.document_number if profile else ""
            self.driver_phone = profile.phone if profile else ""
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"driver_name", "driver_document", "driver_phone"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.plate}{f' - {self.name}' if self.name else ''}"


class Route(UUIDTimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=300, blank=True)
    active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        self.name = " ".join(self.name.split()).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DriverProfile(UUIDTimeStampedModel):
    """Administrator-managed mobile assignments for a driver account."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="driver_profile")
    document_number = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    device_id = models.CharField(max_length=128, unique=True, null=True, blank=True, help_text="Identificador generado por la app e inscrito por el administrador.")
    encrypted_login_password = models.TextField(blank=True, editable=False)
    routes = models.ManyToManyField(Route, blank=True, related_name="driver_profiles")
    products = models.ManyToManyField(CollectionProduct, blank=True, related_name="driver_profiles")
    producers = models.ManyToManyField(Producer, blank=True, related_name="driver_profiles", help_text="Si no selecciona productores, el conductor verá todos los productores activos.")

    def clean(self):
        if self.user_id and self.user.role not in {"DRIVER", "COLLECTOR"}:
            raise ValidationError({"user": "Seleccione un usuario Conductor o Recolector."})

    def save(self, *args, **kwargs):
        self.device_id = (self.device_id or "").strip() or None
        self.document_number = "".join(self.document_number.split()).upper()
        self.phone = self.phone.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class DriverModuleSecurity(models.Model):
    """One administrator-provisioned password for the management module."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    password_hash = models.CharField(max_length=128, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Acceso al módulo de conductores"


class DocumentSequence(models.Model):
    key = models.CharField(max_length=40, unique=True)
    prefix = models.CharField(max_length=12)
    next_value = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.key}: {self.next_value}"


class RouteTrip(UUIDTimeStampedModel):
    """An actual driver shift; timestamps are set by the server."""

    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="trips")
    product = models.ForeignKey(CollectionProduct, on_delete=models.PROTECT, default=default_product)
    inspection = models.ForeignKey("VehicleInspection", on_delete=models.PROTECT, null=True, blank=True, related_name="trips")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="trips")
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="route_trips")
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.CharField(max_length=500, blank=True)
    reopened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reopened_route_trips")
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(fields=["driver"], condition=Q(ended_at__isnull=True), name="one_open_trip_per_driver"),
            models.UniqueConstraint(fields=["vehicle"], condition=Q(ended_at__isnull=True), name="one_open_trip_per_vehicle"),
            models.CheckConstraint(condition=Q(ended_at__isnull=True) | Q(ended_at__gte=models.F("started_at")), name="trip_end_after_start"),
        ]

    def __str__(self):
        return f"{self.route} · {self.driver} · {self.started_at:%Y-%m-%d %H:%M}"


class WeighbridgeRecord(UUIDTimeStampedModel):
    """Laboratory validation of the milk that physically arrived for a trip."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Pendiente de validar"
        VALIDATED = "VALIDATED", "Validado"

    class Result(models.TextChoices):
        LOSS = "LOSS", "Pérdida"
        BALANCED = "BALANCED", "Dentro de tolerancia"
        GAIN = "GAIN", "Ganancia"

    trip = models.OneToOneField(RouteTrip, on_delete=models.PROTECT, related_name="weighbridge_record")
    weighed_at = models.DateTimeField(default=timezone.now, db_index=True)
    scale_ticket = models.CharField(max_length=80, blank=True)
    gross_weight_kg = models.DecimalField(max_digits=14, decimal_places=2)
    tare_weight_kg = models.DecimalField(max_digits=14, decimal_places=2)
    density_kg_l = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("1.0300"))
    tolerance_percent = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0.500"))
    net_weight_kg = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    collected_liters = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    actual_liters = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    variance_liters = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    variance_percent = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    allocation_factor = models.DecimalField(max_digits=16, decimal_places=8, null=True, blank=True)
    result = models.CharField(max_length=12, choices=Result.choices, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    laboratory_notes = models.TextField(max_length=1000, blank=True)
    correction_reason = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_weighbridge_records")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_weighbridge_records")
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="validated_weighbridge_records", null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-weighed_at"]
        constraints = [
            models.CheckConstraint(condition=Q(gross_weight_kg__gt=models.F("tare_weight_kg")), name="weighbridge_gross_gt_tare"),
            models.CheckConstraint(condition=Q(tare_weight_kg__gte=0), name="weighbridge_tare_gte_zero"),
            models.CheckConstraint(condition=Q(density_kg_l__gte=Decimal("0.9000"), density_kg_l__lte=Decimal("1.2000")), name="weighbridge_density_range"),
            models.CheckConstraint(condition=Q(tolerance_percent__gte=0, tolerance_percent__lte=100), name="weighbridge_tolerance_range"),
        ]

    def clean(self):
        errors = {}
        if self.gross_weight_kg is not None and self.tare_weight_kg is not None and self.gross_weight_kg <= self.tare_weight_kg:
            errors["gross_weight_kg"] = "El peso bruto debe ser mayor que la tara."
        if self.tare_weight_kg is not None and self.tare_weight_kg < 0:
            errors["tare_weight_kg"] = "La tara no puede ser negativa."
        if self.density_kg_l is not None and not Decimal("0.9000") <= self.density_kg_l <= Decimal("1.2000"):
            errors["density_kg_l"] = "La densidad debe estar entre 0,9000 y 1,2000 kg/L."
        if self.tolerance_percent is not None and not Decimal("0") <= self.tolerance_percent <= Decimal("100"):
            errors["tolerance_percent"] = "La tolerancia debe estar entre 0 y 100 %."
        if self.weighed_at and self.weighed_at > timezone.now() + timedelta(minutes=5):
            errors["weighed_at"] = "La fecha del pesaje no puede estar en el futuro."
        if self.trip_id and self.weighed_at and self.weighed_at < self.trip.started_at:
            errors["weighed_at"] = "El pesaje no puede ser anterior al inicio del recorrido."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Báscula {self.trip} · {self.get_status_display()}"


class WeighbridgeRevision(models.Model):
    """Immutable snapshot for every laboratory validation."""

    record = models.ForeignKey(WeighbridgeRecord, on_delete=models.PROTECT, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    gross_weight_kg = models.DecimalField(max_digits=14, decimal_places=2)
    tare_weight_kg = models.DecimalField(max_digits=14, decimal_places=2)
    density_kg_l = models.DecimalField(max_digits=7, decimal_places=4)
    tolerance_percent = models.DecimalField(max_digits=6, decimal_places=3)
    net_weight_kg = models.DecimalField(max_digits=14, decimal_places=2)
    collected_liters = models.DecimalField(max_digits=14, decimal_places=2)
    actual_liters = models.DecimalField(max_digits=14, decimal_places=2)
    variance_liters = models.DecimalField(max_digits=14, decimal_places=2)
    variance_percent = models.DecimalField(max_digits=10, decimal_places=4)
    result = models.CharField(max_length=12, choices=WeighbridgeRecord.Result.choices)
    scale_ticket = models.CharField(max_length=80, blank=True)
    laboratory_notes = models.TextField(max_length=1000, blank=True)
    correction_reason = models.CharField(max_length=500, blank=True)
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="weighbridge_revisions")
    validated_at = models.DateTimeField()

    class Meta:
        ordering = ["-revision_number"]
        constraints = [models.UniqueConstraint(fields=["record", "revision_number"], name="unique_weighbridge_revision")]

    def __str__(self):
        return f"{self.record_id} · revisión {self.revision_number}"


class ProducerRequest(UUIDTimeStampedModel):
    class EmailStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        SENT = "SENT", "Correo enviado"
        FAILED = "FAILED", "Error de envío"

    external_id = models.UUIDField(unique=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="producer_requests")
    name = models.CharField(max_length=180)
    fiscal_category = models.CharField(max_length=12, choices=Producer.FiscalCategory.choices, default=Producer.FiscalCategory.SUPPORT)
    document_type = models.CharField(max_length=10, choices=Producer.DocumentType.choices, blank=True)
    requested_products = models.JSONField(default=list, blank=True)
    document_number = models.CharField(max_length=30, blank=True)
    farm_name = models.CharField(max_length=180, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    municipality = models.CharField(max_length=120, blank=True)
    village = models.CharField(max_length=120, blank=True)
    notes = models.TextField(max_length=1000, blank=True)
    email_status = models.CharField(max_length=10, choices=EmailStatus.choices, default=EmailStatus.PENDING)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} · {self.get_email_status_display()}"


class MilkReceipt(UUIDTimeStampedModel):
    class Source(models.TextChoices):
        WEB = "WEB", "Web"
        MOBILE = "MOBILE", "Aplicación móvil"
        IMPORT = "IMPORT", "Importación"

    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmado"
        VOIDED = "VOIDED", "Anulado"

    class SyncStatus(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        SYNCED = "SYNCED", "Sincronizado"
        ERROR = "ERROR", "Error"

    external_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    internal_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    producer = models.ForeignKey(Producer, on_delete=models.PROTECT, related_name="receipts")
    product = models.ForeignKey(CollectionProduct, on_delete=models.PROTECT, default=default_product)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    adjustments = models.JSONField(default=list, blank=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="receipts")
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="receipts", null=True, blank=True)
    trip = models.ForeignKey(RouteTrip, on_delete=models.PROTECT, related_name="receipts", null=True, blank=True)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="milk_receipts",
    )
    collected_at = models.DateTimeField(db_index=True)
    liters = models.DecimalField(max_digits=12, decimal_places=2)
    observations = models.TextField(blank=True, max_length=1000)
    collection_shift = models.CharField(max_length=10, blank=True)
    source_reference = models.CharField(max_length=80, unique=True, null=True, blank=True)
    support_type = models.CharField(max_length=80, blank=True)
    payment_method = models.CharField(max_length=80, blank=True)
    support_number = models.CharField(max_length=80, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.WEB)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    sync_status = models.CharField(
        max_length=12,
        choices=SyncStatus.choices,
        default=SyncStatus.SYNCED,
        db_index=True,
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="voided_receipts",
        null=True,
        blank=True,
    )
    void_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-collected_at", "-created_at"]
        indexes = [
            models.Index(fields=["collected_at", "status"], name="receipt_date_status_idx"),
            models.Index(fields=["producer", "collected_at"], name="receipt_producer_date_idx"),
            models.Index(fields=["vehicle", "collected_at"], name="receipt_vehicle_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(liters__gt=0), name="receipt_liters_gt_zero")
        ]

    def clean(self):
        errors = {}
        if self.liters is not None and self.liters <= 0:
            errors["liters"] = "La cantidad de litros debe ser mayor que cero."
        if self.status == self.Status.CONFIRMED:
            if self.producer_id and not self.producer.active:
                errors["producer"] = "El productor seleccionado está inactivo."
            if self.vehicle_id and not self.vehicle.active:
                errors["vehicle"] = "El vehículo seleccionado está inactivo."
        if self.trip_id:
            if self.vehicle_id != self.trip.vehicle_id:
                errors["vehicle"] = "El vehículo debe coincidir con el recorrido asociado."
            if self.route_id != self.trip.route_id:
                errors["route"] = "La ruta debe coincidir con el recorrido asociado."
        if errors:
            raise ValidationError(errors)

    def mark_void(self, *, user, reason: str):
        self.status = self.Status.VOIDED
        self.voided_at = timezone.now()
        self.voided_by = user
        self.void_reason = reason.strip()

    def __str__(self):
        return self.internal_number or str(self.external_id)


class VehicleInspection(UUIDTimeStampedModel):
    class Condition(models.TextChoices):
        OK = "OK", "Conforme"
        ISSUE = "ISSUE", "Con novedad"

    external_id = models.UUIDField(default=uuid.uuid4, unique=True)
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vehicle_inspections")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="inspections")
    inspected_on = models.DateField(default=timezone.localdate, db_index=True)
    odometer_km = models.PositiveIntegerField()
    brakes = models.CharField(max_length=5, choices=Condition.choices)
    tires = models.CharField(max_length=5, choices=Condition.choices)
    lights = models.CharField(max_length=5, choices=Condition.choices)
    fluids = models.CharField(max_length=5, choices=Condition.choices)
    tank_hygiene = models.CharField(max_length=5, choices=Condition.choices)
    documents = models.CharField(max_length=5, choices=Condition.choices)
    safety_kit = models.CharField(max_length=5, choices=Condition.choices)
    observations = models.TextField(max_length=2000, blank=True)
    safe_to_operate = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    @property
    def has_issues(self):
        return any(getattr(self, field) == "ISSUE" for field in ("brakes", "tires", "lights", "fluids", "tank_hygiene", "documents", "safety_kit"))

    def clean(self):
        if self.has_issues and not self.observations.strip():
            raise ValidationError({"observations": "Describa las novedades de la inspección."})
        if self.safe_to_operate and any(getattr(self, field) == "ISSUE" for field in ("brakes", "tires", "tank_hygiene", "documents")):
            raise ValidationError({"safe_to_operate": "Corrija las fallas críticas antes de autorizar el vehículo."})
        if self.inspected_on != timezone.localdate() and self._state.adding:
            raise ValidationError({"inspected_on": "La inspección debe corresponder al día actual."})

    def __str__(self):
        return f"{self.vehicle.plate} · {self.inspected_on} · {self.driver}"


class Notification(UUIDTimeStampedModel):
    """Durable email outbox. Failures never discard an operational record."""
    key = models.CharField(max_length=160, unique=True)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    recipients = models.JSONField(default=list)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
