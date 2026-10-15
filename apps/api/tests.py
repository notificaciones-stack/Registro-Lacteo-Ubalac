import uuid
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.operations.models import MilkReceipt
from apps.operations.services import create_receipt
from apps.operations.tests.factories import (
    make_producer,
    make_user,
    make_vehicle,
    receipt_data,
)


class MobileApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.producer = make_producer()
        self.vehicle = make_vehicle()

    def test_health_check_is_public(self):
        response = self.client.get(reverse("api-v1:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_receipts_require_authentication(self):
        response = self.client.get(reverse("api-v1:receipt-list"))
        self.assertIn(response.status_code, {401, 403})

    def test_token_login_rotates_token_and_rejects_expired_token(self):
        collector = make_user(username="token-user", role=User.Role.COLLECTOR)
        login_url = reverse("api-v1:token")
        credentials = {
            "username": collector.username,
            "password": "A-secure-test-password-2026!",
        }

        first = self.client.post(login_url, credentials, format="json")
        second = self.client.post(login_url, credentials, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertNotEqual(first.data["token"], second.data["token"])
        self.assertIn("expires_at", second.data)

        token = Token.objects.get(key=second.data["token"])
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(hours=13))
        expired_client = APIClient()
        expired_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = expired_client.get(reverse("api-v1:receipt-list"))
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_collector_creates_mobile_receipt_idempotently(self):
        collector = make_user(username="api-collector", role=User.Role.COLLECTOR)
        from apps.operations.models import Route, RouteTrip
        from django.utils.dateparse import parse_datetime
        route = Route.objects.create(name="Ruta API")
        RouteTrip.objects.create(route=route, vehicle=self.vehicle, driver=collector, started_at=parse_datetime("2026-09-24T13:00:00Z"), ended_at=parse_datetime("2026-09-24T14:00:00Z"))
        self.client.force_authenticate(collector)
        external_id = uuid.uuid4()
        payload = {
            "external_id": str(external_id),
            "producer": str(self.producer.pk),
            "vehicle": str(self.vehicle.pk),
            "collected_at": "2026-09-24T13:30:00Z",
            "liters": "88.25",
            "observations": "Capturado sin conexión y sincronizado",
        }

        created = self.client.post(reverse("api-v1:receipt-list"), payload, format="json")
        retried = self.client.post(reverse("api-v1:receipt-list"), payload, format="json")

        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(retried.status_code, 200, retried.data)
        self.assertEqual(created.data["id"], retried.data["id"])
        self.assertEqual(MilkReceipt.objects.count(), 1)
        self.assertEqual(MilkReceipt.objects.get().source, MilkReceipt.Source.MOBILE)

    def test_viewer_cannot_create_receipt(self):
        viewer = make_user(username="api-viewer", role=User.Role.VIEWER)
        self.client.force_authenticate(viewer)
        response = self.client.post(
            reverse("api-v1:receipt-list"),
            {
                "producer": str(self.producer.pk),
                "vehicle": str(self.vehicle.pk),
                "collected_at": "2026-09-24T13:30:00Z",
                "liters": "10.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_voucher_endpoint_returns_supplier_collection_data(self):
        collector = make_user(username="receipt-owner", role=User.Role.COLLECTOR)
        receipt = create_receipt(
            user=collector,
            **receipt_data(producer=self.producer, vehicle=self.vehicle),
        )
        self.client.force_authenticate(collector)

        response = self.client.get(
            reverse("api-v1:receipt-voucher", kwargs={"pk": receipt.pk})
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["document_type"], "MILK_COLLECTION_RECEIPT")
        self.assertEqual(response.data["copy_for"], "PRODUCER")
        self.assertEqual(response.data["receipt"]["internal_number"], receipt.internal_number)
        self.assertEqual(response.data["receipt"]["producer_name"], self.producer.name)
        self.assertEqual(response.data["receipt"]["liters"], "123.45")
