from django.contrib import admin
from django import forms
from django.contrib.auth.hashers import make_password

from django.urls import reverse

from apps.accounts.models import User
from .models import DocumentSequence, DriverModuleSecurity, MilkReceipt, Producer, ProducerRequest, Route, RouteTrip, RouteSchedule, RouteScheduleHistory, Vehicle, WeighbridgeRecord, WeighbridgeRevision
from .models import CollectionProduct, FiscalParameter, PurchaseTerms, VehicleInspection, Notification, ProducerProduct, DriverProfile
from .forms import ProducerForm, FiscalParameterForm


@admin.register(ProducerRequest)
class ProducerRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "document_number", "requested_by", "email_status", "created_at")
    list_filter = ("email_status", "created_at")
    search_fields = ("name", "document_number", "requested_by__username", "external_id")
    readonly_fields = ("external_id", "requested_by", "name", "document_number", "farm_name", "phone", "municipality", "village", "notes", "email_status", "emailed_at", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False


class DriverModuleSecurityForm(forms.ModelForm):
    new_password = forms.CharField(label="Nueva clave del módulo", min_length=6, widget=forms.PasswordInput, help_text="Mínimo 6 caracteres. Se almacena como hash y no puede consultarse.")
    confirm_password = forms.CharField(label="Confirmar clave", widget=forms.PasswordInput)

    class Meta:
        model = DriverModuleSecurity
        fields = []

    def clean(self):
        values = super().clean()
        if values.get("new_password") != values.get("confirm_password"):
            raise forms.ValidationError("Las claves no coinciden.")
        return values

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.password_hash = make_password(self.cleaned_data["new_password"])
        if commit:
            instance.save()
        return instance


@admin.register(DriverModuleSecurity)
class DriverModuleSecurityAdmin(admin.ModelAdmin):
    form = DriverModuleSecurityForm
    fields = ("new_password", "confirm_password", "updated_at")
    readonly_fields = ("updated_at",)
    list_display = ("__str__", "updated_at")

    def has_add_permission(self, request):
        return self.has_module_permission(request) and not DriverModuleSecurity.objects.exists()

    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.role == User.Role.ADMIN

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


class BulkAdmin(admin.ModelAdmin):
    change_list_template = "admin/operations/bulk_change_list.html"
    bulk_kind = None

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(
            bulk_import_url=reverse("operations:bulk_import", kwargs={"kind": self.bulk_kind}),
            bulk_export_url=reverse("operations:bulk_export", kwargs={"kind": self.bulk_kind}),
            bulk_can_import=request.user.is_superuser or request.user.role == User.Role.ADMIN or (self.bulk_kind != "receipts" and request.user.role == User.Role.SUPERVISOR),
        )
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Producer)
class ProducerAdmin(BulkAdmin):
    form = ProducerForm
    bulk_kind = "producers"
    list_display = ("name", "document_type", "document_number", "farm_name", "municipality", "village", "assigned_driver", "assigned_route", "assigned_vehicle", "active")
    list_filter = ("active", "document_type", "municipality")
    search_fields = ("name", "farm_name", "document_number")

    def get_fields(self, request, obj=None):
        fields = [*ProducerForm.Meta.fields, "active"]
        if not (request.user.is_superuser or request.user.role == "ADMIN"):
            fields.remove("deductions")
        return fields + [f"price_{product.pk}" for product in CollectionProduct.objects.filter(active=True)]

    def get_form(self, request, obj=None, **kwargs):
        fields = kwargs.get("fields")
        kwargs["fields"] = [field for field in (fields if fields is not None else self.get_fields(request, obj)) if not field.startswith("price_")]
        parent = super().get_form(request, obj, **kwargs)
        class RequestProducerForm(parent):
            def __init__(self, *args, **form_kwargs):
                form_kwargs["user"] = request.user
                super().__init__(*args, **form_kwargs)
        return RequestProducerForm


@admin.register(CollectionProduct, FiscalParameter)
class PurchaseCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "active")

    def get_form(self, request, obj=None, **kwargs):
        if self.model is FiscalParameter:
            kwargs["form"] = FiscalParameterForm
        return super().get_form(request, obj, **kwargs)

    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.role == "ADMIN"

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if isinstance(form.instance, FiscalParameter):
            from .services.pricing import snapshot_terms
            for producer in form.instance.producers.all():
                snapshot_terms(producer)


