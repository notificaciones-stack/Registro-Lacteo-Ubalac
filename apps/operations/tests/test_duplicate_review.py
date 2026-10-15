from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.operations.models import MilkReceipt, Route, RouteTrip
from apps.operations.services import create_receipt
from .factories import make_producer, make_user, make_vehicle


class ReviewWorkflowTests(TestCase):
    def setUp(self):
        self.admin = make_user(username="review-admin", role=User.Role.ADMIN)
        self.driver = make_user(username="review-driver", role=User.Role.DRIVER)
        self.route = Route.objects.create(name="Revision")
        self.vehicle = make_vehicle()
        self.vehicle.driver = self.driver
        self.vehicle.route = self.route
        self.vehicle.save()
        self.producer = make_producer()
        self.trip = RouteTrip.objects.create(route=self.route, vehicle=self.vehicle, driver=self.driver, started_at=timezone.now() - timedelta(minutes=5))

    def test_three_mobile_receipts_alert_review_and_retained_void_history(self):
        receipts = [create_receipt(user=self.driver, producer=self.producer, vehicle=self.vehicle, collected_at=timezone.now(), liters=str(10 + i)) for i in range(3)]
        alerts = reverse("operations:duplicate_alerts")
        review = reverse("operations:duplicate_review", kwargs={"trip_id": self.trip.pk, "producer_id": self.producer.pk})
        self.client.force_login(self.driver)
        self.assertEqual(self.client.get(alerts).status_code, 403)
        self.assertEqual(self.client.post(review, {"selected_id": str(receipts[1].pk), "reason": "Duplicado por captura incorrecta"}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(alerts), "Revisar y elegir")
        self.assertEqual(self.client.post(review, {"selected_id": str(receipts[1].pk), "reason": "Duplicado por captura incorrecta"}).status_code, 302)
        self.assertEqual(MilkReceipt.objects.filter(trip=self.trip).count(), 3)
        self.assertEqual(MilkReceipt.objects.filter(trip=self.trip, status=MilkReceipt.Status.CONFIRMED).count(), 1)
        self.assertFalse("Revisar y elegir" in self.client.get(alerts).content.decode())
        receipts[0].refresh_from_db()
        self.assertEqual(receipts[0].void_reason, "Duplicado por captura incorrecta")
        self.assertEqual(receipts[0].voided_by, self.admin)
        api = APIClient()
        api.force_authenticate(self.driver)
        statuses = [row["status"] for row in api.get(reverse("api-v1:receipt-list")).data["results"]]
        self.assertEqual(sorted(statuses), ["CONFIRMED", "VOIDED", "VOIDED"])

    def test_web_only_reopen_with_reason(self):
        self.trip.ended_at = timezone.now()
        self.trip.save(update_fields=["ended_at"])
        url = reverse("operations:trip_reopen", kwargs={"pk": self.trip.pk})
        self.client.force_login(self.driver)
        self.assertEqual(self.client.post(url, {"reason": "Cierre accidental del conductor"}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(url, {"reason": "corto"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"reason": "Cierre accidental del conductor"}).status_code, 302)
        self.trip.refresh_from_db()
        self.assertIsNone(self.trip.ended_at)
        self.assertEqual(self.trip.reopened_by, self.admin)
        self.assertEqual(self.trip.reopen_reason, "Cierre accidental del conductor")
        api = APIClient()
        api.force_authenticate(self.driver)
        trip = api.get(reverse("api-v1:route-trip-list")).data["results"][0]
        self.assertIsNotNone(trip["reopened_at"])
        self.assertIsNone(trip["ended_at"])
