from __future__ import annotations

from django import forms

from core.models import Persona
from core.services import normalizar_dni


class PersonaRegistroForm(forms.ModelForm):
    CREDENCIAL_VALTRA = "Valtra"
    CREDENCIAL_AGCO = "AGCO"
    CREDENCIAL_CHOICES = (
        (CREDENCIAL_VALTRA, "Valtra"),
        (CREDENCIAL_AGCO, "AGCO"),
    )

    credencial = forms.ChoiceField(
        choices=CREDENCIAL_CHOICES,
        label="Credencial",
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dni"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Ej: 30111222 o AB123456",
                "autocomplete": "off",
            }
        )
        self.fields["nombre_apellido"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Nombre y apellido",
                "autocomplete": "off",
            }
        )
        self.fields["concesionario"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Concesionario",
                "autocomplete": "off",
            }
        )
        self.fields["credencial"].widget.attrs.update({"class": "form-select"})
        self.fields["tipo_vianda"].widget.attrs.update({"class": "form-select"})
        self.fields["puede_invitar"].widget.attrs.update({"class": "form-check-input"})
        self.fields["activo"].widget.attrs.update({"class": "form-check-input"})

    def clean_dni(self):
        dni = normalizar_dni(self.cleaned_data.get("dni", ""))
        if not dni:
            raise forms.ValidationError("Ingresá un documento válido.")
        return dni
