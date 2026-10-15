import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError


class Command(BaseCommand):
    help = "Crea de forma idempotente el administrador inicial desde variables de entorno."

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")
        if not username or not password:
            raise CommandError(
                "Defina DJANGO_SUPERUSER_USERNAME y DJANGO_SUPERUSER_PASSWORD."
            )

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
                "role": user_model.Role.ADMIN,
            },
        )
        if created:
            try:
                validate_password(password, user)
            except ValidationError as exc:
                user.delete()
                raise CommandError("La contraseña no cumple la política: " + " ".join(exc.messages))
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Administrador {username} creado."))
        else:
            self.stdout.write(f"El usuario {username} ya existe; no se modificó su clave.")
