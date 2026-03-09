from django.test import TestCase, override_settings
from django.urls import reverse

from core.forms import PersonaRegistroForm
from core.models import Empresa, Persona


@override_settings(SECURE_SSL_REDIRECT=False, DEFAULT_EMPRESA_CODE="DEFAULT")
class RegistroPersonasTests(TestCase):
    def setUp(self):
        self.empresa_vf, _ = Empresa.objects.get_or_create(
            codigo=PersonaRegistroForm.PADRON_VALTRA_FENDT,
            defaults={"nombre": "Valtra Fendt"},
        )
        self.empresa_massey, _ = Empresa.objects.get_or_create(
            codigo=PersonaRegistroForm.PADRON_MASSEY,
            defaults={"nombre": "Massey Ferguson"},
        )
        self.url = reverse("core:personas_registro")

    def test_form_is_public(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Formulario de Personas")

    def test_creates_persona_with_meal_type(self):
        response = self.client.post(
            self.url,
            data={
                "padron_destino": PersonaRegistroForm.PADRON_VALTRA_FENDT,
                "dni": "ab-123456",
                "nombre_apellido": "Katherine Johnson",
                "concesionario": "Demo",
                "credencial": "AGCO",
                "tipo_vianda": "VEGETARIANO",
                "puede_invitar": "on",
                "activo": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        persona = Persona.objects.get(empresa=self.empresa_vf, dni="AB123456")
        self.assertEqual(persona.tipo_vianda, Persona.VIANDA_VEGETARIANO)
        self.assertTrue(persona.puede_invitar)

    def test_creates_persona_with_celiac_meal_type(self):
        response = self.client.post(
            self.url,
            data={
                "padron_destino": PersonaRegistroForm.PADRON_VALTRA_FENDT,
                "dni": "30111222",
                "nombre_apellido": "Ada Lovelace",
                "concesionario": "Demo",
                "credencial": "Valtra",
                "tipo_vianda": "CELIACO",
                "activo": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        persona = Persona.objects.get(empresa=self.empresa_vf, dni="30111222")
        self.assertEqual(persona.tipo_vianda, Persona.VIANDA_CELIACO)

    def test_creates_persona_in_selected_massey_padron(self):
        response = self.client.post(
            self.url,
            data={
                "padron_destino": PersonaRegistroForm.PADRON_MASSEY,
                "dni": "30999111",
                "nombre_apellido": "Grace Hopper",
                "concesionario": "Massey Dealer",
                "credencial": "Massey",
                "tipo_vianda": "CLASICO",
                "activo": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        persona = Persona.objects.get(empresa=self.empresa_massey, dni="30999111")
        self.assertEqual(persona.nombre_apellido, "Grace Hopper")
