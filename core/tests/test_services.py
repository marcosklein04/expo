from concurrent.futures import ThreadPoolExecutor
from django.db import connection
from django.test import TestCase, TransactionTestCase
from core.models import CupoDiario, Persona, Ticket, VoucherTipo
from core.services import (
    CupoAgotadoError,
    lookup_persona_cupos,
    redeem_voucher,
    redeem_vouchers_batch,
    reporte_tickets_diario,
)


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

    def test_redeem_batch_supports_multiple_vouchers(self):
        tickets = redeem_vouchers_batch(
            dni=self.persona.dni,
            totem_id="TOTEM-01",
            items=[
                {"voucher": VoucherTipo.DESAYUNO, "cantidad": 1},
                {"voucher": VoucherTipo.ALMUERZO, "cantidad": 1},
                {"voucher": VoucherTipo.INVITADO, "cantidad": 2},
            ],
        )

        self.assertEqual(len(tickets), 4)
        self.assertEqual(
            Ticket.objects.filter(voucher_tipo__codigo=VoucherTipo.DESAYUNO).count(),
            1,
        )
        self.assertEqual(
            Ticket.objects.filter(voucher_tipo__codigo=VoucherTipo.ALMUERZO).count(),
            1,
        )
        self.assertEqual(
            Ticket.objects.filter(voucher_tipo__codigo=VoucherTipo.INVITADO).count(),
            2,
        )

    def test_redeem_batch_fails_when_requested_quantity_exceeds_quota(self):
        with self.assertRaises(CupoAgotadoError):
            redeem_vouchers_batch(
                dni=self.persona.dni,
                totem_id="TOTEM-01",
                items=[{"voucher": VoucherTipo.DESAYUNO, "cantidad": 2}],
            )

    def test_reporte_tickets_diario_returns_breakdown(self):
        redeem_vouchers_batch(
            dni=self.persona.dni,
            totem_id="TOTEM-99",
            items=[
                {"voucher": VoucherTipo.DESAYUNO, "cantidad": 1},
                {"voucher": VoucherTipo.INVITADO, "cantidad": 2},
            ],
        )

        report = reporte_tickets_diario()
        self.assertEqual(report["total_tickets"], 3)
        by_voucher = {row["voucher"]: row["total"] for row in report["por_voucher"]}
        self.assertEqual(by_voucher[VoucherTipo.DESAYUNO], 1)
        self.assertEqual(by_voucher[VoucherTipo.INVITADO], 2)
        self.assertEqual(report["por_totem"][0]["totem_id"], "TOTEM-99")


class VoucherConcurrencyMySQLTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("Test de concurrencia habilitado solo para MySQL.")

        self.persona = Persona.objects.create(
            dni="30888999",
            nombre_apellido="Grace Hopper",
            concesionario="Demo",
            credencial="VIP",
        )
        VoucherTipo.objects.create(codigo=VoucherTipo.DESAYUNO, cupo_por_dia=1)
        VoucherTipo.objects.create(codigo=VoucherTipo.ALMUERZO, cupo_por_dia=1)
        VoucherTipo.objects.create(codigo=VoucherTipo.INVITADO, cupo_por_dia=5)

    def test_concurrent_redeem_creates_single_ticket_for_single_quota(self):
        def attempt():
            try:
                redeem_voucher(
                    dni=self.persona.dni,
                    voucher_codigo=VoucherTipo.DESAYUNO,
                    totem_id="TOTEM-01",
                )
                return "ok"
            except CupoAgotadoError:
                return "quota_exhausted"

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _: attempt(), range(10)))

        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(
            Ticket.objects.filter(voucher_tipo__codigo=VoucherTipo.DESAYUNO).count(),
            1,
        )

