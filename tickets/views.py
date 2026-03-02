from django.shortcuts import get_object_or_404, render

from core.models import Ticket


def print_ticket(request, ticket_numero: str):
    ticket = get_object_or_404(
        Ticket.objects.select_related("persona", "voucher_tipo"),
        ticket_numero=ticket_numero,
    )
    return render(request, "tickets/ticket.html", {"ticket": ticket})
