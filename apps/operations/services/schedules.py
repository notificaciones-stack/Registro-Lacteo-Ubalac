from __future__ import annotations

from io import BytesIO
from textwrap import wrap

from django.db.models import Max
from django.utils import timezone

from ..models import RouteSchedule, RouteScheduleHistory


def schedule_snapshot(schedule: RouteSchedule) -> dict:
    return {
        "scheduled_date": schedule.scheduled_date.isoformat(),
        "shift": schedule.shift,
        "shift_label": schedule.get_shift_display(),
        "collection_type": schedule.collection_type,
        "collection_type_label": schedule.get_collection_type_display(),
        "status": schedule.status,
        "status_label": schedule.get_status_display(),
        "driver_id": str(schedule.driver_id),
        "driver": schedule.driver.get_full_name() or schedule.driver.username,
        "route_id": str(schedule.route_id),
        "route": schedule.route.name,
        "vehicle_id": str(schedule.vehicle_id),
        "vehicle": schedule.vehicle.plate,
        "producer_ids": [str(value) for value in schedule.producers.values_list("id", flat=True)],
        "producers": list(schedule.producers.values_list("name", flat=True)),
        "notes": schedule.notes,
        "updated_at": timezone.localtime(schedule.updated_at).isoformat() if schedule.updated_at else "",
    }


def record_schedule_history(schedule: RouteSchedule, user, reason: str = "") -> RouteScheduleHistory:
    version = (schedule.history.aggregate(value=Max("version"))["value"] or 0) + 1
    return RouteScheduleHistory.objects.create(
        schedule=schedule,
        version=version,
        changed_by=user,
        reason=(reason or "").strip(),
        snapshot=schedule_snapshot(schedule),
    )


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def schedule_pdf(schedule: RouteSchedule) -> bytes:
    lines = [
        "UBALAC - PROGRAMACION DE RECOLECCION",
        "",
        f"Fecha: {schedule.scheduled_date:%d/%m/%Y}",
        f"Turno: {schedule.get_shift_display()}",
        f"Tipo de recoleccion: {schedule.get_collection_type_display()}",
        f"Estado: {schedule.get_status_display()}",
        f"Conductor: {schedule.driver.get_full_name() or schedule.driver.username}",
        f"Ruta: {schedule.route.name}",
        f"Placa: {schedule.vehicle.plate}",
        f"Creada por: {schedule.created_by.get_full_name() or schedule.created_by.username}",
        f"Ultima modificacion por: {schedule.updated_by.get_full_name() or schedule.updated_by.username}",
        "",
        "Productores programados:",
    ]
    for index, producer in enumerate(schedule.producers.all().order_by("name"), start=1):
        detail = f"{index}. {producer.name}"
        if producer.farm_name:
            detail += f" - {producer.farm_name}"
        if producer.village:
            detail += f" - {producer.village}"
        lines.extend(wrap(detail, 92) or [detail])
    if schedule.notes:
        lines += ["", "Observaciones:"] + wrap(schedule.notes, 92)
    lines += ["", "Historial de cambios:"]
    for item in schedule.history.select_related("changed_by").order_by("version"):
        actor = item.changed_by.get_full_name() or item.changed_by.username
        reason = item.reason or "Creacion inicial"
        summary = f"v{item.version} - {timezone.localtime(item.changed_at):%d/%m/%Y %H:%M} - {actor} - {reason}"
        lines.extend(wrap(summary, 92) or [summary])

    page_size = 48
    pages = [lines[i:i + page_size] for i in range(0, len(lines), page_size)] or [[]]
    font_id = 3 + (2 * len(pages))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{3 + 2*i} 0 R" for i in range(len(pages))), len(pages))).encode(),
    ]
    for page_index, page_lines in enumerate(pages):
        page_id = 3 + 2 * page_index
        content_id = page_id + 1
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>").encode())
        content_lines = ["BT", "/F1 10 Tf", "45 800 Td", "15 TL"]
        for line in page_lines:
            safe = _pdf_escape(line.encode("latin-1", "replace").decode("latin-1"))
            content_lines += [f"({safe}) Tj", "T*"]
        content_lines += ["ET"]
        stream = "\n".join(content_lines).encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = BytesIO(); out.write(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(out.tell()); out.write(f"{idx} 0 obj\n".encode()); out.write(obj); out.write(b"\nendobj\n")
    xref = out.tell(); out.write(f"xref\n0 {len(objects)+1}\n".encode()); out.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]: out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return out.getvalue()
