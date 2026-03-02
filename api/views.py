import json

from django.conf import settings
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.services import DomainError, lookup_persona_cupos, redeem_voucher


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


@csrf_exempt
@require_POST
def lookup(request):
    try:
        payload = _json_body(request)
        dni = str(payload.get("dni", ""))
        result = lookup_persona_cupos(dni=dni)
        return JsonResponse({"ok": True, **result})
    except DomainError as exc:
        return _error_response(exc)


@csrf_exempt
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

        print_url = reverse("tickets:print_ticket", kwargs={"ticket_numero": ticket.ticket_numero})
        return JsonResponse(
            {
                "ok": True,
                "ticket": {
                    "ticket_numero": ticket.ticket_numero,
                    "dia": ticket.dia.isoformat(),
                    "creado_en": ticket.creado_en.isoformat(),
                    "voucher": ticket.voucher_tipo.codigo,
                    "totem_id": ticket.totem_id,
                    "print_url": print_url,
                },
            },
            status=201,
        )
    except DomainError as exc:
        return _error_response(exc)
