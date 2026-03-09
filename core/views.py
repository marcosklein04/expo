from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from core.forms import PersonaRegistroForm
from core.models import Empresa, Persona
from core.services import normalizar_codigo_empresa


PADRON_NOMBRES = {
    PersonaRegistroForm.PADRON_VALTRA_FENDT: "Valtra Fendt",
    PersonaRegistroForm.PADRON_MASSEY: "Massey Ferguson",
}


def _padron_registro_default() -> str:
    codigo = normalizar_codigo_empresa(str(getattr(settings, "DEFAULT_EMPRESA_CODE", "")))
    if codigo in PADRON_NOMBRES:
        return codigo
    return PersonaRegistroForm.PADRON_VALTRA_FENDT


def _empresa_registro(codigo_padron: str | None = None) -> Empresa:
    codigo = normalizar_codigo_empresa(codigo_padron or _padron_registro_default()) or _padron_registro_default()
    nombre = PADRON_NOMBRES.get(codigo, codigo)
    empresa, _ = Empresa.objects.get_or_create(
        codigo=codigo,
        defaults={"nombre": nombre, "activo": True},
    )
    if empresa.nombre != nombre:
        empresa.nombre = nombre
        empresa.save(update_fields=["nombre", "actualizado_en"])
    if not empresa.activo:
        empresa.activo = True
        empresa.save(update_fields=["activo", "actualizado_en"])
    return empresa


def personas_registro(request):
    selected_padron = normalizar_codigo_empresa(
        request.POST.get("padron_destino")
        or request.GET.get("padron")
        or request.GET.get("padron_destino")
        or _padron_registro_default()
    ) or _padron_registro_default()
    empresa = _empresa_registro(selected_padron)
    form = PersonaRegistroForm(
        request.POST or None,
        initial={"padron_destino": empresa.codigo},
    )

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        empresa = _empresa_registro(data["padron_destino"])
        persona, created = Persona.objects.update_or_create(
            empresa=empresa,
            dni=data["dni"],
            defaults={
                "nombre_apellido": data["nombre_apellido"],
                "concesionario": data["concesionario"],
                "credencial": data["credencial"],
                "tipo_vianda": data["tipo_vianda"],
                "puede_invitar": data["puede_invitar"],
                "activo": data["activo"],
            },
        )

        if created:
            messages.success(request, "Persona creada correctamente.")
        else:
            messages.success(request, "Persona actualizada correctamente.")

        return redirect(f"{reverse('core:personas_registro')}?padron={empresa.codigo}")

    recientes = (
        Persona.objects.select_related("empresa")
        .filter(empresa=empresa)
        .order_by("-actualizado_en")[:40]
    )
    return render(
        request,
        "core/personas_registro.html",
        {
            "form": form,
            "recientes": recientes,
            "empresa": empresa,
        },
    )
