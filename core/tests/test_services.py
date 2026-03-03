from concurrent.futures import ThreadPoolExecutor

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from core.models import (
    CanjeOperacion,
    CanjeOperacionItem,
    CupoDiario,
    Persona,
    PoolDiario,
    Ticket,
    VoucherTipo,
)
from core.services import (
    CantidadInvalidaError,
    CupoAgotadoError,
    StockAgotadoError,
    lookup_persona_cupos,
    reporte_operaciones_canje,
    redeem_voucher,
    redeem_vouchers_batch,
    reporte_tickets_diario,
)


def _seed_vouchers() -> None:
    VoucherTipo.objects.create(codigo=VoucherTipo.DESAYUNO, cupo_por_dia=1)
    VoucherTipo.objects.create(codigo=VoucherTipo.ALMUERZO, cupo_por_dia=1)
    VoucherTipo.objects.create(codigo=VoucherTipo.INVITADO, cupo_por_dia=5)
    VoucherTipo.objects.create(codigo=VoucherTipo.INVITADO_DESAYUNO, cupo_por_dia=5)
    VoucherTipo.objects.create(codigo=VoucherTipo.INVITADO_ALMUERZO, cupo_por_dia=5)


class VoucherServiceTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            dni="30111222",
            nombre_apellido="Ada Lovelace",
            concesionario="Demo",
            credencial="STAFF",
        )
        _seed_vouchers()

    def test_lookup_reports_separate_meal_counters(self):
        payload = lookup_persona_cupos(dni=self.persona.dni)
        self.assertEqual(payload["persona"]["dni"], self.persona.dni)

        comidas = {item["codigo"]: item for item in payload["comidas"]}
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["fijos"]["usados_persona"], 0)
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["fijos"]["cupo_persona"], 1)
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["invitados"]["cupo_persona"], 5)
        self.assertEqual(comidas[VoucherTipo.ALMUERZO]["invitados"]["cupo_persona"], 5)

    def test_redeem_batch_allows_breakfast_and_lunch_with_separate_guest_counters(self):
        tickets = redeem_vouchers_batch(
            dni=self.persona.dni,
            totem_id="TOTEM-01",
            items=[
                {"comida": VoucherTipo.DESAYUNO, "invitados": 5},
                {"comida": VoucherTipo.ALMUERZO, "invitados": 5},
            ],
        )
        self.assertEqual(len(tickets), 12)
        self.assertTrue(all(ticket.operacion_id for ticket in tickets))

        cupo_desayuno_inv = CupoDiario.objects.get(
            persona=self.persona,
            voucher_tipo__codigo=VoucherTipo.INVITADO_DESAYUNO,
        )
        cupo_almuerzo_inv = CupoDiario.objects.get(
            persona=self.persona,
            voucher_tipo__codigo=VoucherTipo.INVITADO_ALMUERZO,
        )
        self.assertEqual(cupo_desayuno_inv.usados, 5)
        self.assertEqual(cupo_almuerzo_inv.usados, 5)

        operacion = CanjeOperacion.objects.get(id=tickets[0].operacion_id)
        self.assertEqual(operacion.persona_id, self.persona.id)
        self.assertEqual(operacion.tickets.count(), 12)
        self.assertEqual(
            CanjeOperacionItem.objects.filter(operacion=operacion).count(),
            2,
        )

    def test_redeem_batch_enforces_max_five_guests_per_meal_person(self):
        with self.assertRaises(CupoAgotadoError):
            redeem_vouchers_batch(
                dni=self.persona.dni,
                totem_id="TOTEM-01",
                items=[{"comida": VoucherTipo.DESAYUNO, "invitados": 6}],
            )

    def test_redeem_batch_allows_guests_when_fixed_already_used(self):
        redeem_voucher(
            dni=self.persona.dni,
            voucher_codigo=VoucherTipo.DESAYUNO,
            totem_id="TOTEM-01",
        )

        tickets = redeem_vouchers_batch(
            dni=self.persona.dni,
            totem_id="TOTEM-01",
            items=[
                {
                    "comida": VoucherTipo.DESAYUNO,
                    "canjear_propio": False,
                    "invitados": 2,
                }
            ],
        )
        self.assertEqual(len(tickets), 2)
        self.assertTrue(
            all(
                ticket.voucher_tipo.codigo == VoucherTipo.INVITADO_DESAYUNO
                for ticket in tickets
            )
        )
        item = CanjeOperacionItem.objects.get(operacion_id=tickets[0].operacion_id)
        self.assertEqual(item.comida_codigo, VoucherTipo.DESAYUNO)
        self.assertFalse(item.canjear_propio)
        self.assertEqual(item.cantidad_invitados, 2)

    def test_redeem_batch_rejects_item_without_fixed_or_guests(self):
        with self.assertRaises(CantidadInvalidaError):
            redeem_vouchers_batch(
                dni=self.persona.dni,
                totem_id="TOTEM-01",
                items=[
                    {
                        "comida": VoucherTipo.DESAYUNO,
                        "canjear_propio": False,
                        "invitados": 0,
                    }
                ],
            )

    @override_settings(
        POOL_STOCK_FIJOS_DESAYUNO=5,
        POOL_STOCK_FIJOS_ALMUERZO=5,
        POOL_STOCK_INVITADOS_DESAYUNO=2,
        POOL_STOCK_INVITADOS_ALMUERZO=5,
    )
    def test_redeem_batch_enforces_global_guest_pool_stock(self):
        persona_2 = Persona.objects.create(
            dni="30999111",
            nombre_apellido="Grace Hopper",
            concesionario="Demo",
            credencial="INVITADA",
        )

        redeem_vouchers_batch(
            dni=self.persona.dni,
            totem_id="TOTEM-01",
            items=[{"comida": VoucherTipo.DESAYUNO, "invitados": 2}],
        )

        with self.assertRaises(StockAgotadoError):
            redeem_vouchers_batch(
                dni=persona_2.dni,
                totem_id="TOTEM-02",
                items=[{"comida": VoucherTipo.DESAYUNO, "invitados": 1}],
            )

        pool = PoolDiario.objects.get(
            codigo=VoucherTipo.INVITADO_DESAYUNO,
        )
        self.assertEqual(pool.stock_total, 2)
        self.assertEqual(pool.usados, 2)

    def test_redeem_single_keeps_daily_limit_for_fixed_meal(self):
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

    def test_reporte_tickets_diario_includes_pools(self):
        redeem_vouchers_batch(
            dni=self.persona.dni,
            totem_id="TOTEM-99",
            items=[
                {"comida": VoucherTipo.DESAYUNO, "invitados": 2},
                {"comida": VoucherTipo.ALMUERZO, "invitados": 1},
            ],
        )
        report = reporte_tickets_diario()
        self.assertGreaterEqual(report["total_tickets"], 5)
        self.assertTrue(report["pools"])

    def test_reporte_operaciones_canje_returns_items_and_totals(self):
        redeem_vouchers_batch(
            dni=self.persona.dni,
            totem_id="TOTEM-77",
            items=[
                {
                    "comida": VoucherTipo.DESAYUNO,
                    "canjear_propio": True,
                    "invitados": 2,
                }
            ],
        )
        report = reporte_operaciones_canje(
            fecha_desde=None,
            fecha_hasta=None,
            dni=self.persona.dni,
            totem_id="TOTEM-77",
            limit=50,
        )
        self.assertEqual(report["total_operaciones"], 1)
        self.assertEqual(report["total_tickets"], 3)
        self.assertEqual(report["total_tickets_propios"], 1)
        self.assertEqual(report["total_tickets_invitados"], 2)
        self.assertEqual(report["operaciones"][0]["items"][0]["comida"], VoucherTipo.DESAYUNO)


class VoucherConcurrencyMySQLTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("Test de concurrencia habilitado solo para MySQL.")

        self.persona = Persona.objects.create(
            dni="30888999",
            nombre_apellido="Alan Turing",
            concesionario="Demo",
            credencial="VIP",
        )
        _seed_vouchers()

    def test_concurrent_redeem_creates_single_fixed_ticket_for_breakfast(self):
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

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: attempt(), range(12)))

        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(
            Ticket.objects.filter(voucher_tipo__codigo=VoucherTipo.DESAYUNO).count(),
            1,
        )
