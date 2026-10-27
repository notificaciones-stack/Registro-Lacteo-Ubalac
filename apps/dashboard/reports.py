from collections import defaultdict
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Q, Sum, When
from django.db.models.functions import TruncDate
from django.utils import timezone
from openpyxl import Workbook

from apps.operations.models import MilkReceipt, RouteTrip, WeighbridgeRecord
from apps.operations.services.bulk import make_sheet, workbook_response


def filtered_data(filters):
    effective = Case(
        When(trip__weighbridge_record__status=WeighbridgeRecord.Status.VALIDATED,
             then=ExpressionWrapper(F("liters") * F("trip__weighbridge_record__allocation_factor"), output_field=DecimalField(max_digits=18, decimal_places=8))),
        default=F("liters"), output_field=DecimalField(max_digits=18, decimal_places=8),
    )
    receipts = MilkReceipt.objects.select_related("producer", "route", "vehicle", "trip", "trip__driver", "trip__weighbridge_record").annotate(effective_liters=effective).filter(collected_at__date__gte=filters["start"], collected_at__date__lte=filters["end"])
    # Closed trips belong to the day they ended; overnight trips are visible
    # immediately after closing. Open trips use their start day.
    trips = RouteTrip.objects.select_related("route", "vehicle", "driver").filter(
        Q(ended_at__date__range=(filters["start"], filters["end"]))
        | Q(ended_at__isnull=True, started_at__date__range=(filters["start"], filters["end"]))
    )
    for key in ("route", "vehicle"):
        if filters.get(key):
            receipts = receipts.filter(**{key: filters[key]})
            trips = trips.filter(**{key: filters[key]})
    if filters.get("product"):
        receipts = receipts.filter(product=filters["product"])
        trips = trips.filter(Q(receipts__product=filters["product"]) | Q(receipts__isnull=True, product=filters["product"])).distinct()
    if filters.get("producer"):
        receipts = receipts.filter(producer=filters["producer"])
        trips = trips.filter(receipts__producer=filters["producer"]).distinct()
    if filters.get("driver"):
        receipts = receipts.filter(trip__driver=filters["driver"])
        trips = trips.filter(driver=filters["driver"])
    if filters.get("shift"):
        receipts = receipts.filter(collection_shift=filters["shift"])
        trips = trips.filter(receipts__collection_shift=filters["shift"]).distinct()
    if filters.get("status") == "VOIDED":
        receipts = receipts.filter(status=MilkReceipt.Status.VOIDED)
        trips = trips.filter(receipts__status=MilkReceipt.Status.VOIDED).distinct()
    elif filters.get("status") != "ALL":
        receipts = receipts.filter(status=MilkReceipt.Status.CONFIRMED)
    return receipts, trips


def _operational_report_data(filters):
    receipts, trips = filtered_data(filters)
    confirmed = receipts.filter(status=MilkReceipt.Status.CONFIRMED)
    totals = confirmed.aggregate(report_liters=Sum("effective_liters"), operational_liters=Sum("liters"), count=Count("id"))
    producers = list(confirmed.values("producer_id", "producer__name", "producer__document_number").annotate(report_liters=Sum("effective_liters"), operational_liters=Sum("liters"), count=Count("id")).order_by("-report_liters", "producer__name"))
    routes = list(confirmed.values("route__name").annotate(report_liters=Sum("effective_liters"), operational_liters=Sum("liters"), count=Count("id")).order_by("-report_liters"))
    daily = list(confirmed.annotate(day=TruncDate("collected_at")).values("day").annotate(report_liters=Sum("effective_liters"), operational_liters=Sum("liters"), count=Count("id")).order_by("day"))
    for collection in (producers, routes, daily):
        for item in collection:
            item["liters"] = (item["report_liters"] or Decimal("0")).quantize(Decimal("0.01"))
            item["operational_liters"] = (item["operational_liters"] or Decimal("0")).quantize(Decimal("0.01"))
    max_liters = max((item["liters"] for item in daily), default=Decimal("0"))
    for item in daily:
        item["bar_width"] = max(2, round(float(item["liters"] / max_liters) * 100)) if max_liters else 0
        item["period_share"] = round(float(item["liters"] / (totals["report_liters"] or Decimal("1"))) * 100, 1)
    completed = trips.filter(ended_at__isnull=False)
    by_driver = defaultdict(lambda: {"count": 0, "seconds": 0, "name": ""})
    for trip in completed.iterator():
        item = by_driver[str(trip.driver_id)]
        item["name"] = trip.driver.get_full_name() or trip.driver.username
        item["count"] += 1
        item["seconds"] += max(0, (trip.ended_at - trip.started_at).total_seconds())
    driver_rank = []
    for item in by_driver.values():
        minutes = item["seconds"] / 60
        driver_rank.append({"name": item["name"], "count": item["count"], "total_minutes": round(minutes, 1), "average_minutes": round(minutes / item["count"], 1), "routes_per_hour": round(item["count"] * 3600 / item["seconds"], 2) if item["seconds"] else 0})
    driver_rank.sort(key=lambda item: (-item["count"], item["average_minutes"], item["name"]))
    weighbridge = WeighbridgeRecord.objects.filter(status=WeighbridgeRecord.Status.VALIDATED, trip__in=trips)
    bridge_totals = weighbridge.aggregate(count=Count("id"))
    # A product/provider filter must not show the variance of the entire mixed load.
    bridge_totals["variance"] = (totals["report_liters"] or Decimal("0")) - (totals["operational_liters"] or Decimal("0"))
    return {"receipts": receipts, "trips": trips, "total_liters": (totals["report_liters"] or Decimal("0")).quantize(Decimal("0.01")), "operational_liters": (totals["operational_liters"] or Decimal("0")).quantize(Decimal("0.01")), "total_variance": (bridge_totals["variance"] or Decimal("0")).quantize(Decimal("0.01")), "weighbridge_count": bridge_totals["count"], "receipt_count": totals["count"], "all_receipt_count": receipts.count(), "completed_count": completed.count(), "producer_rank": producers, "route_rank": routes, "daily": daily, "daily_max_liters": max_liters, "driver_rank": driver_rank, "top_producer": producers[0] if producers else None, "weighbridge_records": weighbridge.select_related("trip__route", "trip__vehicle", "validated_by")}


