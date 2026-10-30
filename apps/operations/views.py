from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.functional import cached_property
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView
from rest_framework.authtoken.models import Token

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import User
from apps.auditlog.models import AuditEvent
from apps.auditlog.services import record_event

from .forms import DriverConfigurationForm, DriverCreateForm, DriverModuleUnlockForm, DriverPasswordResetForm, RouteScheduleForm, DuplicateReviewForm, ImportWorkbookForm, MilkReceiptForm, ProducerForm, RouteForm, StartTripForm, TripReopenForm, VehicleForm, VoidReasonForm, WeighbridgeCorrectionForm, WeighbridgeRecordForm
from .models import CollectionProduct, DriverModuleSecurity, DriverProfile, MilkReceipt, Producer, Route, RouteTrip, RouteSchedule, Vehicle, WeighbridgeRecord
from .assignments import assigned_producers, assigned_routes, assigned_vehicles, driver_profile
from .password_vault import encrypt_driver_password, get_visible_driver_password
from .services.bulk import SHEETS, export_workbook, import_workbook
from .services.trips import close_trip, reopen_trip, start_trip
from .services.weighbridge import reopen_weighbridge, save_weighbridge_draft, validate_weighbridge
from .services import create_receipt, void_receipt
from .services.schedules import record_schedule_history, schedule_pdf


MASTER_ROLES = {User.Role.ADMIN, User.Role.SUPERVISOR}
RECEIPT_ROLES = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.COLLECTOR, User.Role.DRIVER}
TRIP_ROLES = RECEIPT_ROLES
WEIGHBRIDGE_ROLES = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.LABORATORY}


class DriverModuleGateMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.can_manage_drivers:
            security = DriverModuleSecurity.objects.first()
            unlock = request.session.get("driver_module_unlock")
            if not security or not unlock or unlock.get("version") != security.updated_at.isoformat() or unlock.get("expires", 0) < timezone.now().timestamp():
                from urllib.parse import urlencode

                return HttpResponseRedirect(f"{reverse('operations:driver_unlock')}?{urlencode({'next': request.get_full_path()})}")
        return super().dispatch(request, *args, **kwargs)


class DriverModuleUnlockView(RoleRequiredMixin, FormView):
    allowed_roles = {User.Role.ADMIN}
    form_class = DriverModuleUnlockForm
    template_name = "operations/driver_unlock.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["configured"] = DriverModuleSecurity.objects.exists()
        context["next"] = self.request.GET.get("next", "")
        return context

    def form_valid(self, form):
        security = DriverModuleSecurity.objects.first()
        if not security:
            form.add_error(None, "Un administrador debe establecer primero la clave del módulo en el panel admin.")
            return self.form_invalid(form)
        cache_key = f"driver-module-attempts:{self.request.user.pk}"
        if int(cache.get(cache_key, 0)) >= 5:
            form.add_error(None, "Demasiados intentos. Intente de nuevo en 15 minutos.")
            return self.form_invalid(form)
        if not check_password(form.cleaned_data["password"], security.password_hash):
            cache.set(cache_key, int(cache.get(cache_key, 0)) + 1, 15 * 60)
            form.add_error("password", "Clave incorrecta.")
            return self.form_invalid(form)
        cache.delete(cache_key)
        self.request.session["driver_module_unlock"] = {"version": security.updated_at.isoformat(), "expires": timezone.now().timestamp() + 30 * 60}
        target = self.request.GET.get("next") or reverse("operations:driver_list")
        if not (target.startswith("/conductores/") and url_has_allowed_host_and_scheme(target, allowed_hosts={self.request.get_host()})):
            target = reverse("operations:driver_list")
        return HttpResponseRedirect(target)


class DriverModuleLockView(RoleRequiredMixin, View):
    allowed_roles = {User.Role.ADMIN}

    def post(self, request):
        request.session.pop("driver_module_unlock", None)
        return HttpResponseRedirect(reverse("operations:driver_unlock"))


