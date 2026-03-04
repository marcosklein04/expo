import csv
import json
from datetime import date

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.services import (
    DomainError,
    lookup_persona_cupos,
    reporte_operaciones_canje,
    redeem_voucher,
    redeem_vouchers_batch,
    reporte_tickets_diario,
)


def _json_body(request) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise DomainError("JSON invalido.", details={"reason": str(exc)})


def _error_response(exc: DomainError) -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
        status=exc.http_status,
    )


def _serialize_ticket(ticket) -> dict:
    return {
        "ticket_numero": ticket.ticket_numero,
        "dia": ticket.dia.isoformat(),
        "creado_en": ticket.creado_en.isoformat(),
        "voucher": ticket.voucher_tipo.codigo,
        "totem_id": ticket.totem_id,
        "print_url": reverse("tickets:print_ticket", kwargs={"ticket_numero": ticket.ticket_numero}),
    }


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise DomainError("Formato de fecha invalido. Use YYYY-MM-DD.")


def _parse_limit(raw: str | None, *, default: int = 500) -> int:
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise DomainError("El parametro limit debe ser numerico.")


@require_POST
def lookup(request):
    try:
        payload = _json_body(request)
        dni = str(payload.get("dni", ""))
        totem_id = str(payload.get("totem_id") or settings.DEFAULT_TOTEM_ID).strip()
        empresa_codigo = str(payload.get("empresa_codigo", "")).strip() or None
        result = lookup_persona_cupos(
            dni=dni,
            totem_id=totem_id,
            empresa_codigo=empresa_codigo,
        )
        return JsonResponse({"ok": True, **result})
    except DomainError as exc:
        return _error_response(exc)


@require_POST
def redeem(request):
    try:
        payload = _json_body(request)
        dni = str(payload.get("dni", ""))
        voucher_codigo = str(payload.get("voucher", "")).upper().strip()
        totem_id = str(payload.get("totem_id") or settings.DEFAULT_TOTEM_ID).strip()
        empresa_codigo = str(payload.get("empresa_codigo", "")).strip() or None

        ticket = redeem_voucher(
            dni=dni,
            voucher_codigo=voucher_codigo,
            totem_id=totem_id,
            empresa_codigo=empresa_codigo,
        )
        return JsonResponse({"ok": True, "ticket": _serialize_ticket(ticket)}, status=201)
    except DomainError as exc:
        return _error_response(exc)


@require_POST
def redeem_batch(request):
    try:
        payload = _json_body(request)
        dni = str(payload.get("dni", ""))
        totem_id = str(payload.get("totem_id") or settings.DEFAULT_TOTEM_ID).strip()
        empresa_codigo = str(payload.get("empresa_codigo", "")).strip() or None
        items = payload.get("items") or []
        if not isinstance(items, list):
            raise DomainError("El campo items debe ser una lista de comidas.")

        tickets = redeem_vouchers_batch(
            dni=dni,
            items=items,
            totem_id=totem_id,
            empresa_codigo=empresa_codigo,
        )
        return JsonResponse(
            {
                "ok": True,
                "tickets": [_serialize_ticket(ticket) for ticket in tickets],
                "total_tickets": len(tickets),
            },
            status=201,
        )
    except DomainError as exc:
        return _error_response(exc)


@require_GET
def report_daily(request):
    try:
        dia = _parse_iso_date(request.GET.get("dia"))
        empresa_codigo = str(request.GET.get("empresa_codigo", "")).strip() or None
        return JsonResponse(
            {
                "ok": True,
                **reporte_tickets_diario(dia=dia, empresa_codigo=empresa_codigo),
            }
        )
    except DomainError as exc:
        return _error_response(exc)


@require_GET
def report_redeems(request):
    try:
        fecha_desde = _parse_iso_date(request.GET.get("desde"))
        fecha_hasta = _parse_iso_date(request.GET.get("hasta"))
        dni = str(request.GET.get("dni", "")).strip() or None
        totem_id = str(request.GET.get("totem_id", "")).strip() or None
        empresa_codigo = str(request.GET.get("empresa_codigo", "")).strip() or None
        limit = _parse_limit(request.GET.get("limit"), default=500)

        payload = reporte_operaciones_canje(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            dni=dni,
            totem_id=totem_id,
            empresa_codigo=empresa_codigo,
            limit=limit,
        )
        return JsonResponse({"ok": True, **payload})
    except DomainError as exc:
        return _error_response(exc)


@require_GET
def report_redeems_csv(request):
    try:
        fecha_desde = _parse_iso_date(request.GET.get("desde"))
        fecha_hasta = _parse_iso_date(request.GET.get("hasta"))
        dni = str(request.GET.get("dni", "")).strip() or None
        totem_id = str(request.GET.get("totem_id", "")).strip() or None
        empresa_codigo = str(request.GET.get("empresa_codigo", "")).strip() or None
        limit = _parse_limit(request.GET.get("limit"), default=2000)

        payload = reporte_operaciones_canje(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            dni=dni,
            totem_id=totem_id,
            empresa_codigo=empresa_codigo,
            limit=limit,
        )

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f"attachment; filename=reporte_canje_{payload['fecha_desde']}_{payload['fecha_hasta']}.csv"
        )

        writer = csv.writer(response)
        writer.writerow(
            [
                "operacion_id",
                "creado_en",
                "dia",
                "totem_id",
                "empresa_codigo",
                "dni",
                "nombre_apellido",
                "concesionario",
                "credencial",
                "comida",
                "canjear_propio",
                "cantidad_invitados",
                "tickets_total",
                "tickets_propios",
                "tickets_invitados",
            ]
        )

        for operacion in payload["operaciones"]:
            items = operacion.get("items") or [{}]
            for item in items:
                writer.writerow(
                    [
                        operacion["operacion_id"],
                        operacion["creado_en"],
                        operacion["dia"],
                        operacion["totem_id"],
                        operacion["persona"].get("empresa_codigo", ""),
                        operacion["persona"]["dni"],
                        operacion["persona"]["nombre_apellido"],
                        operacion["persona"]["concesionario"],
                        operacion["persona"]["credencial"],
                        item.get("comida", ""),
                        item.get("canjear_propio", ""),
                        item.get("cantidad_invitados", ""),
                        operacion["tickets"]["total"],
                        operacion["tickets"]["propios"],
                        operacion["tickets"]["invitados"],
                    ]
                )

        return response
    except DomainError as exc:
        return _error_response(exc)


@require_GET
def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return JsonResponse({"ok": True, "status": "healthy"}, status=200)
    except Exception as exc:
        return JsonResponse(
            {
                "ok": False,
                "status": "unhealthy",
                "error": {"code": "db_unavailable", "message": str(exc)},
            },
            status=503,
        )
