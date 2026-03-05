from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from core.forms import PersonaRegistroForm
from core.models import Empresa, Persona
from core.services import normalizar_codigo_empresa


def _empresa_registro() -> Empresa:
    codigo = normalizar_codigo_empresa(
        str(getattr(settings, "DEFAULT_EMPRESA_CODE", "DEFAULT"))
    ) or "DEFAULT"
    empresa, _ = Empresa.objects.get_or_create(
        codigo=codigo,
        defaults={"nombre": codigo, "activo": True},
    )
    if not empresa.activo:
        empresa.activo = True
        empresa.save(update_fields=["activo", "actualizado_en"])
    return empresa


def personas_registro(request):
    empresa = _empresa_registro()
    form = PersonaRegistroForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
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

        return redirect("core:personas_registro")

    recientes = Persona.objects.select_related("empresa").order_by("-actualizado_en")[:40]
    return render(
        request,
        "core/personas_registro.html",
        {
            "form": form,
            "recientes": recientes,
            "empresa": empresa,
        },
    )