class DriverListView(DriverModuleGateMixin, RoleRequiredMixin, ListView):
    allowed_roles = {User.Role.ADMIN}
    template_name = "operations/driver_list.html"
    context_object_name = "drivers"
    paginate_by = 30

    def get_queryset(self):
        qs = User.objects.filter(role__in=[User.Role.DRIVER, User.Role.COLLECTOR]).select_related("driver_profile").prefetch_related("assigned_vehicles", "driver_profile__routes")
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
        return qs


def lock_selected_vehicles(form, user):
    selected = set(form.cleaned_data["vehicles"].values_list("pk", flat=True))
    locked = list(Vehicle.objects.select_for_update().filter(pk__in=selected))
    if len(locked) != len(selected) or any(vehicle.driver_id not in (None, user.pk) for vehicle in locked):
        form.add_error("vehicles", "Una placa seleccionada fue asignada a otro conductor. Actualice la página.")
        return None
    return selected


def save_driver_assignments(form, user):
    profile = form.save()
    selected = set(form.cleaned_data["vehicles"].values_list("pk", flat=True))
    now = timezone.now()
    Vehicle.objects.filter(driver=user).exclude(pk__in=selected).update(driver=None, updated_at=now)
    Vehicle.objects.filter(pk__in=selected).update(driver=user, driver_name=user.get_full_name() or user.username, driver_document=profile.document_number, driver_phone=profile.phone, updated_at=now)
    return profile


class DriverCreateView(DriverModuleGateMixin, RoleRequiredMixin, FormView):
    allowed_roles = {User.Role.ADMIN}
    form_class = DriverCreateForm
    template_name = "operations/driver_create.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = DriverProfile(user=User(role=User.Role.DRIVER))
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            user = form.instance.user
            selected = lock_selected_vehicles(form, user)
            if selected is None:
                return self.form_invalid(form)
            user.username = form.cleaned_data["username"]
            user.first_name = form.cleaned_data["first_name"].strip()
            user.last_name = form.cleaned_data["last_name"].strip()
            user.email = form.cleaned_data["email"]
            user.set_password(form.cleaned_data["password1"])
            user.save()
            profile = save_driver_assignments(form, user)
            profile.encrypted_login_password = encrypt_driver_password(form.cleaned_data["password1"])
            profile.save(update_fields=["encrypted_login_password", "updated_at"])
            record_event(actor=self.request.user, action=AuditEvent.Action.CREATE, instance=profile, changes={"driver": user.username, "routes": list(profile.routes.values_list("name", flat=True)), "vehicles": list(Vehicle.objects.filter(driver=user).values_list("plate", flat=True))}, request=self.request)
        return render(self.request, "operations/driver_password_issued.html", {"driver": user, "issued_password": form.cleaned_data["password1"], "created": True})


class DriverPasswordResetView(DriverModuleGateMixin, RoleRequiredMixin, FormView):
    allowed_roles = {User.Role.ADMIN}
    form_class = DriverPasswordResetForm
    template_name = "operations/driver_password_reset.html"

    @cached_property
    def driver(self):
        return get_object_or_404(User, pk=self.kwargs["pk"], role__in=[User.Role.DRIVER, User.Role.COLLECTOR])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.driver
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["driver"] = self.driver
        return context

    def form_valid(self, form):
        with transaction.atomic():
            self.driver.set_password(form.cleaned_data["password1"])
            self.driver.save(update_fields=["password"])
            profile, _ = DriverProfile.objects.get_or_create(user=self.driver)
            profile.encrypted_login_password = encrypt_driver_password(form.cleaned_data["password1"])
            profile.save(update_fields=["encrypted_login_password", "updated_at"])
            Token.objects.filter(user=self.driver).delete()
            record_event(actor=self.request.user, action=AuditEvent.Action.UPDATE, instance=self.driver, changes={"password_reset": True}, request=self.request)
        return render(self.request, "operations/driver_password_issued.html", {"driver": self.driver, "issued_password": form.cleaned_data["password1"], "created": False})


class DriverDetailView(DriverModuleGateMixin, RoleRequiredMixin, DetailView):
    allowed_roles = {User.Role.ADMIN}
    model = User
    template_name = "operations/driver_detail.html"
    context_object_name = "driver"

    def get_queryset(self):
        return User.objects.filter(role__in=[User.Role.DRIVER, User.Role.COLLECTOR])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = driver_profile(self.object)
        context.update(profile=profile, visible_password=get_visible_driver_password(profile), routes=assigned_routes(self.object), vehicles=assigned_vehicles(self.object), producers=assigned_producers(self.object))
        return context


