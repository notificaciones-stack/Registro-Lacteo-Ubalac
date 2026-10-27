import io
from datetime import timedelta
from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User
from apps.dashboard.reports import report_data
from apps.operations.assignments import assigned_producers
from apps.operations.forms import ProducerForm, VehicleForm
from apps.operations.models import CollectionProduct, DriverProfile, MilkReceipt, Producer, ProducerProduct, Route, RouteTrip, Vehicle
from apps.operations.services import create_receipt
from apps.operations.services.bulk import export_workbook, import_workbook
from .factories import make_user, make_vehicle, make_producer


class GuidedWorkflowTests(TestCase):
    def setUp(self):
        self.admin = make_user(username='root', is_superuser=True)
        self.driver = make_user(username='driver', role=User.Role.DRIVER)
        self.route = Route.objects.create(name='NORTE')
        self.vehicle = make_vehicle()
        self.vehicle.driver, self.vehicle.route = self.driver, self.route
        self.vehicle.save()
        self.profile = DriverProfile.objects.create(user=self.driver, document_number='123', phone='300123')
        self.profile.routes.add(self.route)
        self.milk = CollectionProduct.objects.get(code='leche')
        self.whey = CollectionProduct.objects.get(code='suero')

    def form(self, **extra):
        return ProducerForm({'fiscal_category': 'SMALL', 'name': 'Nuevo', 'products': [str(self.milk.pk)], f'price_{self.milk.pk}': '1500', **extra}, user=self.admin)

    def test_driver_or_route_completes_only_unique_assignment(self):
        for field, value in [('assigned_driver', self.driver.pk), ('assigned_route', self.route.pk)]:
            form = self.form(**{field: str(value)})
            self.assertTrue(form.is_valid(), form.errors)
            producer = form.save()
            self.assertEqual(producer.assigned_driver, self.driver)
            self.assertEqual(producer.assigned_route, self.route)
            self.assertEqual(producer.assigned_vehicle, self.vehicle)
            self.assertIn(producer, assigned_producers(self.driver))

    def test_ambiguous_route_not_chosen_and_mismatch_rejected(self):
        other = Route.objects.create(name='SUR')
        self.profile.routes.add(other)
        Vehicle.objects.create(plate='XYZ789', driver=self.driver, route=other)
        form = self.form(assigned_driver=str(self.driver.pk))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.instance.assigned_route)
        self.assertIsNone(form.instance.assigned_vehicle)
        invalid = self.form(assigned_vehicle=str(self.vehicle.pk), assigned_route=str(other.pk))
        self.assertFalse(invalid.is_valid())
        self.assertIn('assigned_vehicle', invalid.errors)

    def test_explicit_assignment_not_visible_to_other_driver(self):
        other = make_user(username='other', role=User.Role.DRIVER)
        form = self.form(assigned_driver=str(self.driver.pk))
        self.assertTrue(form.is_valid(), form.errors)
        producer = form.save()
        self.assertNotIn(producer, assigned_producers(other))

    def test_vehicle_form_fills_driver_identity(self):
        form = VehicleForm({'plate': 'NEW123', 'driver': str(self.driver.pk)})
        self.assertTrue(form.is_valid(), form.errors)
        vehicle = form.save()
        self.assertEqual(vehicle.driver_name, 'driver')
        self.assertEqual(vehicle.driver_document, '123')
        self.assertEqual(vehicle.driver_phone, '300123')
        self.assertEqual(vehicle.route, self.route)

    def test_excel_keeps_assignment(self):
        form = self.form(assigned_driver=str(self.driver.pk))
        self.assertTrue(form.is_valid(), form.errors)
        producer = form.save()
        response = export_workbook('producers')
        created, updated, errors = import_workbook(io.BytesIO(response.content), 'producers', self.admin)
        self.assertEqual((created, updated, errors), (0, 1, []))
        producer.refresh_from_db()
        self.assertEqual(producer.assigned_driver, self.driver)
        self.assertEqual(producer.assigned_vehicle, self.vehicle)

    def test_mixed_trip_review_does_not_void_other_product(self):
        producer = make_producer()
        for product in (self.milk, self.whey):
            ProducerProduct.objects.create(producer=producer, product=product, unit_price='1000')
        trip = RouteTrip.objects.create(driver=self.driver, vehicle=self.vehicle, route=self.route, product=self.milk, started_at=timezone.now() - timedelta(minutes=1))
        def collect(product):
            return create_receipt(user=self.driver, producer=producer, vehicle=self.vehicle, product=product, collected_at=timezone.now(), liters='10')
        milk, whey, repeated = collect(self.milk), collect(self.whey), collect(self.milk)
        self.assertEqual(whey.trip_id, trip.pk)
        self.client.force_login(self.admin)
        alerts = self.client.get(reverse('operations:duplicate_alerts'))
        self.assertEqual(len(alerts.context['alerts']), 1)
        self.assertEqual(alerts.context['alerts'][0]['product_id'], self.milk.pk)
        url = reverse('operations:duplicate_review_product', args=[trip.pk, producer.pk, self.milk.pk])
        self.assertEqual(self.client.post(url, {'selected_id': str(milk.pk), 'reason': 'Captura duplicada de leche'}).status_code, 302)
        whey.refresh_from_db(); repeated.refresh_from_db()
        self.assertEqual(whey.status, 'CONFIRMED')
        self.assertEqual(repeated.status, 'VOIDED')
        data = report_data({'start': timezone.localdate(), 'end': timezone.localdate(), 'product': self.whey})
        self.assertEqual(data['total_liters'], 10)
        self.assertIn(trip, data['trips'])

    def test_driver_cannot_capture_unassigned_product(self):
        producer = make_producer()
        ProducerProduct.objects.create(producer=producer, product=self.whey, unit_price='300')
        self.profile.products.add(self.milk)
        RouteTrip.objects.create(driver=self.driver, vehicle=self.vehicle, route=self.route, product=self.milk)
        with self.assertRaises(ValidationError):
            create_receipt(user=self.driver, producer=producer, vehicle=self.vehicle, product=self.whey, collected_at=timezone.now(), liters='1')

    def test_superuser_delete_covers_other_registered_models(self):
        group = Group.objects.create(name='Prueba')
        model_admin = admin.site._registry[Group]
        request = RequestFactory().get('/')
        request.user = self.admin
        self.assertTrue(model_admin.has_delete_permission(request, group))
        model_admin.delete_model(request, group)
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())
        request.user = self.driver
        self.assertFalse(model_admin.has_delete_permission(request))
