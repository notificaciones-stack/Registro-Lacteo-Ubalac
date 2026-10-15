from decimal import Decimal
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.dashboard.reports import report_data
from apps.operations.models import Route, RouteTrip, WeighbridgeRecord
from apps.operations.services import create_receipt
from apps.operations.services.weighbridge import reopen_weighbridge, save_weighbridge_draft, validate_weighbridge
from .factories import make_producer, make_user, make_vehicle


class WeighbridgeTests(TestCase):
    def setUp(self):
        self.admin = make_user(username="admin-scale", role=User.Role.ADMIN)
        self.lab = make_user(username="lab-scale", role=User.Role.LABORATORY)
        self.driver = make_user(username="driver-scale", role=User.Role.DRIVER)
        self.route = Route.objects.create(name="Báscula norte")
        self.vehicle = make_vehicle()
        self.vehicle.driver = self.driver
        self.vehicle.route = self.route
        self.vehicle.save()
        self.producer = make_producer()
        now = timezone.now()
        self.trip = RouteTrip.objects.create(route=self.route, vehicle=self.vehicle, driver=self.driver, started_at=now - timedelta(minutes=30))
        self.receipt = create_receipt(user=self.driver, producer=self.producer, vehicle=self.vehicle, collected_at=now - timedelta(minutes=20), liters="950.00")
        self.trip.ended_at = now
        self.trip.save(update_fields=["ended_at", "updated_at"])

    def draft(self):
        return save_weighbridge_draft(
            trip=self.trip,
            values={"weighed_at": timezone.now(), "scale_ticket": "BAS-001", "gross_weight_kg": Decimal("1130.00"), "tare_weight_kg": Decimal("100.00"), "density_kg_l": Decimal("1.0300"), "tolerance_percent": Decimal("0.500"), "laboratory_notes": "Muestra conforme"},
            user=self.lab,
        )

    def test_laboratory_validates_and_reports_use_actual_liters(self):
        record = validate_weighbridge(record=self.draft(), user=self.lab)
        self.assertEqual(record.net_weight_kg, Decimal("1030.00"))
        self.assertEqual(record.actual_liters, Decimal("1000.00"))
        self.assertEqual(record.variance_liters, Decimal("50.00"))
        self.assertEqual(record.result, WeighbridgeRecord.Result.GAIN)
        self.assertEqual(record.revisions.count(), 1)
        data = report_data({"start": timezone.localdate(), "end": timezone.localdate()})
        self.assertEqual(data["total_liters"], Decimal("1000.00"))
        self.assertEqual(data["operational_liters"], Decimal("950"))
        self.assertEqual(data["producer_rank"][0]["liters"], Decimal("1000.00"))
        self.assertEqual(data["weighbridge_count"], 1)
        self.client.force_login(self.lab)
        page = self.client.get(reverse("operations:weighbridge_record", kwargs={"trip_id": self.trip.pk}))
        self.assertContains(page, "Litros reales")
        self.assertContains(page, "1000,00")

    def test_validated_record_is_locked_and_correction_preserves_revision(self):
        record = validate_weighbridge(record=self.draft(), user=self.lab)
        with self.assertRaises(PermissionDenied):
            reopen_weighbridge(record=record, user=self.lab, reason="Error del tiquete")
        reopen_weighbridge(record=record, user=self.admin, reason="Corrección de tara reportada")
        record.refresh_from_db()
        self.assertEqual(record.status, WeighbridgeRecord.Status.DRAFT)
        record.gross_weight_kg = Decimal("1078.50")
        record.save(update_fields=["gross_weight_kg", "updated_at"])
        validate_weighbridge(record=record, user=self.lab)
        record.refresh_from_db()
        self.assertEqual(record.actual_liters, Decimal("950.00"))
        self.assertEqual(record.revisions.count(), 2)
        self.assertEqual(record.revisions.get(revision_number=1).actual_liters, Decimal("1000.00"))
        self.assertEqual(record.revisions.get(revision_number=2).correction_reason, "Corrección de tara reportada")

    def test_permissions_and_open_trip_are_rejected(self):
        self.client.force_login(self.driver)
        self.assertEqual(self.client.get(reverse("operations:weighbridge_list")).status_code, 403)
        self.client.force_login(self.lab)
        self.assertEqual(self.client.get(reverse("operations:weighbridge_list")).status_code, 200)
        self.trip.ended_at = None
        self.trip.save(update_fields=["ended_at", "updated_at"])
        with self.assertRaises(ValidationError):
            self.draft()

    def test_duplicate_receipts_must_be_resolved_before_validation(self):
        create_receipt(user=self.driver, producer=self.producer, vehicle=self.vehicle, collected_at=self.trip.started_at + timedelta(minutes=5), liters="10.00")
        with self.assertRaisesMessage(ValidationError, "recibidos repetidos"):
            validate_weighbridge(record=self.draft(), user=self.lab)

    def test_new_receipt_cannot_change_a_validated_trip(self):
        validate_weighbridge(record=self.draft(), user=self.lab)
        with self.assertRaisesMessage(ValidationError, "ya validó"):
            create_receipt(user=self.driver, producer=self.producer, vehicle=self.vehicle, collected_at=self.trip.started_at + timedelta(minutes=1), liters="5.00")
