import io
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.auditlog.models import AuditEvent
from apps.dashboard.reports import report_data
from apps.operations.forms import ProducerForm, FiscalParameterForm
from apps.operations.models import CollectionProduct, FiscalParameter, MilkReceipt, Notification, Producer, ProducerProduct, PurchaseTerms, Route, RouteTrip, VehicleInspection, default_product
from apps.operations.services import create_receipt
from apps.operations.services.bulk import export_workbook, import_workbook
from apps.operations.services.notifications import deliver_notification, enqueue_notification
from apps.operations.services.pricing import receipt_amounts, snapshot_terms
from apps.operations.services.trips import start_trip
from .factories import make_inspection, make_producer, make_user, make_vehicle


class PurchaseExtensionTests(TestCase):
    def setUp(self):
        self.admin = make_user(username="purchase-admin", is_superuser=True)
        self.driver = make_user(username="purchase-driver", role=User.Role.DRIVER)
        self.supervisor = make_user(username="purchase-supervisor", role=User.Role.SUPERVISOR)
        self.producer = make_producer()
        self.milk = CollectionProduct.objects.get(pk=default_product())
        self.whey = CollectionProduct.objects.get(code="suero")
        self.vehicle = make_vehicle()
        self.route = Route.objects.create(name="COMPRAS")
        self.vehicle.driver, self.vehicle.route = self.driver, self.route
        self.vehicle.save()
        self.price = ProducerProduct.objects.create(producer=self.producer, product=self.milk, unit_price=Decimal("2000"))
        self.retention = FiscalParameter.objects.create(name="Retención configurable", rate=Decimal("2.5"))
        self.producer.deductions.add(self.retention)
        snapshot_terms(self.producer)

    def receipt(self, **kwargs):
        values = dict(user=self.admin, producer=self.producer, product=self.milk, vehicle=self.vehicle, collected_at=timezone.now(), liters="400")
        values.update(kwargs)
        return create_receipt(**values)

    def test_purchase_400_liters_and_retention(self):
        receipt = self.receipt()
        self.assertEqual(receipt.unit_price, Decimal("2000"))
        amounts = receipt_amounts(receipt)
        self.assertEqual(amounts["gross"], Decimal("800000.00"))
        self.assertEqual(amounts["deductions"], Decimal("20000.00"))
        self.assertEqual(amounts["net"], Decimal("780000.00"))

    def test_price_and_retention_changes_preserve_receipts_and_offline_terms(self):
        first = self.receipt()
        captured = timezone.now()
        self.price.unit_price = Decimal("2500")
        self.price.save()
        self.retention.rate = Decimal("3.5")
        self.retention.save()
        snapshot_terms(self.producer)
        delayed = self.receipt(collected_at=captured)
        current = self.receipt()
        first.refresh_from_db()
        self.assertEqual(delayed.unit_price, first.unit_price)
        self.assertEqual(delayed.adjustments, first.adjustments)
        self.assertEqual(current.unit_price, Decimal("2500"))
        self.assertEqual(current.adjustments[0]["rate"], "3.5000")

    def test_tax_additions_and_adjusted_scale_liters(self):
        tax = FiscalParameter.objects.create(name="Adición de prueba", kind="TAX", rate=Decimal("1"))
        self.producer.deductions.add(tax)
        snapshot_terms(self.producer)
        receipt = self.receipt()
        receipt.effective_liters = Decimal("440")
        amounts = receipt_amounts(receipt)
        self.assertEqual(amounts["gross"], Decimal("880000"))
        self.assertEqual(amounts["taxes"], Decimal("8800"))
        self.assertEqual(amounts["deductions"], Decimal("22000"))
        self.assertEqual(amounts["net"], Decimal("866800"))

    def test_small_provider_without_documents_and_normal_provider_validation(self):
        for name in ("Pequeño A", "Pequeño B"):
            provider = Producer(name=name, fiscal_category="SMALL")
            provider.full_clean()
            provider.save()
        provider = Producer(name="Normal", fiscal_category="SUPPORT")
        with self.assertRaises(ValidationError):
            provider.full_clean()

    def test_form_requires_prices_only_for_selected_products(self):
        values = {"fiscal_category": "SMALL", "name": "Nuevo sin documento", "products": [str(self.whey.pk)], f"price_{self.whey.pk}": "350.00"}
        form = ProducerForm(values, user=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        producer = form.save()
        self.assertEqual(list(producer.products.all()), [self.whey])
        self.assertEqual(producer.purchase_terms.first().unit_price, Decimal("350"))
        values["fiscal_category"] = "ELECTRONIC"
        invalid = ProducerForm(values, user=self.admin)
        self.assertFalse(invalid.is_valid())
        self.assertIn("document_number", invalid.errors)

    def test_provider_product_must_be_enabled(self):
        with self.assertRaises(ValidationError):
            self.receipt(product=self.whey)
        ProducerProduct.objects.create(producer=self.producer, product=self.whey, unit_price=Decimal("350"))
        snapshot_terms(self.producer)
        receipt = self.receipt(product=self.whey)
        self.assertEqual(receipt.unit_price, Decimal("350"))

    def test_product_filter_and_void_exclusion(self):
        self.receipt()
        ProducerProduct.objects.create(producer=self.producer, product=self.whey, unit_price=Decimal("500"))
        snapshot_terms(self.producer)
        self.receipt(product=self.whey, liters="100")
        void = self.receipt(liters="7")
        void.status = "VOIDED"
        void.save()
        today = timezone.localdate()
        data = report_data({"start": today, "end": today, "product": self.whey})
        self.assertEqual(data["total_liters"], Decimal("100"))
        self.assertEqual(data["financial"]["gross"], Decimal("50000"))
        self.assertEqual(len(data["financial_rows"]), 1)

    def test_unpriced_history_is_explicit_and_can_be_valued_only_by_admin(self):
        old = self.receipt(collected_at=timezone.now() - timedelta(days=2))
        self.assertIsNone(old.unit_price)
        today = timezone.localdate()
        fields = {"date_from": (today - timedelta(days=3)).isoformat(), "date_to": today.isoformat(), "confirm": "yes"}
        url = reverse("operations:producer_statement", kwargs={"pk": self.producer.pk})
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.post(url, fields).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(url, fields).status_code, 302)
        old.refresh_from_db()
        self.assertEqual(old.unit_price, Decimal("2000"))
        self.assertTrue(AuditEvent.objects.filter(changes__reason="EXPLICIT_HISTORICAL_VALUATION").exists())

    def test_catalogs_are_admin_only(self):
        self.client.force_login(self.supervisor)
        for url in ("fiscal_list", "fiscal_create", "product_list", "product_create", "notification_list"):
            self.assertEqual(self.client.get(reverse(f"operations:{url}")).status_code, 403)
        self.client.force_login(self.admin)
        for url in ("fiscal_list", "product_list", "notification_list"):
            self.assertEqual(self.client.get(reverse(f"operations:{url}")).status_code, 200)

    def test_excel_roundtrip_prices_products_and_small_provider(self):
        other = Producer.objects.create(name="Cuantía prueba", fiscal_category="SMALL")
        ProducerProduct.objects.create(producer=other, product=self.whey, unit_price=Decimal("400"))
        response = export_workbook("producers")
        book = load_workbook(io.BytesIO(response.content))
        headers = [c.value for c in book["Productores"][1]]
        self.assertIn("Clasificación", headers)
        self.assertIn("Precio suero COP/L", headers)
        created, updated, errors = import_workbook(io.BytesIO(response.content), "producers", self.admin)
        self.assertEqual(errors, [])
        self.assertEqual(created, 0)
        self.assertEqual(updated, 2)
        self.assertEqual(other.product_prices.get(product=self.whey).unit_price, Decimal("400"))

    def test_inspection_mandatory_same_driver_vehicle_day_and_safe(self):
        with self.assertRaises(ValidationError):
            start_trip(user=self.driver, route=self.route, vehicle=self.vehicle)
        inspection = make_inspection(self.driver, self.vehicle)
        trip = start_trip(user=self.driver, route=self.route, vehicle=self.vehicle, inspection=inspection, product=self.milk)
        self.assertEqual(trip.inspection_id, inspection.pk)
        self.assertEqual(trip.product_id, self.milk.pk)

    def test_cannot_declare_critical_fault_safe(self):
        inspection = make_inspection(self.driver, self.vehicle)
        inspection.brakes, inspection.observations = "ISSUE", "Frenos requieren revisión"
        with self.assertRaises(ValidationError):
            inspection.full_clean()

    @override_settings(OPERATIONS_NOTIFICATION_EMAILS=["operacion@example.com"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_inspection_api_is_idempotent_and_alerts_on_novelty(self):
        api = APIClient()
        api.force_authenticate(self.driver)
        payload = dict(external_id=str(uuid.uuid4()), vehicle=str(self.vehicle.pk), odometer_km=1500, observations="Luz auxiliar averiada", safe_to_operate=True, **{key: "OK" for key in ("brakes", "tires", "lights", "fluids", "tank_hygiene", "documents", "safety_kit")})
        payload["lights"] = "ISSUE"
        with self.captureOnCommitCallbacks(execute=True):
            first = api.post(reverse("api-v1:vehicle-inspection-list"), payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        second = api.post(reverse("api-v1:vehicle-inspection-list"), payload, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(VehicleInspection.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_new_views_and_statements_render(self):
        self.receipt()
        self.client.force_login(self.admin)
        for url in (reverse("dashboard:index"), reverse("dashboard:reports"), reverse("operations:producer_statement", kwargs={"pk": self.producer.pk}), reverse("operations:inspection_list"), reverse("operations:producer_create")):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        for url in (reverse("admin:operations_producer_add"), reverse("admin:operations_producer_change", args=[self.producer.pk]), reverse("admin:operations_fiscalparameter_add")):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_administration_layout_and_checkbox_widgets(self):
        from html.parser import HTMLParser
        from apps.operations.forms import ProducerForm

        class NavigationParser(HTMLParser):
            active_product = False
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == "a" and values.get("href") == reverse("operations:product_list"):
                    self.active_product = "is-active" in values.get("class", "").split()

        self.client.force_login(self.admin)
        for name in ("product_list", "fiscal_list", "notification_list", "inspection_list"):
            response = self.client.get(reverse(f"operations:{name}"))
            self.assertEqual(response.status_code, 200)
            # Sidebar icons must fit their compact container, rather than nest a header logo.
            self.assertNotContains(response, '<span class="nav-icon"><span class="module-logo')
            if name == "product_list":
                parser = NavigationParser()
                parser.feed(response.content.decode())
                self.assertTrue(parser.active_product)
        form = ProducerForm(user=self.admin)
        for name in ("products", "deductions"):
            self.assertEqual(form.fields[name].widget.attrs["class"], "assignment-checkboxes")
        response = self.client.get(reverse("admin:operations_producer_add"))
        self.assertContains(response, "css/admin-layout.css")
        self.assertNotContains(response, "css/app.css")

    def test_superuser_cascade_deletes_protected_dependencies_only_after_confirmation(self):
        receipt = self.receipt()
        model_admin = admin.site._registry[Producer]
        request = RequestFactory().get("/")
        request.user = self.admin
        preview, counts, perms, protected = model_admin.get_deleted_objects([self.producer], request)
        self.assertTrue(any(str(receipt) in item for item in preview))
        self.assertEqual(protected, [])
        model_admin.delete_model(request, self.producer)
        self.assertFalse(MilkReceipt.objects.filter(pk=receipt.pk).exists())
        self.assertFalse(Producer.objects.filter(pk=self.producer.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(action="DELETE").exists())
        request.user = self.supervisor
        self.assertFalse(model_admin.has_delete_permission(request))
        with self.assertRaises(PermissionDenied):
            model_admin.delete_queryset(request, Producer.objects.all())

    @override_settings(OPERATIONS_NOTIFICATION_EMAILS=["operacion@example.com"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_failure_is_saved_and_retried(self):
        item = enqueue_notification(key="test-notification", subject="Prueba", body="Novedad de prueba")
        with patch("apps.operations.services.notifications.send_mail", side_effect=RuntimeError("SMTP offline")):
            deliver_notification(item.pk)
        item.refresh_from_db()
        self.assertIsNone(item.sent_at)
        self.assertEqual(item.attempts, 1)
        deliver_notification(item.pk)
        deliver_notification(item.pk)
        self.assertEqual(len(mail.outbox), 1)
