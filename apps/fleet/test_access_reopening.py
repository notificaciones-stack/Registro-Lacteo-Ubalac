from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.operations.models import Route, RouteTrip
from apps.operations.tests.factories import make_user, make_vehicle, make_inspection
from .models import ReopenRequest, FatigueSurvey
from .services import request_reopen, resolve_reopen
import uuid


class SSTAndReopeningTests(TestCase):
    def setUp(self):
        self.sst = make_user(username='sst', role=User.Role.SST)
        self.driver = make_user(username='driver', role=User.Role.DRIVER)
        self.other = make_user(username='other', role=User.Role.DRIVER)
        self.admin = make_user(username='admin')
        self.vehicle = make_vehicle()
        self.route = Route.objects.create(name='Prueba SST')
        self.trip = RouteTrip.objects.create(driver=self.driver, vehicle=self.vehicle, route=self.route, started_at=timezone.now()-timedelta(minutes=10), ended_at=timezone.now())
        make_inspection(self.driver, self.vehicle)
        FatigueSurvey.objects.create(external_id=uuid.uuid4(), trip=self.trip, sleep_hours=8, sleepy=False, rested=True, fatigue=False, commitment=True)

    def test_sst_only_reads_assigned_modules(self):
        self.client.force_login(self.sst)
        self.assertRedirects(self.client.get(reverse('dashboard:index')), reverse('operations:inspection_list'))
        self.assertContains(self.client.get(reverse('operations:inspection_list')), self.vehicle.plate)
        self.assertContains(self.client.get(reverse('fleet:fatigue')), self.vehicle.plate)
        for name in ['fleet:fuel', 'fleet:reopen_requests', 'operations:inspection_create', 'operations:producer_list', 'operations:duplicate_alerts', 'dashboard:reports']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.post(reverse('fleet:fatigue_create'), {}).status_code, 403)

    def test_sst_token_cannot_bypass_modules(self):
        api = APIClient(); api.force_authenticate(self.sst)
        self.assertEqual(api.get(reverse('api-v1:receipt-list')).status_code, 403)
        response = api.get(reverse('api-v1:vehicle-inspection-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(api.post(reverse('api-v1:vehicle-inspection-list'), {}).status_code, 403)

    def test_request_is_idempotent_and_only_web_can_approve(self):
        api = APIClient(); api.force_authenticate(self.driver)
        url = reverse('api-v1:route-trip-reopen-request', args=[self.trip.pk])
        for i in range(2):
            self.assertEqual(api.post(url, {'reason': 'Cerré el día por accidente'}).status_code, 200)
        self.assertEqual(ReopenRequest.objects.count(), 1)
        self.trip.refresh_from_db(); self.assertIsNotNone(self.trip.ended_at)
        item = ReopenRequest.objects.get()
        page = reverse('fleet:reopen_requests')
        self.client.force_login(self.driver)
        self.assertEqual(self.client.post(page, {'id': item.pk, 'decision': 'approve', 'reason': 'Revisión autorizada'}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(page, {'id': item.pk, 'decision': 'approve', 'reason': 'Revisión autorizada'}).status_code, 302)
        self.trip.refresh_from_db(); self.assertIsNone(self.trip.ended_at)
        self.assertEqual(api.get(url).data['status'], 'APPROVED')
        self.trip.ended_at = timezone.now(); self.trip.save()
        self.assertIsNone(api.get(url).data['status'])
        self.assertEqual(api.post(url, {'reason': 'Nuevo cierre accidental'}).data['status'], 'PENDING')
        self.assertEqual(ReopenRequest.objects.count(), 2)
        api.force_authenticate(self.other)
        self.assertEqual(api.post(url, {'reason': 'Intento de otro usuario'}).status_code, 404)

    def test_rejection_does_not_reopen_and_keeps_reason(self):
        item = request_reopen(trip=self.trip, user=self.driver, reason='Cierre por accidente')
        item = resolve_reopen(item=item, user=self.admin, approve=False, reason='No procede la reapertura')
        self.trip.refresh_from_db()
        self.assertIsNotNone(self.trip.ended_at)
        self.assertEqual(item.status, 'REJECTED')
        self.assertEqual(item.reviewed_by, self.admin)

    def test_stale_request_cannot_reopen_later_cycle(self):
        item = request_reopen(trip=self.trip, user=self.driver, reason='Cierre por accidente')
        self.trip.ended_at += timedelta(seconds=1); self.trip.save()
        with self.assertRaises(ValidationError):
            resolve_reopen(item=item, user=self.admin, approve=True, reason='Revisión autorizada')
