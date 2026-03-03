from django.shortcuts import get_object_or_404, render

from core.models import Ticket


def _parse_bool_flag(raw_value: str | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() not in {"0", "false", "no", "off"}


def print_ticket(request, ticket_numero: str):
    ticket = get_object_or_404(
        Ticket.objects.select_related("persona", "voucher_tipo"),
        ticket_numero=ticket_numero,
    )
    auto_print = _parse_bool_flag(request.GET.get("autoprint"), default=True)
    auto_close = _parse_bool_flag(request.GET.get("autoclose"), default=True)
    return render(
        request,
        "tickets/ticket.html",
        {
            "ticket": ticket,
            "auto_print": auto_print,
            "auto_close": auto_close,
        },
    )
