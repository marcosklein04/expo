from django.conf import settings
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from core.services import DomainError, lookup_persona_cupos


@ensure_csrf_cookie
def start_screen(request):
    return render(
        request,
        "start.html",
        {
            "idle_seconds": settings.KIOSK_IDLE_SECONDS,
        },
    )


@ensure_csrf_cookie
def dni_screen(request):
    return render(
        request,
        "dni.html",
        {
            "idle_seconds": settings.KIOSK_IDLE_SECONDS,
        },
    )


@ensure_csrf_cookie
def vouchers_screen(request):
    document = request.GET.get("doc") or request.GET.get("dni", "")
    if not document:
        return redirect("kiosk:dni")

    context = {
        "idle_seconds": settings.KIOSK_IDLE_SECONDS,
        "totem_id": settings.DEFAULT_TOTEM_ID,
        "error": None,
        "persona": None,
        "comidas": [],
        "vouchers": [],
        "dia": None,
    }

    try:
        data = lookup_persona_cupos(
            dni=document,
            totem_id=settings.DEFAULT_TOTEM_ID,
        )
        context.update(data)
    except DomainError as exc:
        context["error"] = exc.message

    return render(request, "vouchers.html", context)
