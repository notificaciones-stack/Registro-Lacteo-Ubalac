from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from apps.operations.models import UUIDTimeStampedModel


class FatigueSurvey(UUIDTimeStampedModel):
    external_id = models.UUIDField(unique=True)
    trip = models.ForeignKey('operations.RouteTrip', on_delete=models.PROTECT, related_name='fatigue_surveys')
    cycle = models.CharField(max_length=64, blank=True)  # reopening timestamp, not client clock
    sleep_hours = models.DecimalField('Horas de sueño en el último descanso', max_digits=4, decimal_places=1, validators=[MinValueValidator(0)])
    sleepy = models.BooleanField('¿Siente sueño, cansancio excesivo o dificultad para mantenerse alerta?')
    rested = models.BooleanField('¿El descanso previo fue suficiente para conducir de forma segura?')
    fatigue = models.BooleanField('¿Tiene alguna condición de fatiga que afecte su conducción?')
    observations = models.TextField('Observaciones', blank=True, max_length=2000)
    commitment = models.BooleanField('Confirmo que informaré cualquier fatiga y no continuaré conduciendo hasta su evaluación')

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['trip', 'cycle'], name='fatigue_trip_cycle_unique')]

    @property
    def has_risk(self):
        return self.sleep_hours < 6 or self.sleepy or not self.rested or self.fatigue


class FuelEntry(UUIDTimeStampedModel):
    external_id = models.UUIDField(unique=True)
    trip = models.ForeignKey('operations.RouteTrip', on_delete=models.PROTECT, related_name='fuel_entries')
    fueled_at = models.DateTimeField('Fecha y hora del tanqueo', default=timezone.now)
    gallons = models.DecimalField('Galones (galón estadounidense)', max_digits=9, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    total_price = models.DecimalField('Valor total (COP)', max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    odometer_km = models.PositiveIntegerField('Kilometraje del vehículo')
    full_tank = models.BooleanField('Tanque lleno', default=False)
    observations = models.TextField('Observaciones', blank=True, max_length=2000)
    fuel_photo = models.BinaryField()  # normalized JPEG; backed up together with database
    invoice_photo = models.BinaryField()

    class Meta:
        ordering = ['-fueled_at', '-created_at']
        constraints = [models.CheckConstraint(condition=models.Q(gallons__gt=0, total_price__gt=0), name='fuel_positive_amounts')]