class DriverSelfView(RoleRequiredMixin, TemplateView):
    allowed_roles = {User.Role.DRIVER, User.Role.COLLECTOR}
    template_name = "operations/driver_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update(driver=user, profile=driver_profile(user), routes=assigned_routes(user), vehicles=assigned_vehicles(user), producers=assigned_producers(user), own_profile=True)
        return context


class DriverConfigurationView(DriverModuleGateMixin, RoleRequiredMixin, FormView):
    allowed_roles = {User.Role.ADMIN}
    form_class = DriverConfigurationForm
    template_name = "operations/driver_configure.html"

    @cached_property
    def driver(self):
        return get_object_or_404(User, pk=self.kwargs["pk"], role__in=[User.Role.DRIVER, User.Role.COLLECTOR])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = DriverProfile.objects.filter(user=self.driver).first() or DriverProfile(user=self.driver)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["driver"] = self.driver
        return context

    def form_valid(self, form):
        with transaction.atomic():
            user = self.driver
            if lock_selected_vehicles(form, user) is None:
                return self.form_invalid(form)
            user.first_name = form.cleaned_data["first_name"].strip()
            user.last_name = form.cleaned_data["last_name"].strip()
            user.username = form.cleaned_data["username"]
            user.email = form.cleaned_data["email"]
            user.save(update_fields=["first_name", "last_name", "username", "email"])
            profile = save_driver_assignments(form, user)
            record_event(actor=self.request.user, action=AuditEvent.Action.UPDATE, instance=profile, changes={"driver": user.username, "routes": list(profile.routes.values_list("name", flat=True)), "vehicles": list(Vehicle.objects.filter(driver=user).values_list("plate", flat=True))}, request=self.request)
        messages.success(self.request, "Configuración del conductor actualizada.")
        return HttpResponseRedirect(reverse("operations:driver_detail", kwargs={"pk": self.driver.pk}))


class SearchableListMixin:
    paginate_by = 25
    search_fields: tuple[str, ...] = ()

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query and self.search_fields:
            criteria = Q()
            for field in self.search_fields:
                criteria |= Q(**{f"{field}__icontains": query})
            queryset = queryset.filter(criteria)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        return context


class RouteScheduleListView(RoleRequiredMixin, SearchableListMixin, ListView):
    allowed_roles = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.LABORATORY}
    model = RouteSchedule
    template_name = "operations/schedule_list.html"
    context_object_name = "schedules"
    paginate_by = 30
    search_fields = ("driver__username", "driver__first_name", "driver__last_name", "route__name", "vehicle__plate")

    def get_queryset(self):
        qs = super().get_queryset().select_related("driver", "route", "vehicle", "created_by", "updated_by").prefetch_related("producers")
        if self.request.GET.get("date"):
            qs = qs.filter(scheduled_date=self.request.GET["date"])
        if self.request.GET.get("shift"):
            qs = qs.filter(shift=self.request.GET["shift"])
        if self.request.GET.get("collection_type"):
            qs = qs.filter(collection_type=self.request.GET["collection_type"])
        return qs


class RouteScheduleCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = MASTER_ROLES
    model = RouteSchedule
    form_class = RouteScheduleForm
    template_name = "operations/schedule_form.html"

    def get_initial(self):
        initial = super().get_initial()
        driver_id = self.request.GET.get("driver")
        if driver_id and User.objects.filter(pk=driver_id, is_active=True, role__in=[User.Role.DRIVER, User.Role.COLLECTOR]).exists():
            initial["driver"] = driver_id
        return initial

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.created_by = self.request.user
            form.instance.updated_by = self.request.user
            response = super().form_valid(form)
            record_schedule_history(self.object, self.request.user, "Programación creada")
            record_event(actor=self.request.user, action=AuditEvent.Action.CREATE, instance=self.object, changes={"schedule": str(self.object)}, request=self.request)
        messages.success(self.request, "Programación creada correctamente.")
        return response

    def get_success_url(self):
        return reverse("operations:schedule_detail", kwargs={"pk": self.object.pk})


class RouteScheduleUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = MASTER_ROLES
    model = RouteSchedule
    form_class = RouteScheduleForm
    template_name = "operations/schedule_form.html"

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.updated_by = self.request.user
            response = super().form_valid(form)
            record_schedule_history(self.object, self.request.user, form.cleaned_data["change_reason"])
            record_event(actor=self.request.user, action=AuditEvent.Action.UPDATE, instance=self.object, changes={"reason": form.cleaned_data["change_reason"]}, request=self.request)
        messages.success(self.request, "Programación actualizada y cambio registrado en el historial.")
        return response

    def get_success_url(self):
        return reverse("operations:schedule_detail", kwargs={"pk": self.object.pk})


class RouteScheduleDetailView(RoleRequiredMixin, DetailView):
    allowed_roles = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.LABORATORY}
    model = RouteSchedule
    template_name = "operations/schedule_detail.html"
    context_object_name = "schedule"

    def get_queryset(self):
        return super().get_queryset().select_related("driver", "route", "vehicle", "created_by", "updated_by").prefetch_related("producers", "history__changed_by")


class RouteSchedulePdfView(RoleRequiredMixin, DetailView):
    allowed_roles = {User.Role.ADMIN, User.Role.SUPERVISOR, User.Role.LABORATORY}
    model = RouteSchedule

    def get(self, request, *args, **kwargs):
        schedule = self.get_object()
        response = HttpResponse(schedule_pdf(schedule), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="programacion-{schedule.scheduled_date}-{schedule.pk}.pdf"'
        return response


class ProducerListView(LoginRequiredMixin, SearchableListMixin, ListView):
    model = Producer
    template_name = "operations/producer_list.html"
    context_object_name = "producers"
    search_fields = ("name", "farm_name", "document_number", "municipality")

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("product_prices__product")
        if self.request.GET.get("product"):
            qs = qs.filter(products__code=self.request.GET["product"])
        return qs

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "products": CollectionProduct.objects.all()}


class ProducerCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = MASTER_ROLES
    model = Producer
    form_class = ProducerForm
    template_name = "operations/form.html"
    success_url = reverse_lazy("operations:producer_list")
    extra_context = {"title": "Nuevo productor", "cancel_url": reverse_lazy("operations:producer_list")}

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.CREATE, instance=self.object, request=self.request)
        messages.success(self.request, "Productor creado correctamente.")
        return response


class ProducerUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = MASTER_ROLES
    model = Producer
    form_class = ProducerForm
    template_name = "operations/form.html"
    success_url = reverse_lazy("operations:producer_list")
    extra_context = {"title": "Editar productor", "cancel_url": reverse_lazy("operations:producer_list")}

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.UPDATE, instance=self.object, request=self.request)
        messages.success(self.request, "Productor actualizado correctamente.")
        return response


class ProducerToggleActiveView(RoleRequiredMixin, View):
    allowed_roles = MASTER_ROLES

    def post(self, request, pk):
        producer = get_object_or_404(Producer, pk=pk)
        producer.active = not producer.active
        producer.save(update_fields=["active", "updated_at"])
        action = AuditEvent.Action.ACTIVATE if producer.active else AuditEvent.Action.DEACTIVATE
        record_event(actor=request.user, action=action, instance=producer, request=request)
        messages.success(request, "Estado del productor actualizado.")
        return HttpResponseRedirect(reverse("operations:producer_list"))


class VehicleListView(LoginRequiredMixin, SearchableListMixin, ListView):
    model = Vehicle
    template_name = "operations/vehicle_list.html"
    context_object_name = "vehicles"
    search_fields = ("plate", "name", "route__name", "driver_name")


class RouteListView(LoginRequiredMixin, SearchableListMixin, ListView):
    model = Route
    template_name = "operations/route_list.html"
    context_object_name = "routes"
    search_fields = ("name", "description")


class RouteCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = MASTER_ROLES
    model = Route
    form_class = RouteForm
    template_name = "operations/form.html"
    success_url = reverse_lazy("operations:route_list")
    extra_context = {"title": "Nueva ruta", "cancel_url": reverse_lazy("operations:route_list")}

    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.CREATE, instance=self.object, request=self.request)
        return response


class RouteUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = MASTER_ROLES
    model = Route
    form_class = RouteForm
    template_name = "operations/form.html"
    success_url = reverse_lazy("operations:route_list")
    extra_context = {"title": "Editar ruta", "cancel_url": reverse_lazy("operations:route_list")}

    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.UPDATE, instance=self.object, request=self.request)
        return response


class RouteToggleActiveView(RoleRequiredMixin, View):
    allowed_roles = MASTER_ROLES

    def post(self, request, pk):
        route = get_object_or_404(Route, pk=pk)
        route.active = not route.active
        route.save(update_fields=["active", "updated_at"])
        record_event(actor=request.user, action=AuditEvent.Action.ACTIVATE if route.active else AuditEvent.Action.DEACTIVATE, instance=route, request=request)
        return HttpResponseRedirect(reverse("operations:route_list"))


class BulkImportView(RoleRequiredMixin, FormView):
    form_class = ImportWorkbookForm
    template_name = "operations/import.html"
    allowed_roles = MASTER_ROLES

    def dispatch(self, request, *args, **kwargs):
        self.kind = kwargs["kind"]
        if self.kind not in SHEETS:
            raise PermissionDenied("Módulo desconocido.")
        if self.kind == "receipts" and not (request.user.is_authenticated and (request.user.is_superuser or request.user.role == User.Role.ADMIN)):
            raise PermissionDenied("Solo el administrador puede importar recibidos.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(kind=self.kind, sheet=SHEETS[self.kind], return_url=reverse(f"operations:{self.kind[:-1] if self.kind != 'receipts' else 'receipt'}_list") if self.kind != "producers" else reverse("operations:producer_list"))
        return context

    def form_valid(self, form):
        try:
            created, updated, errors = import_workbook(form.cleaned_data["file"], self.kind, self.request.user, self.request)
        except (ValueError, ValidationError) as exc:
            errors = [str(exc)]
        if errors:
            return self.render_to_response(self.get_context_data(form=form, import_errors=errors))
        messages.success(self.request, f"Importación completada: {created} creados y {updated} actualizados.")
        return HttpResponseRedirect(self.get_context_data()["return_url"])


class BulkExportView(LoginRequiredMixin, View):
    def get(self, request, kind):
        if kind not in SHEETS:
            raise PermissionDenied("Módulo desconocido.")
        return export_workbook(kind)


class TripListView(RoleRequiredMixin, ListView):
    allowed_roles = TRIP_ROLES
    model = RouteTrip
    template_name = "operations/trip_list.html"
    context_object_name = "trips"
    paginate_by = 30

    def get_queryset(self):
        qs = RouteTrip.objects.select_related("route", "vehicle", "driver").all()
        if not (self.request.user.is_superuser or self.request.user.role in MASTER_ROLES):
            qs = qs.filter(driver=self.request.user)
        if self.request.GET.get("product"):
            qs = qs.filter(Q(receipts__product__code=self.request.GET["product"]) | Q(receipts__isnull=True, product__code=self.request.GET["product"])).distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["open_trip"] = RouteTrip.objects.filter(driver=self.request.user, ended_at__isnull=True).select_related("route", "vehicle").first()
        context["products"] = CollectionProduct.objects.all()
        return context


class TripStartView(RoleRequiredMixin, FormView):
    allowed_roles = TRIP_ROLES
    form_class = StartTripForm
    template_name = "operations/trip_start.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            trip = start_trip(user=self.request.user, **form.cleaned_data, request=self.request)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"Ruta {trip.route.name} abierta a las {timezone.localtime(trip.started_at):%H:%M}.")
        return HttpResponseRedirect(reverse("operations:trip_list"))


class TripCloseView(RoleRequiredMixin, View):
    allowed_roles = TRIP_ROLES

    def post(self, request, pk):
        trip = get_object_or_404(RouteTrip, pk=pk)
        try:
            close_trip(trip=trip, user=request.user, request=request)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Recorrido cerrado y duración registrada.")
        return HttpResponseRedirect(reverse("operations:trip_list"))


class TripReopenView(RoleRequiredMixin, FormView):
    allowed_roles = MASTER_ROLES
    form_class = TripReopenForm
    template_name = "operations/trip_reopen.html"

    def dispatch(self, request, *args, **kwargs):
        self.trip = get_object_or_404(RouteTrip.objects.select_related("route", "vehicle", "driver"), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "trip": self.trip}

    def form_valid(self, form):
        try:
            reopen_trip(trip=self.trip, user=self.request.user, reason=form.cleaned_data["reason"], request=self.request)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Recorrido reabierto; el conductor lo verá al sincronizar.")
        return HttpResponseRedirect(reverse("operations:trip_list"))


class WeighbridgeListView(RoleRequiredMixin, ListView):
    allowed_roles = WEIGHBRIDGE_ROLES
    model = RouteTrip
    template_name = "operations/weighbridge_list.html"
    context_object_name = "trips"
    paginate_by = 30

    def get_queryset(self):
        qs = RouteTrip.objects.filter(ended_at__isnull=False).select_related(
            "route", "vehicle", "driver", "weighbridge_record", "weighbridge_record__validated_by"
        ).order_by("-ended_at")
        if self.request.GET.get("product"):
            qs = qs.filter(Q(receipts__product__code=self.request.GET["product"]) | Q(receipts__isnull=True, product__code=self.request.GET["product"])).distinct()
        return qs

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "products": CollectionProduct.objects.all()}


