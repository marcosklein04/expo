from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Empresa, Persona, Ticket, VoucherTipo


class TicketAdminSummaryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin",
        )
        self.client.force_login(self.user)

        self.empresa = Empresa.objects.create(codigo="ADMIN_TEST", nombre="Admin Test")
        self.persona_hoy = Persona.objects.create(
            empresa=self.empresa,
            dni="30111222",
            nombre_apellido="Ada Lovelace",
            credencial="VALTRA",
        )
        self.persona_otro_dia = Persona.objects.create(
            empresa=self.empresa,
            dni="30111223",
            nombre_apellido="Grace Hopper",
            credencial="VALTRA",
        )
        self.voucher = VoucherTipo.objects.create(
            codigo=VoucherTipo.DESAYUNO,
            cupo_por_dia=1,
        )

    def test_summary_page_filters_rows_by_selected_date(self):
        Ticket.objects.create(
            persona=self.persona_hoy,
            voucher_tipo=self.voucher,
            dia=date(2026, 3, 6),
            totem_id="TOTEM_VALTRA",
            ticket_numero="TICKET-20260306-1",
        )
        Ticket.objects.create(
            persona=self.persona_otro_dia,
            voucher_tipo=self.voucher,
            dia=date(2026, 3, 5),
            totem_id="TOTEM_VALTRA",
            ticket_numero="TICKET-20260305-1",
        )

        response = self.client.get(
            reverse("admin:core_ticket_resumen_dia"),
            {"dia": "2026-03-06"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="2026-03-06"', html=False)
        self.assertContains(response, "Ada Lovelace")
        self.assertNotContains(response, "Grace Hopper")
