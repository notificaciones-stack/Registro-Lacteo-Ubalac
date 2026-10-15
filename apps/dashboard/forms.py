from django import forms
from django.db.models import Q

from apps.accounts.models import User
from apps.operations.models import CollectionProduct, MilkReceipt, Producer, Route, Vehicle


class ReportFilterForm(forms.Form):
    product = forms.ModelChoiceField(label="Producto", required=False, queryset=CollectionProduct.objects.all(), widget=forms.Select(attrs={"class": "form-select"}))
    date_from = forms.DateField(label="Desde", widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"))
    date_to = forms.DateField(label="Hasta", widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"))
    producer = forms.ModelChoiceField(label="Productor", required=False, queryset=Producer.objects.all(), widget=forms.Select(attrs={"class": "form-select"}))
    route = forms.ModelChoiceField(label="Ruta", required=False, queryset=Route.objects.all(), widget=forms.Select(attrs={"class": "form-select"}))
    vehicle = forms.ModelChoiceField(label="Vehículo", required=False, queryset=Vehicle.objects.all(), widget=forms.Select(attrs={"class": "form-select"}))
    driver = forms.ModelChoiceField(label="Conductor", required=False, queryset=User.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))
    status = forms.ChoiceField(label="Estado", required=False, choices=[("", "Solo confirmados"), ("VOIDED", "Solo anulados"), ("ALL", "Todos los estados")], widget=forms.Select(attrs={"class": "form-select"}))
    shift = forms.ChoiceField(label="Jornada", required=False, choices=[("", "Todas"), ("AM", "AM"), ("PM", "PM")], widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["driver"].queryset = User.objects.filter(Q(role__in=[User.Role.DRIVER, User.Role.COLLECTOR]) | Q(route_trips__isnull=False)).distinct().order_by("username")

    def clean(self):
        values = super().clean()
        start, end = values.get("date_from"), values.get("date_to")
        if start and end:
            if start > end:
                raise forms.ValidationError("La fecha inicial debe ser anterior a la fecha final.")
            if (end - start).days > 3660:
                raise forms.ValidationError("Seleccione un periodo de máximo 10 años.")
            values["start"] = start
            values["end"] = end
        return values