def report_data(filters):
    from apps.operations.services.pricing import financial_summary
    data = _operational_report_data(filters)
    data.update(financial_summary(data["receipts"].select_related("product").iterator()))
    return data


def export_report(filters):
    data = report_data(filters)
    if data["all_receipt_count"] > 50000 or data["trips"].count() > 50000:
        raise ValueError("La descarga supera 50.000 filas. Reduzca el periodo o aplique filtros.")
    book = Workbook()
    book.remove(book.active)
    make_sheet(book, "Liquidación por proveedor", ["Proveedor", "Producto", "Litros", "Recibidos", "Bruto COP", "Retenciones COP", "Impuestos COP", "Neto COP", "Pendientes valoración"], ([r["producer"].name, r["product"].name, r["liters"], r["count"], r["gross"], r["deductions"], r["taxes"], r["net"], r["unpriced"]] for r in data["financial_rows"]))
    make_sheet(book, "Retenciones e impuestos", ["Concepto", "Tipo", "Porcentaje", "Valor COP"], ([r["name"], r["kind"], r["rate"], r["amount"]] for r in data["adjustment_totals"]))
    make_sheet(book, "Detalle económico", ["Recibido", "Proveedor", "Producto", "Litros para informe", "Precio por litro COP", "Bruto COP", "Descuentos COP", "Impuestos COP", "Neto COP", "Valorado"], _financial_export_rows(data["receipts"]))
    make_sheet(book, "Resumen", ["Indicador", "Valor"], [
        ["Fecha inicial", filters["start"].isoformat()], ["Fecha final", filters["end"].isoformat()],
        ["Litros reales para informes", data["total_liters"]], ["Litros operativos registrados", data["operational_liters"]],
        ["Varianza de básculas validadas", data["total_variance"]], ["Básculas validadas", data["weighbridge_count"]], ["Recibidos confirmados", data["receipt_count"]],
        ["Recibidos filtrados", data["all_receipt_count"]], ["Recorridos cerrados", data["completed_count"]],
    ])
    make_sheet(book, "Productores", ["Productor", "Documento", "Litros", "Recibidos"], ([r["producer__name"], r["producer__document_number"], r["liters"], r["count"]] for r in data["producer_rank"]))
    make_sheet(book, "Conductores", ["Conductor", "Recorridos", "Minutos totales", "Promedio minutos", "Recorridos por hora"], ([r["name"], r["count"], r["total_minutes"], r["average_minutes"], r["routes_per_hour"]] for r in data["driver_rank"]))
    make_sheet(book, "Recibidos", ["Número", "Fecha", "Productor", "Documento", "Ruta", "Vehículo", "Conductor de recorrido", "Litros operativos", "Litros ajustados para informe", "Estado", "Jornada"], ([r.internal_number, timezone.localtime(r.collected_at).strftime("%Y-%m-%d %H:%M"), r.producer.name, r.producer.document_number, r.route.name if r.route else "", r.vehicle.plate, (r.trip.driver.get_full_name() or r.trip.driver.username) if r.trip else "", r.liters, r.effective_liters, r.get_status_display(), r.collection_shift] for r in data["receipts"].iterator()))
    make_sheet(book, "Recorridos", ["Ruta", "Vehículo", "Conductor", "Inicio", "Cierre", "Duración minutos"], ([t.route.name, t.vehicle.plate, t.driver.get_full_name() or t.driver.username, timezone.localtime(t.started_at).strftime("%Y-%m-%d %H:%M"), timezone.localtime(t.ended_at).strftime("%Y-%m-%d %H:%M") if t.ended_at else "", round((t.ended_at - t.started_at).total_seconds() / 60, 1) if t.ended_at else ""] for t in data["trips"].iterator()))
    make_sheet(book, "Báscula", ["Ruta", "Vehículo", "Tiquete", "Peso neto kg", "Densidad kg/L", "Litros operativos", "Litros reales", "Varianza L", "Varianza %", "Resultado", "Validado por", "Fecha validación"], ([w.trip.route.name, w.trip.vehicle.plate, w.scale_ticket, w.net_weight_kg, w.density_kg_l, w.collected_liters, w.actual_liters, w.variance_liters, w.variance_percent, w.get_result_display(), w.validated_by.get_full_name() or w.validated_by.username, timezone.localtime(w.validated_at).strftime("%Y-%m-%d %H:%M")] for w in data["weighbridge_records"].iterator()))
    return workbook_response(book, f"ubalac_informe_{filters['start']}_{filters['end']}")


def _financial_export_rows(receipts):
    from apps.operations.services.pricing import receipt_amounts
    for r in receipts.select_related("product").iterator():
        amounts = receipt_amounts(r) if r.status == "CONFIRMED" else {"gross": 0, "deductions": 0, "taxes": 0, "net": 0, "priced": False}
        yield [r.internal_number, r.producer.name, r.product.name, r.effective_liters, r.unit_price, amounts["gross"], amounts["deductions"], amounts["taxes"], amounts["net"], "Sí" if amounts["priced"] else "No / anulado"]