class WeighbridgeRecordView(RoleRequiredMixin, FormView):
    allowed_roles = WEIGHBRIDGE_ROLES
    form_class = WeighbridgeRecordForm
    template_name = "operations/weighbridge_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.trip = get_object_or_404(RouteTrip.objects.select_related("route", "vehicle", "driver"), pk=kwargs["trip_id"], ended_at__isnull=False)
        self.record = WeighbridgeRecord.objects.filter(trip=self.trip).select_related("validated_by", "created_by", "updated_by").first()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.record or WeighbridgeRecord(trip=self.trip, created_by=self.request.user, updated_by=self.request.user)}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "trip": self.trip, "record": self.record, "revisions": self.record.revisions.select_related("validated_by") if self.record else [], "received_products": list(self.trip.receipts.filter(status="CONFIRMED").order_by("product__name").values_list("product__name", flat=True).distinct())}

    def form_valid(self, form):
        try:
            self.record = save_weighbridge_draft(trip=self.trip, values={field: form.cleaned_data[field] for field in form._meta.fields}, user=self.request.user, request=self.request)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Pesaje guardado. Revise los valores y valide para incorporarlos a los informes.")
        return HttpResponseRedirect(reverse("operations:weighbridge_record", kwargs={"trip_id": self.trip.pk}))


class WeighbridgeValidateView(RoleRequiredMixin, View):
    allowed_roles = WEIGHBRIDGE_ROLES

    def post(self, request, pk):
        record = get_object_or_404(WeighbridgeRecord, pk=pk)
        try:
            validate_weighbridge(record=record, user=request.user, request=request)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Báscula validada. Los informes ya utilizan los litros reales.")
        return HttpResponseRedirect(reverse("operations:weighbridge_record", kwargs={"trip_id": record.trip_id}))


class WeighbridgeReopenView(RoleRequiredMixin, FormView):
    allowed_roles = MASTER_ROLES
    form_class = WeighbridgeCorrectionForm
    template_name = "operations/weighbridge_reopen.html"

    def dispatch(self, request, *args, **kwargs):
        self.record = get_object_or_404(WeighbridgeRecord.objects.select_related("trip", "trip__route", "trip__vehicle"), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "record": self.record}

    def form_valid(self, form):
        try:
            reopen_weighbridge(record=self.record, user=self.request.user, reason=form.cleaned_data["reason"], request=self.request)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Corrección habilitada. La validación anterior permanece en el historial.")
        return HttpResponseRedirect(reverse("operations:weighbridge_record", kwargs={"trip_id": self.record.trip_id}))


class VehicleCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = MASTER_ROLES
    model = Vehicle
    form_class = VehicleForm
    template_name = "operations/form.html"
    success_url = reverse_lazy("operations:vehicle_list")
    extra_context = {"title": "Nuevo vehículo", "cancel_url": reverse_lazy("operations:vehicle_list")}

    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.CREATE, instance=self.object, request=self.request)
        messages.success(self.request, "Vehículo creado correctamente.")
        return response


class VehicleUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = MASTER_ROLES
    model = Vehicle
    form_class = VehicleForm
    template_name = "operations/form.html"
    success_url = reverse_lazy("operations:vehicle_list")
    extra_context = {"title": "Editar vehículo", "cancel_url": reverse_lazy("operations:vehicle_list")}

    def form_valid(self, form):
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.UPDATE, instance=self.object, request=self.request)
        messages.success(self.request, "Vehículo actualizado correctamente.")
        return response


class VehicleToggleActiveView(RoleRequiredMixin, View):
    allowed_roles = MASTER_ROLES

    def post(self, request, pk):
        vehicle = get_object_or_404(Vehicle, pk=pk)
        vehicle.active = not vehicle.active
        vehicle.save(update_fields=["active", "updated_at"])
        action = AuditEvent.Action.ACTIVATE if vehicle.active else AuditEvent.Action.DEACTIVATE
        record_event(actor=request.user, action=action, instance=vehicle, request=request)
        messages.success(request, "Estado del vehículo actualizado.")
        return HttpResponseRedirect(reverse("operations:vehicle_list"))


class ReceiptListView(LoginRequiredMixin, SearchableListMixin, ListView):
    model = MilkReceipt
    template_name = "operations/receipt_list.html"
    context_object_name = "receipts"
    search_fields = (
        "internal_number",
        "producer__name",
        "producer__document_number",
        "vehicle__plate",
    )

    def get_context_data(self, **kwargs):
        from .models import CollectionProduct
        context = super().get_context_data(**kwargs)
        context["products"] = CollectionProduct.objects.all()
        return context

    def get_queryset(self):
        queryset = super().get_queryset().select_related("producer", "vehicle", "collected_by")
        product = self.request.GET.get("product", "")
        from .models import CollectionProduct
        if product and CollectionProduct.objects.filter(code=product).exists():
            queryset = queryset.filter(product__code=product)
        status = self.request.GET.get("status", "").strip()
        if status in MilkReceipt.Status.values:
            queryset = queryset.filter(status=status)
        return queryset


class DuplicateReceiptAlertsView(RoleRequiredMixin, TemplateView):
    allowed_roles = MASTER_ROLES
    template_name = "operations/duplicate_alerts.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["alerts"] = (MilkReceipt.objects.filter(trip__isnull=False, status=MilkReceipt.Status.CONFIRMED)
            .values("trip_id", "producer_id", "producer__name", "product_id", "product__name", "trip__route__name", "trip__started_at")
            .annotate(total=Count("id")).filter(total__gt=1).order_by("-total", "producer__name")[:100])
        return context


class DuplicateReceiptReviewView(RoleRequiredMixin, FormView):
    allowed_roles = MASTER_ROLES
    form_class = DuplicateReviewForm
    template_name = "operations/duplicate_review.html"

    def dispatch(self, request, *args, **kwargs):
        self.trip = get_object_or_404(RouteTrip, pk=kwargs["trip_id"])
        self.producer = get_object_or_404(Producer, pk=kwargs["producer_id"])
        return super().dispatch(request, *args, **kwargs)

    def candidate_queryset(self):
        qs = MilkReceipt.objects.filter(trip=self.trip, producer=self.producer, status=MilkReceipt.Status.CONFIRMED)
        product = self.kwargs.get("product_id")
        if product:
            return qs.filter(product_id=product)
        # Old links remain usable only for a single-product group.
        if qs.values("product_id").distinct().count() > 1:
            return qs.none()
        return qs

    def candidates(self):
        return list(self.candidate_queryset().order_by("collected_at", "pk"))

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "receipts": self.candidates()}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "trip": self.trip, "producer": self.producer, "receipts": self.candidates()}

    def form_valid(self, form):
        with transaction.atomic():
            candidates = list(self.candidate_queryset().select_for_update())
            selected = form.cleaned_data["selected_id"]
            if len(candidates) < 2 or selected not in {str(item.pk) for item in candidates}:
                form.add_error(None, "Los recibidos cambiaron. Actualice la página y revise de nuevo.")
                return self.form_invalid(form)
            for item in candidates:
                if str(item.pk) != selected:
                    void_receipt(receipt=item, user=self.request.user, reason=form.cleaned_data["reason"], request=self.request)
        messages.success(self.request, "Se conservó el recibido elegido. Los demás quedaron anulados y permanecen en el historial.")
        return HttpResponseRedirect(reverse("operations:duplicate_alerts"))


