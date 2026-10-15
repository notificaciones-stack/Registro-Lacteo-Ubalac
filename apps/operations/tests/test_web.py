from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.operations.models import MilkReceipt
from apps.operations.services import create_receipt

from .factories import make_producer, make_user, make_vehicle, receipt_data


class WebAuthorizationTests(TestCase):
    def setUp(self):
        self.producer = make_producer()
        self.vehicle = make_vehicle()

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("operations:receipt_list"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('operations:receipt_list')}",
        )

    def test_viewer_cannot_create_master_data(self):
        viewer = make_user(username="viewer", role=User.Role.VIEWER)
        self.client.force_login(viewer)
        response = self.client.get(reverse("operations:producer_create"))
        self.assertEqual(response.status_code, 403)

    def test_collector_can_create_receipt_and_generate_provider_voucher(self):
        collector = make_user(username="collector", role=User.Role.COLLECTOR)
        self.client.force_login(collector)
        response = self.client.post(
            reverse("operations:receipt_create"),
            {
                "producer": self.producer.pk,
                "vehicle": self.vehicle.pk,
                "collected_at": "2026-09-24T08:30",
                "liters": "75.50",
                "observations": "Ruta norte",
            },
        )
        receipt = MilkReceipt.objects.get()
        self.assertRedirects(response, reverse("operations:receipt_detail", kwargs={"pk": receipt.pk}))

        voucher = self.client.get(reverse("operations:receipt_voucher", kwargs={"pk": receipt.pk}))
        self.assertEqual(voucher.status_code, 200)
        self.assertContains(voucher, "Comprobante de recolección de leche")
        self.assertContains(voucher, receipt.internal_number)
        self.assertContains(voucher, self.producer.name)
        self.assertContains(voucher, "Formato 80 mm")
        self.assertNotContains(voucher, "Precio por litro")
        self.assertNotContains(voucher, "$", html=False)

        narrow_voucher = self.client.get(
            reverse("operations:receipt_voucher", kwargs={"pk": receipt.pk}),
            {"paper": "58"},
        )
        self.assertContains(narrow_voucher, "Formato 58 mm")

    def test_csrf_is_required_for_state_changes(self):
        supervisor = make_user(username="supervisor", role=User.Role.SUPERVISOR)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(supervisor)
        response = csrf_client.post(
            reverse("operations:producer_toggle", kwargs={"pk": self.producer.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_security_headers_and_private_cache_policy_are_present(self):
        user = make_user(username="headers", role=User.Role.VIEWER)
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertTrue(response.headers["X-Request-ID"])

    def test_temporary_password_forces_change_and_flag_is_cleared(self):
        user = make_user(username="temporary", role=User.Role.VIEWER)
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])
        self.client.force_login(user)

        blocked = self.client.get(reverse("dashboard:index"))
        self.assertRedirects(blocked, reverse("accounts:password_change"))

        changed = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "A-secure-test-password-2026!",
                "new_password1": "A-different-secure-password-2026!",
                "new_password2": "A-different-secure-password-2026!",
            },
        )
        self.assertRedirects(changed, reverse("accounts:password_change_done"))
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)

    def test_primary_web_pages_render_with_real_records(self):
        admin = make_user(username="smoke-admin", role=User.Role.ADMIN)
        receipt = create_receipt(
            user=admin,
            **receipt_data(producer=self.producer, vehicle=self.vehicle),
        )
        self.client.force_login(admin)
        urls = [
            reverse("dashboard:index"),
            reverse("operations:producer_list"),
            reverse("operations:vehicle_list"),
            reverse("operations:receipt_list"),
            reverse("operations:receipt_detail", kwargs={"pk": receipt.pk}),
            reverse("operations:receipt_voucher", kwargs={"pk": receipt.pk}),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
