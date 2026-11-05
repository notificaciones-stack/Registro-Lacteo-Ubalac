import base64
import io
import uuid
from datetime import timedelta
from decimal import Decimal
from PIL import Image
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from apps.operations.tests.factories import make_user, make_vehicle
from apps.operations.models import Route, RouteTrip
from apps.operations.services.trips import reopen_trip
from .models import FatigueSurvey, FuelEntry
from .services import efficiency, cycle_for


def photo():
    result = io.BytesIO(); Image.new('RGB', (12, 12), 'green').save(result, 'JPEG')
    return base64.b64encode(result.getvalue()).decode()


class FleetTests(TestCase):
    def setUp(self):
        self.driver = make_user(username='driver', role='DRIVER')
        self.other = make_user(username='other', role='DRIVER')
        self.admin = make_user()
        self.vehicle = make_vehicle()
        self.vehicle.driver = self.driver; self.vehicle.save()
        self.route = Route.objects.create(name='Ruta prueba')
        self.trip = RouteTrip.objects.create(driver=self.driver, vehicle=self.vehicle, route=self.route, started_at=timezone.now() - timedelta(minutes=30))
        self.client = APIClient(); self.client.force_authenticate(self.driver)
    def fuel(self, **overrides):
        return dict(external_id=str(uuid.uuid4()), trip=str(self.trip.pk), fueled_at=timezone.now().isoformat(), gallons='10.000', total_price='150000.00', odometer_km=1000, full_tank=True, observations='', fuel_photo=photo(), invoice_photo=photo(), **overrides)
    def survey(self):
        return dict(external_id=str(uuid.uuid4()), trip=str(self.trip.pk), expected_cycle='', sleep_hours='5.0', sleepy=True, rested=False, fatigue=True, commitment=True, observations='Cansancio al finalizar')
    def test_fuel_idempotence_and_photos(self):
        payload = self.fuel()
        for _ in range(2):
            response = self.client.post('/api/v1/fuel-entries/', payload, format='json')
            self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(FuelEntry.objects.count(), 1)
        self.assertNotIn('fuel_photo', response.data)
        self.client.force_login(self.driver)
        response = self.client.get(reverse('fleet:photo', args=[FuelEntry.objects.get().pk, 'fuel']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
    def test_cross_driver_and_invalid_photo(self):
        payload = self.fuel(); self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post('/api/v1/fuel-entries/', payload, format='json').status_code, 400)
        self.client.force_authenticate(self.driver); payload['fuel_photo'] = base64.b64encode(b'not a photo').decode()
        self.assertEqual(self.client.post('/api/v1/fuel-entries/', payload, format='json').status_code, 400)
        self.assertEqual(FuelEntry.objects.count(), 0)
    def test_survey_required_for_versioned_close_and_reopen_protection(self):
        url = f'/api/v1/route-trips/{self.trip.pk}/close/'
        self.assertEqual(self.client.post(url, {'expected_cycle': ''}, format='json').status_code, 400)
        payload = self.survey()
        first = self.client.post('/api/v1/fatigue-surveys/', payload, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertTrue(first.data['has_risk'])
        self.assertEqual(self.client.post('/api/v1/fatigue-surveys/', payload, format='json').status_code, 201)
        self.assertEqual(FatigueSurvey.objects.count(), 1)
        self.assertEqual(self.client.post(url, {'expected_cycle': ''}, format='json').status_code, 200)
        self.trip.refresh_from_db(); reopen_trip(trip=self.trip, user=self.admin, reason='Prueba de reapertura')
        self.assertEqual(self.client.post(url, {'expected_cycle': ''}, format='json').status_code, 409)
        self.trip.refresh_from_db(); self.assertIsNone(self.trip.ended_at)
        remote = self.client.get(f'/api/v1/route-trips/{self.trip.pk}/')
        self.assertEqual(remote.status_code, 200)
        self.assertEqual(remote.data['reopened_at'], cycle_for(self.trip))
        payload['external_id'] = str(uuid.uuid4()); payload['expected_cycle'] = cycle_for(self.trip)
        self.assertEqual(self.client.post('/api/v1/fatigue-surveys/', payload, format='json').status_code, 201)
        self.assertEqual(self.client.post(url, {'expected_cycle': cycle_for(self.trip)}, format='json').status_code, 200)
        self.assertEqual(FatigueSurvey.objects.count(), 2)
    def test_reports_filters_export_and_permissions(self):
        response = self.client.post('/api/v1/fuel-entries/', self.fuel(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.client.force_login(self.admin)
        for group in ['day', 'week', 'month']:
            response = self.client.get(reverse('fleet:fuel'), {'group': group, 'route': str(self.route.pk)})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '150000')
        self.assertEqual(self.client.get(reverse('fleet:fuel_export')).status_code, 200)
        self.assertEqual(self.client.get(reverse('fleet:fatigue')).status_code, 200)
        self.assertEqual(self.client.get(reverse('fleet:fuel'), {'date_from': 'not-a-date'}).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('fleet:photo', args=[FuelEntry.objects.get().pk, 'invoice'])).status_code, 404)
        self.assertEqual(self.client.get(reverse('fleet:fuel')).context['page_obj'].paginator.count, 0)
    def test_full_to_full_includes_partial_fills(self):
        start = timezone.now() - timedelta(minutes=20)
        a = FuelEntry.objects.create(external_id=uuid.uuid4(), trip=self.trip, fueled_at=start, gallons=10, total_price=100, odometer_km=1000, full_tank=True, fuel_photo=b'a', invoice_photo=b'a')
        FuelEntry.objects.create(external_id=uuid.uuid4(), trip=self.trip, fueled_at=start+timedelta(minutes=1), gallons=5, total_price=50, odometer_km=1100, full_tank=False, fuel_photo=b'a', invoice_photo=b'a')
        b = FuelEntry.objects.create(external_id=uuid.uuid4(), trip=self.trip, fueled_at=start+timedelta(minutes=2), gallons=5, total_price=50, odometer_km=1200, full_tank=True, fuel_photo=b'a', invoice_photo=b'a')
        self.assertIsNone(efficiency(a)); self.assertEqual(efficiency(b), Decimal('20.00'))
    def test_web_forms_create_and_close(self):
        self.client.force_login(self.driver)
        data = self.survey(); data['close_trip'] = 'yes'
        response = self.client.post(reverse('fleet:fatigue_create'), data)
        self.assertEqual(response.status_code, 302, response.content[:1000])
        self.trip.refresh_from_db(); self.assertIsNotNone(self.trip.ended_at)
        data = self.fuel(); data['fueled_at'] = (self.trip.started_at + timedelta(minutes=1)).isoformat()
        data['fuel_photo'] = SimpleUploadedFile('fuel.jpg', base64.b64decode(photo()), content_type='image/jpeg')
        data['invoice_photo'] = SimpleUploadedFile('invoice.jpg', base64.b64decode(photo()), content_type='image/jpeg')
        response = self.client.post(reverse('fleet:fuel_create'), data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.status_code == 200 else response.content)