class ReceiptDetailView(LoginRequiredMixin, DetailView):
    model = MilkReceipt
    template_name = "operations/receipt_detail.html"
    context_object_name = "receipt"

    def get_queryset(self):
        return super().get_queryset().select_related("producer", "vehicle", "collected_by", "voided_by")


class ReceiptVoucherView(LoginRequiredMixin, DetailView):
    model = MilkReceipt
    template_name = "operations/receipt_voucher.html"
    context_object_name = "receipt"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "producer", "vehicle", "collected_by", "voided_by"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        paper_width = self.request.GET.get("paper", "80")
        context["paper_width"] = paper_width if paper_width in {"58", "80"} else "80"
        return context


class ReceiptCreateView(RoleRequiredMixin, FormView):
    allowed_roles = RECEIPT_ROLES
    form_class = MilkReceiptForm
    template_name = "operations/form.html"
    extra_context = {"title": "Nuevo recibido de leche", "cancel_url": reverse_lazy("operations:receipt_list")}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            receipt = create_receipt(user=self.request.user, request=self.request, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, f"Recibido {receipt.internal_number} registrado correctamente.")
        return HttpResponseRedirect(reverse("operations:receipt_detail", kwargs={"pk": receipt.pk}))


class ReceiptUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = {User.Role.ADMIN, User.Role.SUPERVISOR}
    model = MilkReceipt
    form_class = MilkReceiptForm
    template_name = "operations/form.html"
    extra_context = {"title": "Editar recibido", "cancel_url": reverse_lazy("operations:receipt_list")}

    def form_valid(self, form):
        original = MilkReceipt.objects.get(pk=self.object.pk)
        if original.producer_id != form.instance.producer_id or original.product_id != form.instance.product_id or original.collected_at != form.instance.collected_at:
            form.add_error(None, "Anule y cree un nuevo recibido para cambiar proveedor, producto o fecha; así conserva los términos de compra históricos.")
            return self.form_invalid(form)
        if self.object.status == MilkReceipt.Status.VOIDED:
            raise PermissionDenied("No se puede editar un recibido anulado.")
        if self.object.trip_id and hasattr(self.object.trip, "weighbridge_record") and self.object.trip.weighbridge_record.status == WeighbridgeRecord.Status.VALIDATED:
            raise PermissionDenied("La báscula del recorrido ya está validada. Habilite primero una corrección.")
        form.instance.collected_by = self.object.collected_by
        response = super().form_valid(form)
        record_event(actor=self.request.user, action=AuditEvent.Action.UPDATE, instance=self.object, request=self.request)
        messages.success(self.request, "Recibido actualizado correctamente.")
        return response

    def get_success_url(self):
        return reverse("operations:receipt_detail", kwargs={"pk": self.object.pk})


class ReceiptVoidView(RoleRequiredMixin, FormView):
    allowed_roles = {User.Role.ADMIN, User.Role.SUPERVISOR}
    form_class = VoidReasonForm
    template_name = "operations/void_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.receipt = get_object_or_404(MilkReceipt, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"title": "Anular recibido", "object": self.receipt})
        return context

    def form_valid(self, form):
        try:
            void_receipt(
                receipt=self.receipt,
                user=self.request.user,
                reason=form.cleaned_data["reason"],
                request=self.request,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Recibido anulado con trazabilidad.")
        return HttpResponseRedirect(reverse("operations:receipt_detail", kwargs={"pk": self.receipt.pk}))
