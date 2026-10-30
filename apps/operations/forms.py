from __future__ import annotations

from decimal import Decimal
import json

from django import forms
from django.contrib.auth.password_validation import CommonPasswordValidator, MinimumLengthValidator, NumericPasswordValidator, UserAttributeSimilarityValidator, validate_password
from django.db import models
from django.utils import timezone

from apps.accounts.models import User
from .models import CollectionProduct, FiscalParameter, ProducerProduct, DriverProfile, MilkReceipt, Producer, Route, RouteTrip, RouteSchedule, Vehicle, VehicleInspection, WeighbridgeRecord
from .assignments import assigned_routes, assigned_vehicles


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                css_class = "assignment-checkboxes"
            elif isinstance(field.widget, forms.Select):
                css_class = "form-select"
            field.widget.attrs.setdefault("class", css_class)


class ProducerForm(StyledModelForm):
    class Media:
        js = ("js/producer-form.js", "js/assignment-defaults.js")

    products = forms.ModelMultipleChoiceField(label="Productos que entrega", queryset=CollectionProduct.objects.filter(active=True), widget=forms.CheckboxSelectMultiple)
    deductions = forms.ModelMultipleChoiceField(label="Retenciones e impuestos", queryset=FiscalParameter.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .assignment_defaults import assignment_catalog
        self.fields["assigned_driver"].queryset = User.objects.filter(is_active=True, role__in=[User.Role.DRIVER, User.Role.COLLECTOR])
        self.fields["assigned_route"].queryset = Route.objects.filter(active=True)
        self.fields["assigned_vehicle"].queryset = Vehicle.objects.filter(active=True)
        self.fields["assigned_driver"].widget.attrs["data-assignments"] = json.dumps(assignment_catalog())
        self.fields["assigned_driver"].help_text = "Se completan las opciones únicas. Si hay varias rutas o placas, elija la correspondiente."
        self.fields["document_type"].required = False
        self.fields["document_number"].required = False
        self.can_set_fiscal = user is None or user.is_superuser or user.role == User.Role.ADMIN
        if not self.can_set_fiscal:
            self.fields.pop("deductions")
        if self.instance.pk and not self.instance._state.adding:
            self.initial["products"] = self.instance.products.all()
        else:
            self.initial["products"] = CollectionProduct.objects.filter(code="leche")
        for product in CollectionProduct.objects.filter(active=True):
            value = self.instance.product_prices.filter(product=product).first() if self.instance.pk and not self.instance._state.adding else None
            self.fields[f"price_{product.pk}"] = forms.DecimalField(label=f"{product.name} · precio de compra por litro (COP)", required=False, min_value=0, max_digits=14, decimal_places=2, initial=value.unit_price if value else None, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}))

    def clean(self):
        values = super().clean()
        for product in values.get("products", []):
            if values.get(f"price_{product.pk}") is None:
                self.add_error(f"price_{product.pk}", "Defina el precio para este producto seleccionado.")
        if self.can_set_fiscal:
            total = sum(p.rate for p in values.get("deductions", []) if p.kind == "WITHHOLDING" and p.active)
            if total > 100:
                self.add_error("deductions", "Los descuentos no pueden superar el 100 %.")
        return values

    def _save_m2m(self):
        # The through model retains independent prices for every product.
        selected = self.cleaned_data.get("products", [])
        self.instance.product_prices.exclude(product__in=selected).delete()
        for product in selected:
            ProducerProduct.objects.update_or_create(producer=self.instance, product=product, defaults={"unit_price": self.cleaned_data[f"price_{product.pk}"]})
        if self.can_set_fiscal:
            self.instance.deductions.set(self.cleaned_data.get("deductions", []))
        from .services.pricing import snapshot_terms
        snapshot_terms(self.instance)

    class Meta:
        model = Producer
        fields = ["fiscal_category", "document_type", "document_number", "name", "farm_name", "phone", "municipality", "village", "notes", "assigned_driver", "assigned_route", "assigned_vehicle", "products", "deductions"]
        labels = {
            "assigned_driver": "Conductor asignado",
            "assigned_route": "Ruta asignada",
            "assigned_vehicle": "Placa asignada",
            "fiscal_category": "Clasificación del proveedor",
            "document_type": "Tipo de documento",
            "document_number": "Número de documento",
            "name": "Nombre o razón social",
            "farm_name": "Nombre de la finca",
            "phone": "Teléfono",
            "municipality": "Municipio",
            "village": "Vereda",
            "notes": "Observaciones",
        }


