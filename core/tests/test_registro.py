from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Empresa, Persona


class RegistroPersonasTests(TestCase):
    def setUp(self):
        self.empresa, _ = Empresa.objects.get_or_create(
            codigo="DEFAULT",
            defaults={"nombre": "Default"},
        )
        self.url = reverse("core:personas_registro")

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_creates_persona_with_meal_type(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="operador",
            password="clave-segura-123",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.post(
            self.url,
            data={
                "dni": "ab-123456",
                "nombre_apellido": "Katherine Johnson",
                "concesionario": "Demo",
                "credencial": "INV",
                "tipo_vianda": "VEGETARIANO",
                "activo": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        persona = Persona.objects.get(empresa=self.empresa, dni="AB123456")
        self.assertEqual(persona.tipo_vianda, Persona.VIANDA_VEGETARIANO)
