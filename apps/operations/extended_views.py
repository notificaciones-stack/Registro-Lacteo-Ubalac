from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, UpdateView, ListView, FormView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import User
from apps.auditlog.models import AuditEvent
from apps.auditlog.services import record_event
from apps.dashboard.forms import ReportFilterForm
from apps.dashboard.reports import filtered_data
from .assignments import assigned_vehicles
from .forms import FiscalParameterForm, ProductForm, VehicleInspectionForm
from .models import CollectionProduct, FiscalParameter, MilkReceipt, Producer, VehicleInspection, Notification
from .services.notifications import enqueue_notification
from .services.pricing import financial_summary, snapshot_terms


class CatalogView(RoleRequiredMixin, ListView):
    allowed_roles = {User.Role.ADMIN}
    template_name = "operations/catalog.html"
    context_object_name = "items"

    def get_queryset(self):
        return self.model.objects.all()


class ProductListView(CatalogView):
    model = CollectionProduct
    extra_context = {"title": "Productos de recolección", "create_route": "operations:product_create", "edit_route": "operations:product_update"}


class FiscalListView(CatalogView):
    model = FiscalParameter
    extra_context = {"title": "Retenciones e impuestos", "create_route": "operations:fiscal_create", "edit_route": "operations:fiscal_update"}


class CatalogSaveMixin(RoleRequiredMixin):
    allowed_roles = {User.Role.ADMIN}
    template_name = "operations/form.html"

    @transaction.atomic
    def form_valid(self, form):
        created = form.instance._state.adding
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.CREATE if created else AuditEvent.Action.UPDATE, instance=self.object, request=self.request)
        if isinstance(self.object, FiscalParameter):
            for producer in self.object.producers.all():
                snapshot_terms(producer)
        return response


class ProductCreateView(CatalogSaveMixin, CreateView):
    model, form_class = CollectionProduct, ProductForm
    success_url = reverse_lazy("operations:product_list")
    extra_context = {"title": "Nuevo producto", "cancel_url": reverse_lazy("operations:product_list")}


class ProductUpdateView(CatalogSaveMixin, UpdateView):
    model, form_class = CollectionProduct, ProductForm
    success_url = reverse_lazy("operations:product_list")
    extra_context = {"title": "Editar producto", "cancel_url": reverse_lazy("operations:product_list")}


class FiscalCreateView(CatalogSaveMixin, CreateView):
    model, form_class = FiscalParameter, FiscalParameterForm
    success_url = reverse_lazy("operations:fiscal_list")
    extra_context = {"title": "Nuevo parámetro fiscal", "cancel_url": reverse_lazy("operations:fiscal_list")}


class FiscalUpdateView(CatalogSaveMixin, UpdateView):
    model, form_class = FiscalParameter, FiscalParameterForm
    success_url = reverse_lazy("operations:fiscal_list")
    extra_context = {"title": "Editar parámetro fiscal", "cancel_url": reverse_lazy("operations:fiscal_list")}


class InspectionListView(RoleRequiredMixin, ListView):
    allowed_roles = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.LABORATORY, User.Role.DRIVER, User.Role.COLLECTOR}
    template_name = "operations/inspections.html"
    context_object_name = "inspections"
    paginate_by = 30

    def get_queryset(self):
        qs = VehicleInspection.objects.select_related("driver", "vehicle")
        if self.request.user.role in {User.Role.DRIVER, User.Role.COLLECTOR} and not self.request.user.is_superuser:
            qs = qs.filter(driver=self.request.user)
        for key, field in (("vehicle", "vehicle_id"), ("driver", "driver_id"), ("date_from", "inspected_on__gte"), ("date_to", "inspected_on__lte")):
            value = self.request.GET.get(key)
            if value:
                try:
                    qs = qs.filter(**{field: value})
                except (ValueError, ValidationError):
                    return qs.none()
        if self.request.GET.get("issues") == "1":
            from django.db.models import Q
            qs = qs.filter(Q(safe_to_operate=False) | Q(brakes="ISSUE") | Q(tires="ISSUE") | Q(lights="ISSUE") | Q(fluids="ISSUE") | Q(tank_hygiene="ISSUE") | Q(documents="ISSUE") | Q(safety_kit="ISSUE"))
        return qs


class InspectionCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = {User.Role.DRIVER, User.Role.COLLECTOR, User.Role.ADMIN, User.Role.SUPERVISOR}
    model, form_class = VehicleInspection, VehicleInspectionForm
    template_name = "operations/form.html"
    success_url = reverse_lazy("operations:inspection_list")
    extra_context = {"title": "Inspección preoperacional del vehículo", "cancel_url": reverse_lazy("operations:inspection_list")}

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["vehicle"].queryset = assigned_vehicles(self.request.user)
        return form

    def form_valid(self, form):
        form.instance.driver = self.request.user
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.CREATE, instance=self.object, request=self.request)
        if self.object.has_issues or not self.object.safe_to_operate:
            enqueue_notification(key=f"inspection:{self.object.pk}", subject="UBALAC · Novedad en inspección vehicular", body=f"Vehículo: {self.object.vehicle}\nConductor: {self.request.user}\nObservaciones: {self.object.observations}\nApto: {self.object.safe_to_operate}")
        return response


class ProducerStatementView(RoleRequiredMixin, TemplateView):
    allowed_roles = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.ACCOUNTING, User.Role.VIEWER}
    template_name = "operations/producer_statement.html"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == "ADMIN"):
            raise PermissionDenied
        producer = get_object_or_404(Producer, pk=kwargs["pk"])
        form = ReportFilterForm(request.POST)
        if not form.is_valid() or request.POST.get("confirm") != "yes":
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest("Confirme la valoración e indique un rango válido.")
        filters = {**form.cleaned_data, "producer": producer}
        qs, _ = filtered_data(filters)
        from .models import PurchaseTerms
        from .services.pricing import snapshot_terms
        snapshot_terms(producer)
        count = 0
        for receipt in qs.select_for_update().filter(status="CONFIRMED", unit_price__isnull=True):
            terms = PurchaseTerms.objects.filter(producer=producer, product=receipt.product).first()
            if not terms or terms.unit_price is None:
                continue
            receipt.unit_price, receipt.adjustments = terms.unit_price, terms.adjustments
            receipt.save(update_fields=["unit_price", "adjustments", "updated_at"])
            record_event(actor=request.user, action=AuditEvent.Action.UPDATE, instance=receipt, changes={"reason": "EXPLICIT_HISTORICAL_VALUATION", "price": str(terms.unit_price), "adjustments": terms.adjustments}, request=request)
            count += 1
        messages.success(request, f"Se valoraron {count} recibidos sin precio usando las condiciones vigentes. Los recibidos ya valorados permanecen intactos.")
        from urllib.parse import urlencode
        return redirect(f"{request.path}?{urlencode({'date_from': filters['start'].isoformat(), 'date_to': filters['end'].isoformat(), **({'product': str(filters['product'].pk)} if filters.get('product') else {})})}")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        producer = get_object_or_404(Producer, pk=self.kwargs["pk"])
        today = timezone.localdate()
        form = ReportFilterForm(self.request.GET or {"date_from": today.replace(day=1), "date_to": today})
        context.update(producer=producer, form=form, prices=producer.product_prices.select_related("product"), printable=self.request.GET.get("print") == "1", query_string=self.request.GET.urlencode())
        if form.is_valid():
            filters = {**form.cleaned_data, "producer": producer}
            qs, _ = filtered_data(filters)
            receipts = list(qs.select_related("product").order_by("collected_at"))
            context.update(financial_summary(receipts))
            context.update(receipts=receipts, start=filters["start"], end=filters["end"])
        return context


class NotificationListView(CatalogView):
    model = Notification
    template_name = "operations/notifications.html"
    paginate_by = 40
