from collections import defaultdict
from decimal import Decimal
from datetime import timedelta
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, TemplateView, View, UpdateView
from django.core.paginator import Paginator
from apps.accounts.mixins import RoleRequiredMixin
from apps.operations.services.trips import close_trip
from .models import FatigueSurvey, FuelEntry
from .forms import FuelForm, FuelAdjustmentForm, FatigueForm, ReportFilter
from .services import STAFF, WRITERS, visible_trips, save_record, efficiency, cycle_for


class RecordCreate(RoleRequiredMixin, FormView):
    allowed_roles = WRITERS
    template_name = 'fleet/form.html'
    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'user': self.request.user}
    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get('trip'):
            trip = get_object_or_404(visible_trips(self.request.user), pk=self.request.GET['trip'])
            initial.update(trip=trip, expected_cycle=cycle_for(trip))
        return initial
    def form_valid(self, form):
        try:
            with transaction.atomic():
                item = save_record(self.model, form.cleaned_data, self.request.user, self.request)
                if self.model is FatigueSurvey and self.request.POST.get('close_trip') == 'yes' and not item.trip.ended_at:
                    if item.cycle != cycle_for(item.trip):
                        raise ValidationError('El recorrido fue reabierto. Abra la encuesta desde el botón Cerrar del recorrido para actualizarla.')
                    close_trip(trip=item.trip, user=self.request.user, request=self.request)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, 'Registro guardado correctamente.')
        return super().form_valid(form)


class FuelCreate(RecordCreate):
    model, form_class = FuelEntry, FuelForm
    success_url = reverse_lazy('fleet:fuel')
    extra_context = {'title': 'Registrar tanqueo', 'icon': 'fuel', 'tone': 'green', 'hint': 'El conductor, la placa y la ruta se toman del recorrido. Adjunte ambas fotos (máximo 4 MB cada una).'}


class FuelUpdate(RoleRequiredMixin, UpdateView):
    model = FuelEntry
    form_class = FuelAdjustmentForm
    template_name = 'fleet/form.html'
    success_url = reverse_lazy('fleet:fuel')
    allowed_roles = {'ADMIN', 'SUPERVISOR'}
    extra_context = {
        'title': 'Ajustar tanqueo',
        'icon': 'fuel',
        'tone': 'amber',
        'hint': 'Solo se permite modificar los galones tanqueados y el valor total de la factura. El resto del registro permanece bloqueado.',
        'is_fuel_adjustment': True,
    }

    def get_queryset(self):
        return FuelEntry.objects.filter(trip__in=visible_trips(self.request.user)).defer('fuel_photo', 'invoice_photo')

    def form_valid(self, form):
        from apps.auditlog.models import AuditEvent
        from apps.auditlog.services import record_event

        with transaction.atomic():
            current = FuelEntry.objects.select_for_update().defer('fuel_photo', 'invoice_photo').get(pk=self.object.pk)
            changes = {}
            for field in ('gallons', 'total_price'):
                old_value = getattr(current, field)
                new_value = form.cleaned_data[field]
                if old_value != new_value:
                    changes[field] = {'before': str(old_value), 'after': str(new_value)}
                    setattr(current, field, new_value)
            current.full_clean()
            current.save(update_fields=['gallons', 'total_price', 'updated_at'])
            self.object = current
            if changes:
                record_event(actor=self.request.user, action=AuditEvent.Action.UPDATE, instance=current, changes=changes, request=self.request)
        messages.success(self.request, 'Tanqueo actualizado correctamente.')
        return redirect(self.success_url)


class FatigueCreate(RecordCreate):
    model, form_class = FatigueSurvey, FatigueForm
    success_url = reverse_lazy('fleet:fatigue')
    extra_context = {'title': 'Encuesta diaria de fatiga y cansancio · cierre del turno', 'icon': 'fatigue', 'tone': 'amber', 'hint': 'Identifique condiciones de fatiga al finalizar su jornada. Si presenta somnolencia, informe al responsable antes de continuar conduciendo.', 'is_fatigue': True}


