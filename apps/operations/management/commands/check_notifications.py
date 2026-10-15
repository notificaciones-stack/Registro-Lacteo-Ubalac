from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email


class Command(BaseCommand):
    help = "Verifica correo sin enviar mensajes. Use --send-test para un envío explícito de prueba."

    def add_arguments(self, parser):
        parser.add_argument("--send-test", action="store_true")

    def handle(self, **options):
        recipients = settings.ACCOUNTING_NOTIFICATION_EMAILS
        if not recipients:
            raise CommandError("Falta ACCOUNTING_NOTIFICATION_EMAILS")
        try:
            for email in [settings.DEFAULT_FROM_EMAIL, *recipients, *settings.OPERATIONS_NOTIFICATION_EMAILS]:
                validate_email(email)
        except ValidationError:
            raise CommandError("Hay una dirección de correo inválida.") from None
        backend = settings.EMAIL_BACKEND
        if backend.endswith("ResendEmailBackend") and not settings.RESEND_API_KEY:
            raise CommandError("Falta RESEND_API_KEY")
        if backend.endswith("smtp.EmailBackend") and (not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD):
            raise CommandError("Faltan credenciales SMTP")
        if not settings.DEBUG and ("console" in backend or "locmem" in backend or "dummy" in backend):
            raise CommandError("Producción requiere un transporte de correo real")
        self.stdout.write(self.style.SUCCESS("Configuración de correo válida. Credenciales no verificadas contra el proveedor."))
        if options["send_test"]:
            from django.core.mail import send_mail
            if send_mail("UBALAC · Prueba de correo", "Prueba de la configuración de notificaciones.", settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False) != 1:
                raise CommandError("El proveedor no confirmó el correo")
            self.stdout.write(self.style.SUCCESS("El proveedor aceptó el correo. Compruebe recepción y spam."))
