from django.contrib.auth.hashers import check_password, make_password
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.accounts.models import User
from apps.operations.models import DriverModuleSecurity, DriverProfile, Producer, Route, Vehicle
from apps.operations.services.trips import start_trip
from apps.operations.services import create_receipt
from .factories import make_inspection, make_producer, make_user, make_vehicle


class DriverConfigurationTests(TestCase):
    def setUp(self):
        self.admin = make_user(username="admin-driver-config", is_superuser=True)
        self.driver = make_user(username="driver-config", role=User.Role.DRIVER)
        self.supervisor = make_user(username="supervisor-config", role=User.Role.SUPERVISOR)
        self.route = Route.objects.create(name="Ruta base")
        self.other_route = Route.objects.create(name="Ruta externa")
        self.vehicle = make_vehicle()
        self.vehicle.driver = self.driver
        self.vehicle.route = self.route
        self.vehicle.save()
        self.producer = make_producer()
        self.other_producer = Producer.objects.create(document_type="CC", document_number="10000001", name="Otro productor")

    def unlock(self):
        return self.client.post(reverse("operations:driver_unlock"), {"password": "Clave adicional segura 2026!"})

    def test_admin_sets_module_password_and_only_admin_can_unlock(self):
        self.client.force_login(self.admin)
        add_url = reverse("admin:operations_drivermodulesecurity_add")
        self.assertEqual(self.client.get(add_url).status_code, 200)
        saved = self.client.post(add_url, {"new_password": "Clave adicional segura 2026!", "confirm_password": "Clave adicional segura 2026!", "_save": "Guardar"})
        self.assertEqual(saved.status_code, 302)
        security = DriverModuleSecurity.objects.get()
        self.assertNotEqual(security.password_hash, "Clave adicional segura 2026!")
        self.assertTrue(check_password("Clave adicional segura 2026!", security.password_hash))
        locked = self.client.get(reverse("operations:driver_list"))
        self.assertRedirects(locked, reverse("operations:driver_unlock") + "?next=%2Fconductores%2F")
        self.assertEqual(self.unlock().status_code, 302)
        self.assertContains(self.client.get(reverse("operations:driver_list")), "driver-config")
        security.password_hash = make_password("Una nueva clave segura 2026!")
        security.save()
        self.assertEqual(self.client.get(reverse("operations:driver_list")).status_code, 302)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse("operations:driver_list")).status_code, 403)
        self.assertIn(self.client.get(add_url).status_code, {302, 403})

    def test_platform_configures_assignments_and_driver_only_sees_own_api_data(self):
        DriverModuleSecurity.objects.create(password_hash=make_password("Clave adicional segura 2026!"))
        self.client.force_login(self.admin)
        self.unlock()
        url = reverse("operations:driver_configure", kwargs={"pk": self.driver.pk})
        form = self.client.get(url)
        self.assertContains(form, "Rutas asignadas")
        updated = self.client.post(url, {
            "first_name": "Elena", "last_name": "Rojas", "username": "driver-config", "email": "elena@example.com",
            "document_number": "123456", "phone": "3000000000", "device_id": "equipo-prueba-001",
            "routes": [str(self.route.pk)], "vehicles": [str(self.vehicle.pk)], "producers": [str(self.producer.pk)],
        })
        self.assertEqual(updated.status_code, 302, updated.context["form"].errors if updated.status_code == 200 else "")
        profile = DriverProfile.objects.get(user=self.driver)
        self.assertEqual(profile.device_id, "equipo-prueba-001")
        self.assertEqual(list(profile.routes.all()), [self.route])
        self.assertEqual(list(profile.producers.all()), [self.producer])
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.first_name, "Elena")
        api = APIClient()
        api.force_authenticate(self.driver)
        own = api.get(reverse("api-v1:driver-configuration"))
        self.assertEqual(own.status_code, 200, own.data)
        self.assertEqual([route["name"] for route in own.data["routes"]], ["RUTA BASE"])
        self.assertEqual([p["name"] for p in own.data["producers"]], [self.producer.name])
        self.assertNotIn("password", str(own.data).lower())
        self.assertNotIn("equipo-prueba-001", str(own.data))
        self.assertEqual(api.get(reverse("api-v1:route-list")).data["count"], 1)
        self.assertEqual(api.get(reverse("api-v1:producer-list")).data["count"], 1)
        with self.assertRaises(PermissionDenied):
            start_trip(user=self.driver, route=self.other_route, vehicle=self.vehicle)
        start_trip(user=self.driver, route=self.route, vehicle=self.vehicle, inspection=make_inspection(self.driver, self.vehicle))
        with self.assertRaises(ValidationError):
            create_receipt(user=self.driver, producer=self.other_producer, vehicle=self.vehicle, collected_at=timezone.now(), liters="5")
        self.driver.refresh_from_db()
        self.client.force_login(self.driver)
        self.assertEqual(self.client.get(reverse("operations:driver_list")).status_code, 403)
        self.assertContains(self.client.get(reverse("operations:driver_self")), "Elena Rojas")

    def test_registered_device_required_for_token_and_api(self):
        DriverProfile.objects.create(user=self.driver, device_id="phone-001")
        api = APIClient()
        login = reverse("api-v1:token")
        credentials = {"username": self.driver.username, "password": "A-secure-test-password-2026!"}
        self.assertEqual(api.post(login, credentials, format="json").status_code, 403)
        token_response = api.post(login, credentials, format="json", HTTP_X_DEVICE_ID="phone-001")
        self.assertEqual(token_response.status_code, 200)
        token = token_response.data["token"]
        api.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(api.get(reverse("api-v1:driver-configuration")).status_code, 401)
        api.credentials(HTTP_AUTHORIZATION=f"Token {token}", HTTP_X_DEVICE_ID="phone-001")
        self.assertEqual(api.get(reverse("api-v1:driver-configuration")).status_code, 200)

    def test_module_blocks_direct_edits_and_prevents_plate_takeover(self):
        DriverModuleSecurity.objects.create(password_hash=make_password("Clave adicional segura 2026!"))
        self.client.force_login(self.admin)
        url = reverse("operations:driver_configure", kwargs={"pk": self.driver.pk})
        self.assertEqual(self.client.post(url, {}).status_code, 302)
        self.unlock()
        other_driver = make_user(username="another-driver", role=User.Role.DRIVER)
        other_vehicle = Vehicle.objects.create(plate="XYZ789", driver=other_driver)
        response = self.client.post(url, {
            "first_name": "Cambio", "last_name": "Inválido", "username": self.driver.username,
            "document_number": "", "phone": "", "device_id": "", "routes": [str(self.route.pk)],
            "vehicles": [str(other_vehicle.pk)], "producers": [],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Escoja una opción válida")
        other_vehicle.refresh_from_db()
        self.assertEqual(other_vehicle.driver_id, other_driver.pk)

    def test_create_driver_with_password_and_assignments_inside_platform(self):
        DriverModuleSecurity.objects.create(password_hash=make_password("Clave adicional segura 2026!"))
        self.client.force_login(self.admin)
        url = reverse("operations:driver_create")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.unlock()
        self.assertContains(self.client.get(url), "Nuevo conductor")
        password = "Conductor nuevo clave 2026!"
        available_vehicle = Vehicle.objects.create(plate="NUE123", route=self.route)
        result = self.client.post(url, {
            "first_name": "Lucía", "last_name": "Pérez", "username": "lucia.driver", "email": "lucia@example.com",
            "document_number": "1003879719", "phone": "3200000000", "device_id": "phone-lucia",
            "routes": [str(self.route.pk), str(self.other_route.pk)],
            "vehicles": [str(available_vehicle.pk)], "producers": [str(self.producer.pk)],
            "password1": password, "password2": password,
        })
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'type="password" id="issued-password"')
        self.assertContains(result, 'data-password-toggle="issued-password"')
        self.assertEqual(result["Cache-Control"], "no-store, private")
        user = User.objects.get(username="lucia.driver")
        self.assertTrue(user.check_password(password))
        self.assertEqual(user.role, User.Role.DRIVER)
        self.assertEqual(set(user.driver_profile.routes.values_list("name", flat=True)), {"RUTA BASE", "RUTA EXTERNA"})
        self.assertEqual(list(user.driver_profile.producers.all()), [self.producer])
        available_vehicle.refresh_from_db()
        self.assertEqual(available_vehicle.driver_id, user.pk)
        self.assertNotIn(password, str(user.password))
        self.assertNotIn(password, str(user.driver_profile.__dict__))
        self.assertContains(self.client.get(reverse("operations:driver_list")), "lucia.driver")

    def test_password_reset_in_module_revokes_old_token(self):
        DriverModuleSecurity.objects.create(password_hash=make_password("Clave adicional segura 2026!"))
        token = Token.objects.create(user=self.driver)
        self.client.force_login(self.admin)
        self.unlock()
        url = reverse("operations:driver_password_reset", kwargs={"pk": self.driver.pk})
        self.assertContains(self.client.get(url), "Nueva contraseña")
        response = self.client.post(url, {"password1": "Nueva clave segura 2026!", "password2": "Nueva clave segura 2026!"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="password" id="issued-password"')
        self.driver.refresh_from_db()
        self.assertTrue(self.driver.check_password("Nueva clave segura 2026!"))
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(api.get(reverse("api-v1:driver-configuration")).status_code, 401)
        self.client.force_login(self.driver)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_six_character_passwords_and_protected_reveal_in_detail(self):
        self.client.force_login(self.admin)
        security_url = reverse("admin:operations_drivermodulesecurity_add")
        response = self.client.post(security_url, {"new_password": "Ab!789", "confirm_password": "Ab!789", "_save": "Guardar"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(check_password("Ab!789", DriverModuleSecurity.objects.get().password_hash))
        self.assertEqual(self.client.post(reverse("operations:driver_unlock"), {"password": "Ab!789"}).status_code, 302)
        detail_url = reverse("operations:driver_detail", kwargs={"pk": self.driver.pk})
        self.assertContains(self.client.get(detail_url), "No disponible")
        password = "Zx!789"
        reset = self.client.post(reverse("operations:driver_password_reset", kwargs={"pk": self.driver.pk}), {"password1": password, "password2": password})
        self.assertEqual(reset.status_code, 200)
        profile = DriverProfile.objects.get(user=self.driver)
        self.assertNotIn(password, profile.encrypted_login_password)
        detail = self.client.get(detail_url)
        self.assertContains(detail, f'value="{password}"')
        self.assertContains(detail, 'type="password"')
        self.assertContains(detail, 'data-password-toggle="driver-visible-password"')
        self.driver.refresh_from_db()
        self.client.force_login(self.driver)
        self.assertNotContains(self.client.get(reverse("operations:driver_self")), password)
        self.driver.set_password("Otra-clave!2026")
        self.driver.save(update_fields=["password"])
        self.client.force_login(self.admin)
        self.client.post(reverse("operations:driver_unlock"), {"password": "Ab!789"})
        self.assertNotContains(self.client.get(detail_url), f'value="{password}"')

    def test_assignments_use_checkboxes_and_edit_prompts_for_confirmation(self):
        DriverModuleSecurity.objects.create(password_hash=make_password("Clave adicional segura 2026!"))
        self.client.force_login(self.admin)
        self.unlock()
        profile = DriverProfile.objects.create(user=self.driver)
        profile.routes.add(self.route)
        profile.producers.add(self.producer)
        page = self.client.get(reverse("operations:driver_configure", kwargs={"pk": self.driver.pk}))
        form = page.context["form"]
        for name in ("routes", "vehicles", "producers"):
            self.assertIsInstance(form.fields[name].widget, forms.CheckboxSelectMultiple)
        self.assertContains(page, 'data-confirm-driver')
        self.assertContains(page, 'Se realizarán estas modificaciones')
        self.assertContains(page, '/static/js/driver-confirm.js')
        self.assertContains(page, 'checked')