class RouteForm(StyledModelForm):
    class Meta:
        model = Route
        fields = ["name", "description"]
        labels = {"name": "Nombre de la ruta", "description": "Descripción"}


class ProductForm(StyledModelForm):
    class Meta:
        model = CollectionProduct
        fields = ["code", "name", "active"]
        labels = {"code": "Código único", "name": "Nombre del producto", "active": "Activo"}


class FiscalParameterForm(StyledModelForm):
    def clean(self):
        values = super().clean()
        if values.get("kind") == "WITHHOLDING" and values.get("active") and values.get("rate") is not None and not self.instance._state.adding:
            for producer in self.instance.producers.all():
                total = sum((p.rate for p in producer.deductions.exclude(pk=self.instance.pk).filter(active=True, kind="WITHHOLDING")), Decimal("0")) + values["rate"]
                if total > 100:
                    raise forms.ValidationError(f"Los descuentos de {producer.name} superarían 100 %.")
        return values
    class Meta:
        model = FiscalParameter
        fields = ["name", "kind", "rate", "description", "active"]
        labels = {"name": "Nombre", "kind": "Tipo de ajuste", "rate": "Porcentaje sobre el valor bruto", "description": "Descripción", "active": "Activo"}


class VehicleInspectionForm(StyledModelForm):
    class Meta:
        model = VehicleInspection
        fields = ["vehicle", "odometer_km", "brakes", "tires", "lights", "fluids", "tank_hygiene", "documents", "safety_kit", "observations", "safe_to_operate"]
        labels = {"vehicle": "Vehículo", "odometer_km": "Kilometraje", "brakes": "Frenos", "tires": "Llantas", "lights": "Luces", "fluids": "Niveles de fluidos", "tank_hygiene": "Higiene del tanque", "documents": "Documentación vigente", "safety_kit": "Equipo de carretera", "observations": "Novedades", "safe_to_operate": "Declaro que el vehículo es apto para operar"}


