from __future__ import annotations

from django import forms

from core.models import Persona
from core.services import normalizar_dni


class PersonaRegistroForm(forms.ModelForm):
    class Meta:
        model = Persona
        fields = [
            "dni",
            "nombre_apellido",
            "concesionario",
            "credencial",
            "tipo_vianda",
            "puede_invitar",
            "activo",
        ]
        labels = {
            "dni": "DNI/Pasaporte",
            "nombre_apellido": "Nombre y apellido",
            "tipo_vianda": "Tipo de vianda",
            "puede_invitar": "Puede invitar",
        }

    def clean_dni(self):
        dni = normalizar_dni(self.cleaned_data.get("dni", ""))
        if not dni:
            raise forms.ValidationError("Ingresá un documento válido.")
        return dni
