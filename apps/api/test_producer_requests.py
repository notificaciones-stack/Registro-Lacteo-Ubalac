import uuid

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.operations.models import ProducerRequest
from apps.operations.tests.factories import make_user


class ProducerRequestTests(TestCase):
    def setUp(self):
        self.driver = make_user(username="driver-request", role=User.Role.DRIVER)
        self.client = APIClient()
        self.client.force_authenticate(self.driver)
        self.url = reverse("api-v1:producer-request-list")
        self.payload = {"external_id": str(uuid.uuid4()), "name": "Nuevo proveedor", "document_number": "12345", "farm_name": "La esperanza", "phone": "3001234567"}

    @override_settings(ACCOUNTING_NOTIFICATION_EMAILS=[], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_no_accounting_email_keeps_mobile_request_pending(self):
        self.assertEqual(self.client.post(self.url, self.payload, format="json").status_code, 503)
        self.assertEqual(ProducerRequest.objects.count(), 0)

    @override_settings(ACCOUNTING_NOTIFICATION_EMAILS=["contabilidad@example.com"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_idempotent_request_emails_accounting_once_and_is_private(self):
        first = self.client.post(self.url, self.payload, format="json")
        second = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["email_status"], "SENT")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["contabilidad@example.com"])
        self.assertEqual(ProducerRequest.objects.count(), 1)
        other = make_user(username="other-request", role=User.Role.DRIVER)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(self.url).data["count"], 0)
        self.assertEqual(self.client.post(self.url, self.payload, format="json").status_code, 409)
