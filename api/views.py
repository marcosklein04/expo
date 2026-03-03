import json
from datetime import date

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.services import (
    DomainError,
    lookup_persona_cupos,
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


@require_POST
def lookup(request):
    try:
        payload = _json_body(request)
        dni = str(payload.get("dni", ""))
        result = lookup_persona_cupos(dni=dni)
        return JsonResponse({"ok": True, **result})
    except DomainError as exc:
        return _error_response(exc)


@require_POST
def redeem(request):
    try:
        payload = _json_body(request)
        dni = str(payload.get("dni", ""))
        voucher_codigo = str(payload.get("voucher", "")).upper().strip()
        totem_id = str(payload.get("totem_id") or settings.DEFAULT_TOTEM_ID)

        ticket = redeem_voucher(
            dni=dni,
            voucher_codigo=voucher_codigo,
            totem_id=totem_id,
        )
        return JsonResponse({"ok": True, "ticket": _serialize_ticket(ticket)}, status=201)
    except DomainError as exc:
        return _error_response(exc)


@require_POST
def redeem_batch(request):
    try:
        payload = _json_body(request)
        dni = str(payload.get("dni", ""))
        totem_id = str(payload.get("totem_id") or settings.DEFAULT_TOTEM_ID)
        items = payload.get("items") or []
        if not isinstance(items, list):
            raise DomainError("El campo items debe ser una lista de vouchers.")

        tickets = redeem_vouchers_batch(
            dni=dni,
            items=items,
            totem_id=totem_id,
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
        return JsonResponse({"ok": True, **reporte_tickets_diario(dia=dia)})
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

