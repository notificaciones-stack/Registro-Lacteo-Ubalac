from django.core.management.base import BaseCommand

from apps.operations.services.trips import auto_close_expired_trips


class Command(BaseCommand):
    help = "Cierra recorridos abiertos a las 23:59 de su día local (America/Bogota)."

    def handle(self, *args, **options):
        count = auto_close_expired_trips()
        self.stdout.write(f"Recorridos cerrados automáticamente: {count}")
