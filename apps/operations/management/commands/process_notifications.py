from django.conf import settings
from django.core.management.base import BaseCommand

from apps.operations.models import Notification, ProducerRequest
from apps.operations.services.notifications import deliver_notification, enqueue_notification


class Command(BaseCommand):
    help = "Reintenta correos pendientes sin borrar solicitudes o inspecciones."

    def handle(self, **options):
        for item in ProducerRequest.objects.exclude(email_status="SENT")[:100]:
            notification = enqueue_notification(recipients=settings.ACCOUNTING_NOTIFICATION_EMAILS, key=f"producer-request:{item.external_id}", subject="UBALAC · Solicitud pendiente de proveedor", body=f"Nombre: {item.name}\nDocumento: {item.document_number}\nClasificación: {item.get_fiscal_category_display()}\nProductos: {item.requested_products}\nFinca: {item.farm_name}\nTeléfono: {item.phone}\nMunicipio: {item.municipality}\nVereda: {item.village}\nConductor: {item.requested_by}\nObservaciones: {item.notes}\nReferencia: {item.external_id}")
            if not notification.sent_at:
                notification.recipients = settings.ACCOUNTING_NOTIFICATION_EMAILS
                notification.save(update_fields=["recipients"])
                deliver_notification(notification.pk)
            notification.refresh_from_db()
            if notification.sent_at:
                ProducerRequest.objects.filter(pk=item.pk).update(email_status="SENT", emailed_at=notification.sent_at)
        for item in Notification.objects.filter(sent_at__isnull=True).order_by("created_at")[:100]:
            if not item.recipients:
                item.recipients = settings.OPERATIONS_NOTIFICATION_EMAILS or settings.ACCOUNTING_NOTIFICATION_EMAILS
                item.save(update_fields=["recipients"])
            deliver_notification(item.pk)
        self.stdout.write(f"Correos pendientes: {Notification.objects.filter(sent_at__isnull=True).count()}")
