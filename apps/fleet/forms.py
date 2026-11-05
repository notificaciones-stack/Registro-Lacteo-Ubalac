import uuid
from django import forms
from .models import FatigueSurvey, FuelEntry
from .services import visible_trips


class FleetForm(forms.ModelForm):
    external_id = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['trip'].queryset = visible_trips(user)
        self.fields['trip'].label = 'Recorrido (conductor, vehículo y ruta vinculados)'


class FuelForm(FleetForm):
    fuel_photo = forms.FileField(label='Foto del tanqueo', widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}))
    invoice_photo = forms.FileField(label='Foto de la factura', widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}))
    class Meta:
        model = FuelEntry
        fields = ['external_id', 'trip', 'fueled_at', 'gallons', 'total_price', 'odometer_km', 'full_tank', 'observations']
        widgets = {'fueled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'), 'observations': forms.Textarea(attrs={'rows': 3})}


class FuelAdjustmentForm(forms.ModelForm):
    class Meta:
        model = FuelEntry
        fields = ['gallons', 'total_price']
        labels = {
            'gallons': 'Galones tanqueados',
            'total_price': 'Valor total de la factura (COP)',
        }
        widgets = {
            'gallons': forms.NumberInput(attrs={'step': '0.001', 'min': '0.001'}),
            'total_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
        }


class FatigueForm(FleetForm):
    expected_cycle = forms.CharField(required=False, widget=forms.HiddenInput)
    commitment = forms.BooleanField(label='Me comprometo a informar la fatiga y no iniciar o continuar conduciendo hasta su evaluación y medidas seguras.')
    class Meta:
        model = FatigueSurvey
        fields = ['external_id', 'trip', 'sleep_hours', 'sleepy', 'rested', 'fatigue', 'observations', 'commitment']
        widgets = {key: forms.RadioSelect(choices=[(True, 'Sí'), (False, 'No')]) for key in ['sleepy', 'rested', 'fatigue']}


class ReportFilter(forms.Form):
    date_from = forms.DateField(label='Desde', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(label='Hasta', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    vehicle = forms.ChoiceField(label='Vehículo', required=False)
    driver = forms.ChoiceField(label='Conductor', required=False)
    route = forms.ChoiceField(label='Ruta', required=False)
    group = forms.ChoiceField(label='Agrupar', choices=[('day', 'Día'), ('week', 'Semana'), ('month', 'Mes')], required=False)
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        trips = visible_trips(user)
        for field, label in [('vehicle', 'vehicle__plate'), ('driver', 'driver__username'), ('route', 'route__name')]:
            pairs = trips.order_by(label).values_list(field, label).distinct()
            self.fields[field].choices = [('', 'Todos')] + [(str(pk), name) for pk, name in pairs]
    def clean(self):
        data = super().clean()
        if data.get('date_from') and data.get('date_to') and data['date_from'] > data['date_to']:
            raise forms.ValidationError('Desde no puede ser posterior a Hasta.')
        return data