class FleetReport(RoleRequiredMixin, TemplateView):
    allowed_roles = STAFF | WRITERS
    template_name = 'fleet/report.html'
    model = FuelEntry
    def records(self):
        self.filter = ReportFilter(self.request.GET, user=self.request.user)
        qs = self.model.objects.filter(trip__in=visible_trips(self.request.user)).select_related('trip__vehicle', 'trip__route', 'trip__driver')
        if self.model is FuelEntry:
            qs = qs.defer('fuel_photo', 'invoice_photo')
        if not self.filter.is_valid():
            return qs.none()
        data = self.filter.cleaned_data
        for name in ('driver', 'vehicle', 'route'):
            if data.get(name):
                qs = qs.filter(**{f'trip__{name}_id': data[name]})
        date = 'fueled_at' if self.model is FuelEntry else 'created_at'
        if data.get('date_from'):
            qs = qs.filter(**{f'{date}__date__gte': data['date_from']})
        if data.get('date_to'):
            qs = qs.filter(**{f'{date}__date__lte': data['date_to']})
        return qs
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.records()
        page = Paginator(qs, 25).get_page(self.request.GET.get('page'))
        context.update(filter=self.filter, page_obj=page, records=page, is_fatigue=self.model is FatigueSurvey)
        query = self.request.GET.copy(); query.pop('page', None)
        context['filter_query'] = query.urlencode()
        if self.model is FatigueSurvey:
            return context
        context['totals'] = qs.aggregate(gallons=Sum('gallons'), cost=Sum('total_price'))
        groups = defaultdict(lambda: {'gallons': Decimal(0), 'cost': Decimal(0)})
        grouping = self.filter.cleaned_data.get('group') or 'day'
        for item in qs:
            date = timezone.localdate(item.fueled_at)
            if grouping == 'week': date -= timedelta(days=date.weekday())
            if grouping == 'month': date = date.replace(day=1)
            groups[date]['gallons'] += item.gallons
            groups[date]['cost'] += item.total_price
        context['chart'] = [(d, v) for d, v in sorted(groups.items())]
        context['max_cost'] = max((v['cost'] for v in groups.values()), default=1) or 1
        context['max_gallons'] = max((v['gallons'] for v in groups.values()), default=1) or 1
        context['vehicles'] = qs.values('trip__vehicle__plate').annotate(gallons=Sum('gallons'), cost=Sum('total_price')).order_by('trip__vehicle__plate')
        context['drivers'] = qs.values('trip__driver__username').annotate(gallons=Sum('gallons'), cost=Sum('total_price')).order_by('trip__driver__username')
        for item in page:
            item.km_per_gallon = efficiency(item)
        query = self.request.GET.copy()
        query.pop('page', None)
        context['filter_query'] = query.urlencode()
        return context


class FatigueReport(FleetReport):
    model = FatigueSurvey


class FuelPhoto(RoleRequiredMixin, View):
    allowed_roles = STAFF | WRITERS
    def get(self, request, pk, kind):
        item = get_object_or_404(FuelEntry, pk=pk, trip__in=visible_trips(request.user))
        if kind not in {'fuel', 'invoice'}:
            from django.http import Http404
            raise Http404
        response = HttpResponse(bytes(getattr(item, kind + '_photo')), content_type='image/jpeg')
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class FuelExport(FleetReport):
    def get(self, request):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = 'Tanqueos'
        ws.append(['Fecha', 'Conductor', 'Placa', 'Ruta', 'Galones US', 'Valor COP', 'Kilometraje', 'Tanque lleno'])
        for row in self.records():
            values = [timezone.localtime(row.fueled_at).strftime('%Y-%m-%d %H:%M'), str(row.trip.driver), row.trip.vehicle.plate, row.trip.route.name, row.gallons, row.total_price, row.odometer_km, 'Sí' if row.full_tank else 'No']
            ws.append(["'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for v in values])
        ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="tanqueos.xlsx"'
        wb.save(response)
        return response
