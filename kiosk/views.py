from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie

from core.services import DomainError, lookup_persona_cupos

MASSEY_ACCESS_DENIED_MESSAGE = (
    "No se encuentra este nombre, diríjase hacia otro tótem."
)

KIOSK_BRANDS: dict[str, dict[str, object]] = {
    "fendt": {
        "slug": "fendt",
        "nombre": "Fendt",
        "totem_env": "KIOSK_TOTEM_ID_FENDT",
        "totem_default": "TOTEM_FENDT",
        "logos": [
            {
                "src": "images/fendt-logo-white.svg",
                "alt": "Fendt",
                "class_name": "brand-logo-fendt-only",
            }
        ],
    },
    "valtra": {
        "slug": "valtra",
        "nombre": "Valtra",
        "totem_env": "KIOSK_TOTEM_ID_VALTRA",
        "totem_default": "TOTEM_VALTRA",
        "logos": [
            {
                "src": "images/valtra-logo.png",
                "alt": "Valtra",
                "class_name": "brand-logo-valtra-only",
            }
        ],
    },
    "massey": {
        "slug": "massey",
        "nombre": "Massey Ferguson",
        "totem_env": "KIOSK_TOTEM_ID_MASSEY",
        "totem_default": "TOTEM_MASSEY",
        "logos": [
            {
                "src": "images/massey-logo-brand.png",
                "alt": "Massey Ferguson",
                "class_name": "brand-logo-massey",
            }
        ],
    },
}

KIOSK_BRAND_ALIASES = {
    "massei": "massey",
}


def _normalize_brand_slug(raw: str | None) -> str:
    candidate = str(raw or "").strip().lower()
    if not candidate:
        return ""
    return KIOSK_BRAND_ALIASES.get(candidate, candidate)


def _default_brand_slug() -> str:
    configured = _normalize_brand_slug(getattr(settings, "DEFAULT_KIOSK_BRAND", "fendt"))
    return configured if configured in KIOSK_BRANDS else "fendt"


def _resolve_brand_or_404(raw_brand: str | None) -> dict[str, object]:
    brand_slug = _normalize_brand_slug(raw_brand)
    brand = KIOSK_BRANDS.get(brand_slug)
    if not brand:
        raise Http404("Marca de tótem no válida.")

    totem_setting = str(brand["totem_env"])
    totem_default = str(brand["totem_default"])
    totem_id = str(getattr(settings, totem_setting, totem_default)).strip() or totem_default

    return {
        **brand,
        "totem_id": totem_id,
    }


def _build_brand_urls(brand_slug: str) -> dict[str, str]:
    return {
        "start": reverse("kiosk:start_brand", kwargs={"brand": brand_slug}),
        "dni": reverse("kiosk:dni_brand", kwargs={"brand": brand_slug}),
        "vouchers": reverse("kiosk:vouchers_brand", kwargs={"brand": brand_slug}),
    }


def _base_context(brand: dict[str, object]) -> dict[str, object]:
    empresa_codigo = str(getattr(settings, "DEFAULT_EMPRESA_CODE", "")).strip()
    return {
        "idle_seconds": settings.KIOSK_IDLE_SECONDS,
        "brand": brand,
        "urls": _build_brand_urls(str(brand["slug"])),
        "totem_id": str(brand["totem_id"]),
        "empresa_codigo": empresa_codigo,
    }


def start_default(_request: HttpRequest) -> HttpResponse:
    return redirect("kiosk:start_brand", brand=_default_brand_slug())


def dni_default(_request: HttpRequest) -> HttpResponse:
    return redirect("kiosk:dni_brand", brand=_default_brand_slug())


def vouchers_default(request: HttpRequest) -> HttpResponse:
    target = reverse("kiosk:vouchers_brand", kwargs={"brand": _default_brand_slug()})
    query_string = request.META.get("QUERY_STRING", "").strip()
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target)


@ensure_csrf_cookie
def start_screen(request: HttpRequest, brand: str) -> HttpResponse:
    brand_cfg = _resolve_brand_or_404(brand)
    return render(
        request,
        "start.html",
        _base_context(brand_cfg),
    )


@ensure_csrf_cookie
def dni_screen(request: HttpRequest, brand: str) -> HttpResponse:
    brand_cfg = _resolve_brand_or_404(brand)
    return render(
        request,
        "dni.html",
        _base_context(brand_cfg),
    )


@ensure_csrf_cookie
def vouchers_screen(request: HttpRequest, brand: str) -> HttpResponse:
    brand_cfg = _resolve_brand_or_404(brand)
    context = {
        **_base_context(brand_cfg),
        "error": None,
        "persona": None,
        "comidas": [],
        "vouchers": [],
        "dia": None,
    }

    document = request.GET.get("doc") or request.GET.get("dni", "")
    if not document:
        return redirect(context["urls"]["dni"])

    try:
        data = lookup_persona_cupos(
            dni=document,
            totem_id=str(brand_cfg["totem_id"]),
            empresa_codigo=(str(context["empresa_codigo"]).strip() or None),
        )
        context.update(data)
    except DomainError as exc:
        if str(brand_cfg["slug"]) == "massey" and exc.code == "persona_not_found":
            context["error"] = MASSEY_ACCESS_DENIED_MESSAGE
        else:
            context["error"] = exc.message

    return render(request, "vouchers.html", context)
