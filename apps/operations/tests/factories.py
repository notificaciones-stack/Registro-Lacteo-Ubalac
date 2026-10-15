from django.utils import timezone

from apps.accounts.models import User
from apps.operations.models import Producer, Vehicle


def make_inspection(driver, vehicle):
    from apps.operations.models import VehicleInspection
    return VehicleInspection.objects.create(driver=driver, vehicle=vehicle, odometer_km=1000, safe_to_operate=True, **{key: "OK" for key in ("brakes", "tires", "lights", "fluids", "tank_hygiene", "documents", "safety_kit")})


def make_user(*, username="admin", role=User.Role.ADMIN, is_superuser=False):
    return User.objects.create_user(
        username=username,
        password="A-secure-test-password-2026!",
        role=role,
        is_staff=is_superuser,
        is_superuser=is_superuser,
    )


def make_producer():
    return Producer.objects.create(
        document_type=Producer.DocumentType.NIT,
        document_number="900123456-7",
        name="Finca El Roble",
        farm_name="El Roble",
        municipality="Sogamoso",
    )


def make_vehicle():
    return Vehicle.objects.create(plate="ABC123", name="Camión 1", capacity_liters="5000.00")


def receipt_data(*, producer, vehicle):
    return {
        "producer": producer,
        "vehicle": vehicle,
        "collected_at": timezone.now(),
        "liters": "123.45",
        "observations": "Recibido de prueba",
    }
