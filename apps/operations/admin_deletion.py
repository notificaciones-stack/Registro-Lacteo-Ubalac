"""Explicit superuser-only cascade deletion, including protected dependencies.

This does not weaken on_delete policies in application/API operations. The admin
confirmation lists exactly the graph that will be deleted. Nullable SET_NULL
relations remain intact, and the transaction rolls back on any failure.
"""
from collections import defaultdict

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import SET_NULL


def deletion_graph(objects):
    nodes, updates, visited = [], [], set()

    def visit(obj):
        key = (obj._meta.label, obj.pk)
        if key in visited:
            return
        visited.add(key)
        for rel in obj._meta.get_fields(include_hidden=True):
            if not (rel.auto_created and not rel.concrete and (rel.one_to_many or rel.one_to_one)):
                continue
            field = rel.field
            children = rel.related_model._base_manager.filter(**{field.name: obj.pk})
            if field.null and field.remote_field.on_delete == SET_NULL:
                updates.append((children, field.name))
            else:
                for child in children:
                    visit(child)
        nodes.append(obj)

    for obj in objects:
        visit(obj)
    return nodes, updates


class SuperuserDeleteMixin:
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_deleted_objects(self, objs, request):
        if not request.user.is_superuser:
            raise PermissionDenied
        nodes, _ = deletion_graph(objs)
        counts = defaultdict(int)
        for obj in nodes:
            counts[str(obj._meta.verbose_name_plural)] += 1
        return [f"{obj._meta.verbose_name}: {obj}" for obj in nodes], dict(counts), set(), []

    def delete_model(self, request, obj):
        self.delete_queryset(request, self.model.objects.filter(pk=obj.pk))

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied
        roots = list(queryset.select_for_update())
        nodes, updates = deletion_graph(roots)
        from apps.auditlog.models import AuditEvent
        from apps.auditlog.services import record_event
        summary = {"roots": [str(o.pk) for o in roots], "cascade_count": len(nodes)}
        for qs, field in updates:
            qs.update(**{field: None})
        # Django-managed foreign keys are deferrable. Delete children first;
        # auto-created M2M join records are part of the graph as well.
        for obj in nodes:
            obj.__class__._base_manager.filter(pk=obj.pk)._raw_delete(queryset.db)
        actor = request.user if request.user._meta.model.objects.filter(pk=request.user.pk).exists() else None
        if roots:
            record_event(actor=actor, action=AuditEvent.Action.DELETE, instance=roots[0], changes=summary, request=request)


def install_admin_deletion(site):
    for model, model_admin in site._registry.items():
        if model._meta.app_label in {"operations", "accounts", "auditlog"} and not isinstance(model_admin, SuperuserDeleteMixin):
            model_admin.__class__ = type(f"Superuser{model_admin.__class__.__name__}", (SuperuserDeleteMixin, model_admin.__class__), {})
