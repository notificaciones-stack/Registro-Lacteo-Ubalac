import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.auditlog.models import AuditEvent
from apps.operations.models import MilkReceipt
from apps.operations.services import create_receipt, void_receipt

from .factories import make_producer, make_user, make_vehicle, receipt_data


class DocumentServiceTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.producer = make_producer()
        self.vehicle = make_vehicle()

    def create_receipt(self, **overrides):
        data = receipt_data(producer=self.producer, vehicle=self.vehicle)
        data.update(overrides)
        return create_receipt(user=self.user, **data)

    def test_receipt_gets_consecutive_number_and_audit_event(self):
        first = self.create_receipt()
        second = self.create_receipt(liters="10.00")

        self.assertRegex(first.internal_number, r"^REC-\d{4}-000001$")
        self.assertRegex(second.internal_number, r"^REC-\d{4}-000002$")
        self.assertTrue(
            AuditEvent.objects.filter(entity_id=str(first.pk), action=AuditEvent.Action.CREATE).exists()
        )

    def test_receipt_creation_is_idempotent_by_external_id(self):
        external_id = uuid.uuid4()
        first = self.create_receipt(external_id=external_id)
        retry = self.create_receipt(external_id=external_id, liters="999.00")

        self.assertEqual(first.pk, retry.pk)
        self.assertEqual(MilkReceipt.objects.count(), 1)
        self.assertEqual(first.liters, Decimal("123.45"))

    def test_non_positive_liters_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.create_receipt(liters="0.00")

    def test_receipt_can_be_voided_with_traceability(self):
        receipt = self.create_receipt()
        voided = void_receipt(receipt=receipt, user=self.user, reason="Dato incorrecto")

        self.assertEqual(voided.status, MilkReceipt.Status.VOIDED)
        self.assertEqual(voided.voided_by, self.user)
        self.assertEqual(voided.void_reason, "Dato incorrecto")
        self.assertTrue(
            AuditEvent.objects.filter(entity_id=str(receipt.pk), action=AuditEvent.Action.VOID).exists()
        )

    def test_void_requires_a_reason(self):
        receipt = self.create_receipt()
        with self.assertRaises(ValidationError):
            void_receipt(receipt=receipt, user=self.user, reason="   ")

    def test_inactive_producer_is_rejected(self):
        self.producer.active = False
        self.producer.save(update_fields=["active"])
        with self.assertRaises(ValidationError):
            self.create_receipt()
