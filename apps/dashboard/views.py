from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseBadRequest
from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Sum, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.generic import TemplateView, View

from apps.operations.models import MilkReceipt, Producer, RouteTrip, Vehicle, WeighbridgeRecord
from .forms import ReportFilterForm
from .reports import export_report, report_data


def default_report_dates():
    today = timezone.localdate()
    return {"date_from": today.replace(day=1).isoformat(), "date_to": today.isoformat()}


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        effective = Case(
            When(trip__weighbridge_record__status=WeighbridgeRecord.Status.VALIDATED,
                 then=ExpressionWrapper(F("liters") * F("trip__weighbridge_record__allocation_factor"), output_field=DecimalField(max_digits=18, decimal_places=8))),
            default=F("liters"), output_field=DecimalField(max_digits=18, decimal_places=8),
        )
        receipts = MilkReceipt.objects.filter(status=MilkReceipt.Status.CONFIRMED).annotate(effective_liters=effective)
        from apps.operations.models import CollectionProduct
        product_id = self.request.GET.get("product")
        products = CollectionProduct.objects.all()
        from django.core.exceptions import ValidationError
        try:
            selected = products.filter(pk=product_id).first() if product_id else None
            selected_producer = Producer.objects.filter(pk=self.request.GET.get("producer")).first() if self.request.GET.get("producer") else None
        except ValidationError:
            selected, selected_producer = None, None
        if selected:
            receipts = receipts.filter(product=selected)
        if selected_producer:
            receipts = receipts.filter(producer=selected_producer)
        context.update(products=products, selected_product=selected, producers=Producer.objects.all(), selected_producer=selected_producer)
        today_receipts = receipts.filter(collected_at__date=today)
        month_receipts = receipts.filter(collected_at__year=today.year, collected_at__month=today.month)
        from apps.operations.services.pricing import financial_summary
        context.update(financial_summary(month_receipts.select_related("producer", "product").iterator()))
        context.update(
            {
                "today_liters": today_receipts.aggregate(total=Coalesce(Sum("effective_liters"), Decimal("0")))["total"],
                "today": today,
                "today_receipts": today_receipts.count(),
                "month_liters": month_receipts.aggregate(total=Coalesce(Sum("effective_liters"), Decimal("0")))["total"],
                "month_receipts_count": month_receipts.count(),
                "active_producers": Producer.objects.filter(active=True).count(),
                "active_vehicles": Vehicle.objects.filter(active=True).count(),
                "trips_closed_today": RouteTrip.objects.filter(ended_at__date=today).count(),
                "trips_open": RouteTrip.objects.filter(ended_at__isnull=True).count(),
                "recent_trips": RouteTrip.objects.select_related("route", "vehicle", "driver").order_by("-started_at")[:5],
                "recent_receipts": receipts.select_related("producer", "vehicle")[:8],
                "vehicle_summary": month_receipts.values("vehicle__plate")
                .annotate(total_liters=Sum("effective_liters"), receipt_count=Count("id"))
                .order_by("-total_liters")[:8],
            }
        )
        return context


class ReportView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/reports.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = ReportFilterForm(self.request.GET if self.request.GET else default_report_dates())
        context["form"] = form
        context["today"] = timezone.localdate()
        if form.is_valid():
            context.update(report_data(form.cleaned_data))
            context["start"] = form.cleaned_data["start"]
            context["end"] = form.cleaned_data["end"]
            context["query_string"] = self.request.GET.urlencode()
        return context


class ReportExportView(LoginRequiredMixin, View):
    def get(self, request):
        form = ReportFilterForm(request.GET if request.GET else default_report_dates())
        if not form.is_valid():
            return HttpResponseBadRequest("Filtros inválidos. Revise el informe antes de descargar.")
        try:
            return export_report(form.cleaned_data)
        except ValueError as exc:
            return HttpResponseBadRequest(str(exc))