class VehicleForm(StyledModelForm):
    class Media:
        js = ("js/assignment-defaults.js",)

    def clean(self):
        values = super().clean()
        driver = values.get("driver")
        if driver:
            profile = getattr(driver, "driver_profile", None)
            values["driver_name"] = driver.get_full_name() or driver.username
            values["driver_document"] = profile.document_number if profile else ""
            values["driver_phone"] = profile.phone if profile else ""
            if not values.get("route"):
                routes = assigned_routes(driver)
                if routes.count() == 1:
                    values["route"] = routes.first()
        return values

    class Meta:
        model = Vehicle
        fields = ["plate", "route", "name", "driver", "driver_name", "driver_document", "driver_phone", "capacity_liters", "notes"]
        labels = {
            "plate": "Placa",
            "name": "Nombre o referencia",
            "capacity_liters": "Capacidad en litros",
            "route": "Ruta",
            "driver_name": "Nombre del conductor",
            "driver": "Usuario conductor asignado",
            "driver_document": "Documento del conductor",
            "driver_phone": "Teléfono del conductor",
            "notes": "Observaciones",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["route"].queryset = Route.objects.filter(active=True)
        self.fields["driver"].queryset = User.objects.filter(is_active=True, role__in=[User.Role.DRIVER, User.Role.COLLECTOR])
        from .assignment_defaults import assignment_catalog
        self.fields["driver"].widget.attrs["data-assignments"] = json.dumps(assignment_catalog())


class RouteScheduleForm(StyledModelForm):
    change_reason = forms.CharField(label="Motivo del ajuste", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}), help_text="Obligatorio cuando modifica una programación ya creada.")

    class Meta:
        model = RouteSchedule
        fields = ["scheduled_date", "shift", "collection_type", "driver", "route", "vehicle", "producers", "status", "notes"]
        labels = {
            "scheduled_date": "Fecha programada", "shift": "Turno", "collection_type": "Tipo de recolección",
            "driver": "Conductor", "route": "Ruta", "vehicle": "Placa / vehículo",
            "producers": "Productores programados", "status": "Estado", "notes": "Observaciones",
        }
        widgets = {
            "scheduled_date": forms.DateInput(attrs={"type": "date"}),
            "producers": forms.CheckboxSelectMultiple(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["driver"].queryset = User.objects.filter(is_active=True, role__in=[User.Role.DRIVER, User.Role.COLLECTOR])
        self.fields["route"].queryset = Route.objects.filter(active=True)
        self.fields["vehicle"].queryset = Vehicle.objects.filter(active=True)
        self.fields["producers"].queryset = Producer.objects.filter(active=True).select_related("assigned_route").order_by("name")
        if not self.is_bound and not self.instance.pk:
            self.initial["scheduled_date"] = timezone.localdate()

    def clean(self):
        values = super().clean()
        if self.instance.pk and not (values.get("change_reason") or "").strip():
            self.add_error("change_reason", "Indique el motivo de la modificación para conservar el historial.")
        return values


class StartTripForm(forms.Form):
    product = forms.ModelChoiceField(label="Producto a recoger", queryset=CollectionProduct.objects.filter(active=True), widget=forms.Select(attrs={"class": "form-select"}))
    inspection = forms.ModelChoiceField(label="Inspección vehicular del día", required=False, queryset=VehicleInspection.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))
    route = forms.ModelChoiceField(label="Ruta", queryset=Route.objects.filter(active=True), widget=forms.Select(attrs={"class": "form-select"}))
    vehicle = forms.ModelChoiceField(label="Vehículo", queryset=Vehicle.objects.filter(active=True), widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not (user.is_superuser or user.role in {User.Role.ADMIN, User.Role.SUPERVISOR}):
            self.fields["inspection"].required = True
            self.fields["inspection"].queryset = VehicleInspection.objects.filter(driver=user, inspected_on=timezone.localdate(), safe_to_operate=True)
            if hasattr(user, "driver_profile") and user.driver_profile.products.exists():
                self.fields["product"].queryset = user.driver_profile.products.filter(active=True)
            self.fields["vehicle"].queryset = Vehicle.objects.filter(active=True, driver=user)
            self.fields["route"].queryset = assigned_routes(user)


class TripReopenForm(forms.Form):
    reason = forms.CharField(label="Motivo de reapertura", min_length=8, max_length=500, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))


class WeighbridgeRecordForm(StyledModelForm):
    class Meta:
        model = WeighbridgeRecord
        fields = ["weighed_at", "scale_ticket", "gross_weight_kg", "tare_weight_kg", "density_kg_l", "tolerance_percent", "laboratory_notes"]
        labels = {
            "weighed_at": "Fecha y hora del pesaje",
            "scale_ticket": "Número de tiquete de báscula",
            "gross_weight_kg": "Peso bruto (kg)",
            "tare_weight_kg": "Tara del vehículo (kg)",
            "density_kg_l": "Densidad del producto (kg/L)",
            "tolerance_percent": "Tolerancia permitida (%)",
            "laboratory_notes": "Observaciones de laboratorio",
        }
        help_texts = {
            "density_kg_l": "Use la densidad medida por laboratorio. Valor inicial: 1,0300 kg/L.",
            "tolerance_percent": "La diferencia dentro de este porcentaje se considera en tolerancia.",
        }
        widgets = {
            "weighed_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "gross_weight_kg": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "tare_weight_kg": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "density_kg_l": forms.NumberInput(attrs={"step": "0.0001", "min": "0.9000", "max": "1.2000"}),
            "tolerance_percent": forms.NumberInput(attrs={"step": "0.001", "min": "0", "max": "100"}),
            "laboratory_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["weighed_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        if not self.is_bound and not self.instance.pk:
            self.initial["weighed_at"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        values = super().clean()
        gross = values.get("gross_weight_kg")
        tare = values.get("tare_weight_kg")
        density = values.get("density_kg_l")
        if gross is not None and tare is not None and gross <= tare:
            self.add_error("gross_weight_kg", "El peso bruto debe ser mayor que la tara.")
        if density is not None and not (Decimal("0.9000") <= density <= Decimal("1.2000")):
            self.add_error("density_kg_l", "La densidad debe estar entre 0,9000 y 1,2000 kg/L.")
        return values


class WeighbridgeCorrectionForm(forms.Form):
    reason = forms.CharField(label="Motivo de corrección", min_length=8, max_length=500, widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}))


class DuplicateReviewForm(forms.Form):
    selected_id = forms.ChoiceField(label="Recibido válido", widget=forms.RadioSelect)
    reason = forms.CharField(label="Motivo de anulación de los demás", min_length=8, max_length=500, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))

    def __init__(self, *args, receipts=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selected_id"].choices = [(str(item.pk), f"{item.internal_number} · {item.liters} L · {timezone.localtime(item.collected_at):%H:%M} · {item.observations[:70]}") for item in receipts]


class DriverConfigurationForm(StyledModelForm):
    first_name = forms.CharField(label="Nombre", max_length=150, required=False)
    last_name = forms.CharField(label="Apellidos", max_length=150, required=False)
    username = forms.CharField(label="Usuario de acceso", max_length=150)
    email = forms.EmailField(label="Correo", required=False)
    vehicles = forms.ModelMultipleChoiceField(label="Placas asignadas", queryset=Vehicle.objects.none(), required=False, widget=forms.CheckboxSelectMultiple(attrs={"class": "assignment-checkboxes"}), help_text="Cada vehículo solo puede estar asignado a un conductor.")

    class Meta:
        model = DriverProfile
        fields = ["first_name", "last_name", "username", "email", "document_number", "phone", "device_id", "routes", "vehicles", "producers", "products"]
        labels = {"document_number": "Documento", "phone": "Teléfono", "device_id": "ID del equipo móvil", "routes": "Rutas asignadas", "producers": "Productores asignados (vacío = disponibles por ruta y conductor)"}
        widgets = {"products": forms.CheckboxSelectMultiple(attrs={"class": "assignment-checkboxes"}), "routes": forms.CheckboxSelectMultiple(attrs={"class": "assignment-checkboxes"}), "producers": forms.CheckboxSelectMultiple(attrs={"class": "assignment-checkboxes"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance.user
        self.fields["products"].label = "Productos que recoge (vacío = todos los activos)"
        self.fields["products"].queryset = CollectionProduct.objects.filter(active=True)
        self.fields["routes"].queryset = Route.objects.filter(active=True)
        self.fields["producers"].queryset = Producer.objects.filter(active=True)
        self.fields["vehicles"].queryset = Vehicle.objects.filter(active=True).filter(
            models.Q(driver__isnull=True) | models.Q(driver=user)
        )
        self.initial.update(first_name=user.first_name, last_name=user.last_name, username=user.username, email=user.email)
        self.initial["vehicles"] = list(Vehicle.objects.filter(driver=user).values_list("pk", flat=True))
        if not self.instance.pk:
            self.initial["routes"] = list(assigned_routes(user).values_list("pk", flat=True))

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.user_id).exists():
            raise forms.ValidationError("Ya existe un usuario con este nombre.")
        return username

    def clean(self):
        values = super().clean()
        previous_routes = self.instance.routes if self.instance.pk else assigned_routes(self.instance.user)
        removed_routes = set(previous_routes.values_list("pk", flat=True)) - set(values.get("routes", []).values_list("pk", flat=True)) if "routes" in values else set()
        removed_vehicles = set(Vehicle.objects.filter(driver=self.instance.user).values_list("pk", flat=True)) - set(values.get("vehicles", []).values_list("pk", flat=True)) if "vehicles" in values else set()
        if RouteTrip.objects.filter(driver=self.instance.user, ended_at__isnull=True).filter(models.Q(route_id__in=removed_routes) | models.Q(vehicle_id__in=removed_vehicles)).exists():
            raise forms.ValidationError("Cierre el recorrido abierto antes de quitar su ruta o placa.")
        return values


class DriverCreateForm(DriverConfigurationForm):
    password1 = forms.CharField(label="Contraseña inicial", min_length=6, widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}))
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}))

    def clean(self):
        values = super().clean()
        password = values.get("password1")
        if password and values.get("password2") and password != values["password2"]:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if password:
            user = self.instance.user
            user.username = values.get("username", "")
            user.first_name = values.get("first_name", "")
            user.last_name = values.get("last_name", "")
            try:
                validate_driver_password(password, user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return values


class DriverPasswordResetForm(forms.Form):
    password1 = forms.CharField(label="Nueva contraseña", min_length=6, widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        values = super().clean()
        password = values.get("password1")
        if password and values.get("password2") and password != values["password2"]:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if password:
            try:
                validate_driver_password(password, self.user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return values


class DriverModuleUnlockForm(forms.Form):
    password = forms.CharField(label="Clave del módulo de conductores", widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}))


def validate_driver_password(password, user):
    validate_password(password, user=user, password_validators=[
        MinimumLengthValidator(min_length=6),
        UserAttributeSimilarityValidator(),
        CommonPasswordValidator(),
        NumericPasswordValidator(),
    ])


class MilkReceiptForm(StyledModelForm):
    class Media:
        js = ("js/assignment-defaults.js",)

    product = forms.ModelChoiceField(label="Producto", queryset=CollectionProduct.objects.filter(active=True), required=False)

    def clean_product(self):
        from .models import default_product
        product = self.cleaned_data.get("product") or CollectionProduct.objects.filter(pk=default_product(), active=True).first()
        if product is None:
            raise forms.ValidationError("Seleccione un producto activo del catálogo.")
        return product
    class Meta:
        model = MilkReceipt
        fields = ["producer", "product", "vehicle", "route", "collected_at", "liters", "collection_shift", "support_type", "payment_method", "support_number", "observations"]
        labels = {
            "producer": "Productor",
            "vehicle": "Vehículo",
            "collected_at": "Fecha y hora de recolección",
            "liters": "Litros recibidos",
            "route": "Ruta",
            "collection_shift": "Jornada (AM/PM)",
            "support_type": "Tipo de soporte",
            "payment_method": "Medio de pago (referencia informativa)",
            "support_number": "Número de soporte",
            "observations": "Observaciones",
        }
        widgets = {
            "collected_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "observations": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .assignments import assigned_producers

        self.fields["producer"].queryset = assigned_producers(user) if user else Producer.objects.filter(active=True)
        self.fields["product"].queryset = CollectionProduct.objects.filter(active=True)
        self.fields["product"].label = "Producto recibido"
        self.fields["producer"].widget.attrs["data-producers"] = json.dumps([{"id": str(p.pk), "route": str(p.assigned_route_id or ""), "vehicle": str(p.assigned_vehicle_id or "")} for p in self.fields["producer"].queryset])
        self.fields["vehicle"].queryset = assigned_vehicles(user) if user else Vehicle.objects.filter(active=True)
        self.fields["route"].queryset = assigned_routes(user) if user else Route.objects.filter(active=True)
        self.fields["collected_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        if not self.is_bound and not self.instance.pk:
            self.initial["collected_at"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")


class VoidReasonForm(forms.Form):
    reason = forms.CharField(
        label="Motivo",
        max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )


class ImportWorkbookForm(forms.Form):
    file = forms.FileField(label="Archivo Excel (.xlsx)", widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".xlsx"}))

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith(".xlsx") or file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Use un archivo .xlsx de hasta 5 MB.")
        return file
