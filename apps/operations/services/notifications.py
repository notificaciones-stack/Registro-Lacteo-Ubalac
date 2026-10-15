import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ..models import Notification

logger = logging.getLogger(__name__)


def deliver_notification(pk):
    try:
        with transaction.atomic():
            item = Notification.objects.select_for_update().get(pk=pk)
            if item.sent_at:
                return
            item.attempts = F("attempts") + 1
            try:
                if not item.recipients:
                    raise ValueError("No hay destinatarios configurados.")
                if send_mail(item.subject, item.body, settings.DEFAULT_FROM_EMAIL, item.recipients, fail_silently=False) != 1:
                    raise ValueError("El proveedor de correo no confirmó el envío.")
                item.sent_at, item.last_error = timezone.now(), ""
            except Exception as exc:
                item.last_error = type(exc).__name__
                logger.warning("Notificación %s pendiente: %s", item.pk, type(exc).__name__)
            item.save(update_fields=["attempts", "sent_at", "last_error", "updated_at"])
    except Exception:
        logger.exception("No se pudo procesar notificación %s", pk)


def enqueue_notification(*, key, subject, body, recipients=None):
    item, _ = Notification.objects.get_or_create(key=key, defaults={"subject": subject, "body": body, "recipients": recipients if recipients is not None else settings.OPERATIONS_NOTIFICATION_EMAILS or settings.ACCOUNTING_NOTIFICATION_EMAILS})
    transaction.on_commit(lambda: deliver_notification(item.pk), robust=True)
    return item
