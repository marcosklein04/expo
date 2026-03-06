from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Empresa, Persona


@override_settings(SECURE_SSL_REDIRECT=False, DEFAULT_EMPRESA_CODE="DEFAULT")
class RegistroPersonasTests(TestCase):
    def setUp(self):
        self.empresa, _ = Empresa.objects.get_or_create(
            codigo="DEFAULT",
            defaults={"nombre": "Default"},
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
        persona = Persona.objects.get(empresa=self.empresa, dni="AB123456")
        self.assertEqual(persona.tipo_vianda, Persona.VIANDA_VEGETARIANO)
        self.assertTrue(persona.puede_invitar)

    def test_creates_persona_with_celiac_meal_type(self):
        response = self.client.post(
            self.url,
            data={
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
        persona = Persona.objects.get(empresa=self.empresa, dni="30111222")
        self.assertEqual(persona.tipo_vianda, Persona.VIANDA_CELIACO)
