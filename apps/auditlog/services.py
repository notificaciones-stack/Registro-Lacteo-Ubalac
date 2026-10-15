from __future__ import annotations

from django.db import transaction

from .models import AuditEvent


def client_ip(request) -> str | None:
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR")


@transaction.atomic
def record_event(*, actor, action, instance, changes=None, request=None) -> AuditEvent:
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=instance._meta.label,
        entity_id=str(instance.pk),
        changes=changes or {},
        ip_address=client_ip(request),
        request_id=getattr(request, "request_id", ""),
    )