@admin.register(PurchaseTerms, VehicleInspection, Notification, ProducerProduct, DriverProfile, WeighbridgeRevision)
class OperationalHistoryAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if f.name != "encrypted_login_password"]

    def has_add_permission(self, request):
        return False


@admin.register(Vehicle)
class VehicleAdmin(BulkAdmin):
    bulk_kind = "vehicles"
    list_display = ("plate", "route", "driver", "driver_name", "capacity_liters", "active")
    list_filter = ("active",)
    search_fields = ("plate", "name")
    autocomplete_fields = ("driver", "route")


@admin.register(RouteTrip)
class RouteTripAdmin(admin.ModelAdmin):
    list_display = ("route", "vehicle", "driver", "started_at", "ended_at")
    list_filter = ("route", "started_at", "ended_at")
    search_fields = ("route__name", "vehicle__plate", "driver__username")
    readonly_fields = ("route", "vehicle", "driver", "product", "inspection", "started_at", "ended_at", "notes", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.role in {User.Role.ADMIN, User.Role.SUPERVISOR}

    def has_delete_permission(self, request, obj=None):
        return False


class WeighbridgeRevisionInline(admin.TabularInline):
    model = WeighbridgeRevision
    extra = 0
    can_delete = False
    readonly_fields = [field.name for field in WeighbridgeRevision._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WeighbridgeRecord)
class WeighbridgeRecordAdmin(admin.ModelAdmin):
    list_display = ("trip", "status", "actual_liters", "variance_liters", "result", "validated_by", "validated_at")
    list_filter = ("status", "result", "weighed_at")
    search_fields = ("trip__route__name", "trip__vehicle__plate", "scale_ticket")
    readonly_fields = [field.name for field in WeighbridgeRecord._meta.fields]
    inlines = (WeighbridgeRevisionInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.role in {User.Role.ADMIN, User.Role.SUPERVISOR}

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Route)
class RouteAdmin(BulkAdmin):
    bulk_kind = "routes"
    list_display = ("name", "description", "active")
    search_fields = ("name", "description")
    list_filter = ("active",)


@admin.register(MilkReceipt)
class MilkReceiptAdmin(BulkAdmin):
    bulk_kind = "receipts"
    list_display = ("internal_number", "producer", "vehicle", "collected_at", "liters", "status", "source")
    list_filter = ("status", "source", "sync_status", "collected_at")
    search_fields = ("internal_number", "producer__name", "producer__document_number", "vehicle__plate")
    readonly_fields = ("id", "external_id", "internal_number", "created_at", "updated_at")
    autocomplete_fields = ("producer", "vehicle", "collected_by")

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (("producer", "product", "collected_at", "unit_price", "adjustments") if obj else ("unit_price", "adjustments"))

    def save_model(self, request, obj, form, change):
        if not change:
            from django.db import transaction
            from .services.pricing import terms_at
            from .services.documents import issue_document_number
            with transaction.atomic():
                obj.unit_price, obj.adjustments = terms_at(obj.producer, obj.product, obj.collected_at)
                obj.internal_number = issue_document_number(key="receipt", prefix="REC")
                obj.full_clean()
                super().save_model(request, obj, form, change)
        else:
            super().save_model(request, obj, form, change)


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ("key", "prefix", "next_value", "updated_at")
    readonly_fields = ("key", "prefix", "next_value", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RouteSchedule)
class RouteScheduleAdmin(admin.ModelAdmin):
    list_display = ("scheduled_date", "shift", "collection_type", "route", "vehicle", "driver", "status")
    list_filter = ("scheduled_date", "shift", "collection_type", "status")
    search_fields = ("route__name", "vehicle__plate", "driver__username", "driver__first_name", "driver__last_name")
    filter_horizontal = ("producers",)


@admin.register(RouteScheduleHistory)
class RouteScheduleHistoryAdmin(admin.ModelAdmin):
    list_display = ("schedule", "version", "changed_by", "changed_at", "reason")
    readonly_fields = ("schedule", "version", "changed_by", "changed_at", "reason", "snapshot")
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
