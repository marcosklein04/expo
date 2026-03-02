from django.test import TestCase

from core.models import CupoDiario, Persona, Ticket, VoucherTipo
from core.services import CupoAgotadoError, lookup_persona_cupos, redeem_voucher


class VoucherServiceTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            dni="30111222",
            nombre_apellido="Ada Lovelace",
            concesionario="Demo",
            credencial="STAFF",
        )
        VoucherTipo.objects.create(codigo=VoucherTipo.DESAYUNO, cupo_por_dia=1)
        VoucherTipo.objects.create(codigo=VoucherTipo.ALMUERZO, cupo_por_dia=1)
        VoucherTipo.objects.create(codigo=VoucherTipo.INVITADO, cupo_por_dia=5)

    def test_lookup_reports_initial_quota(self):
        payload = lookup_persona_cupos(dni=self.persona.dni)
        self.assertEqual(payload["persona"]["dni"], self.persona.dni)
        vouchers = {item["codigo"]: item for item in payload["vouchers"]}
        self.assertEqual(vouchers[VoucherTipo.DESAYUNO]["usados"], 0)
        self.assertEqual(vouchers[VoucherTipo.DESAYUNO]["cupo_por_dia"], 1)
        self.assertEqual(vouchers[VoucherTipo.INVITADO]["cupo_por_dia"], 5)

    def test_redeem_enforces_daily_limit(self):
        redeem_voucher(
            dni=self.persona.dni,
            voucher_codigo=VoucherTipo.DESAYUNO,
            totem_id="TOTEM-01",
        )

        with self.assertRaises(CupoAgotadoError):
            redeem_voucher(
                dni=self.persona.dni,
                voucher_codigo=VoucherTipo.DESAYUNO,
                totem_id="TOTEM-01",
            )

        self.assertEqual(Ticket.objects.count(), 1)
        cupo = CupoDiario.objects.get(
            persona=self.persona,
            voucher_tipo__codigo=VoucherTipo.DESAYUNO,
        )
        self.assertEqual(cupo.usados, 1)

    def test_redeem_invited_allows_five(self):
        for _ in range(5):
            redeem_voucher(
                dni=self.persona.dni,
                voucher_codigo=VoucherTipo.INVITADO,
                totem_id="TOTEM-01",
            )

        with self.assertRaises(CupoAgotadoError):
            redeem_voucher(
                dni=self.persona.dni,
                voucher_codigo=VoucherTipo.INVITADO,
                totem_id="TOTEM-01",
            )

        self.assertEqual(
            Ticket.objects.filter(voucher_tipo__codigo=VoucherTipo.INVITADO).count(),
            5,
        )
