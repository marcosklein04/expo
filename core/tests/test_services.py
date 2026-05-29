from concurrent.futures import ThreadPoolExecutor

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from core.models import (
    CanjeOperacion,
    CanjeOperacionItem,
    CupoDiario,
    Empresa,
    Persona,
    PoolDiario,
    Ticket,
    Totem,
    VoucherTipo,
)
from core.services import (
    CantidadInvalidaError,
    CupoAgotadoError,
    PinSoporteInvalidoError,
    StockAgotadoError,
    lookup_persona_cupos,
    obtener_tickets_ultimo_canje,
    reporte_operaciones_canje,
    redeem_voucher,
    redeem_vouchers_batch,
    reporte_tickets_diario,
)


def _seed_vouchers() -> None:
    for codigo, cupo in (
        (VoucherTipo.DESAYUNO, 1),
        (VoucherTipo.ALMUERZO, 1),
        (VoucherTipo.MERIENDA, 1),
        (VoucherTipo.INVITADO, 5),
        (VoucherTipo.INVITADO_DESAYUNO, 5),
        (VoucherTipo.INVITADO_ALMUERZO, 5),
        (VoucherTipo.INVITADO_MERIENDA, 5),
    ):
        VoucherTipo.objects.update_or_create(
            codigo=codigo,
            defaults={"cupo_por_dia": cupo},
        )


class VoucherServiceTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(codigo="VALTRA_FENDT", nombre="Valtra Fendt")
        Totem.objects.create(codigo="TOTEM-01", empresa=self.empresa, nombre="Totem 1")
        Totem.objects.create(codigo="TOTEM-02", empresa=self.empresa, nombre="Totem 2")
        Totem.objects.create(codigo="TOTEM-77", empresa=self.empresa, nombre="Totem 77")
        Totem.objects.create(codigo="TOTEM-99", empresa=self.empresa, nombre="Totem 99")
        Totem.objects.create(codigo="TOTEM-MASSEY", empresa=self.empresa, nombre="Totem Massey")
        self.persona = Persona.objects.create(
            empresa=self.empresa,
            dni="30111222",
            nombre_apellido="Ada Lovelace",
            concesionario="Demo",
            credencial="STAFF",
        )
        self.persona_autorizada = Persona.objects.create(
            empresa=self.empresa,
            dni="30111223",
            nombre_apellido="Emiliano Ferrari",
            concesionario="Demo",
            credencial="STAFF",
            puede_invitar=True,
        )
        _seed_vouchers()

    def test_lookup_reports_separate_meal_counters(self):
        payload = lookup_persona_cupos(dni=self.persona.dni, totem_id="TOTEM-01")
        self.assertEqual(payload["persona"]["dni"], self.persona.dni)

        comidas = {item["codigo"]: item for item in payload["comidas"]}
        self.assertEqual(
            set(comidas),
            {VoucherTipo.DESAYUNO, VoucherTipo.ALMUERZO, VoucherTipo.MERIENDA},
        )
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["fijos"]["usados_persona"], 0)
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["fijos"]["cupo_persona"], 1)
        self.assertFalse(comidas[VoucherTipo.DESAYUNO]["invitados"]["habilitado"])
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["invitados"]["cupo_persona"], 0)
        self.assertFalse(comidas[VoucherTipo.ALMUERZO]["invitados"]["habilitado"])
        self.assertEqual(comidas[VoucherTipo.ALMUERZO]["invitados"]["cupo_persona"], 0)
        self.assertFalse(comidas[VoucherTipo.ALMUERZO]["invitados"]["ilimitado"])
        self.assertFalse(comidas[VoucherTipo.MERIENDA]["invitados"]["habilitado"])
        self.assertEqual(comidas[VoucherTipo.MERIENDA]["invitados"]["cupo_persona"], 0)
        self.assertFalse(comidas[VoucherTipo.MERIENDA]["invitados"]["ilimitado"])

    def test_lookup_marks_unlimited_guests_for_authorized_person(self):
        payload = lookup_persona_cupos(dni=self.persona_autorizada.dni, totem_id="TOTEM-01")
        comidas = {item["codigo"]: item for item in payload["comidas"]}
        self.assertTrue(comidas[VoucherTipo.DESAYUNO]["invitados"]["ilimitado"])
        self.assertTrue(comidas[VoucherTipo.DESAYUNO]["invitados"]["habilitado"])
        self.assertEqual(
            comidas[VoucherTipo.DESAYUNO]["invitados"]["disponibles_persona"],
            999,
        )
        self.assertTrue(comidas[VoucherTipo.ALMUERZO]["invitados"]["ilimitado"])
        self.assertTrue(comidas[VoucherTipo.ALMUERZO]["invitados"]["habilitado"])
        self.assertEqual(
            comidas[VoucherTipo.ALMUERZO]["invitados"]["disponibles_persona"],
            999,
        )
        self.assertTrue(comidas[VoucherTipo.MERIENDA]["invitados"]["ilimitado"])
        self.assertTrue(comidas[VoucherTipo.MERIENDA]["invitados"]["habilitado"])
        self.assertEqual(
            comidas[VoucherTipo.MERIENDA]["invitados"]["disponibles_persona"],
            999,
        )

    def test_lookup_allows_guests_for_fixed_name_without_flag(self):
        persona_fija = Persona.objects.create(
            empresa=self.empresa,
            dni="45550001",
            nombre_apellido="Facundo Guzmán",
            concesionario="Demo",
            credencial="STAFF",
            puede_invitar=False,
        )
        payload = lookup_persona_cupos(dni=persona_fija.dni, totem_id="TOTEM-01")
        comidas = {item["codigo"]: item for item in payload["comidas"]}
        self.assertTrue(comidas[VoucherTipo.DESAYUNO]["invitados"]["habilitado"])
        self.assertTrue(comidas[VoucherTipo.ALMUERZO]["invitados"]["habilitado"])
        self.assertTrue(comidas[VoucherTipo.MERIENDA]["invitados"]["habilitado"])

    def test_lookup_accepts_alphanumeric_document_for_passport(self):
        persona_pasaporte = Persona.objects.create(
            empresa=self.empresa,
            dni="AB123456",
            nombre_apellido="Katherine Johnson",
            concesionario="Demo",
            credencial="INV",
        )

        payload = lookup_persona_cupos(dni="ab-123456", totem_id="TOTEM-01")
        self.assertEqual(payload["persona"]["dni"], persona_pasaporte.dni)

    def test_lookup_uses_massey_company_without_credential_gate(self):
        empresa_massey = Empresa.objects.create(codigo="MASSEY", nombre="Massey")
        Totem.objects.update_or_create(
            codigo="TOTEM-MASSEY",
            defaults={"empresa": empresa_massey, "nombre": "Totem Massey"},
        )
        persona_massey = Persona.objects.create(
            empresa=empresa_massey,
            dni="46660001",
            nombre_apellido="Usuario Massey",
            credencial="STAFF",
        )

        payload = lookup_persona_cupos(dni=persona_massey.dni, totem_id="TOTEM-MASSEY")
        self.assertEqual(payload["empresa"]["codigo"], empresa_massey.codigo)
        self.assertEqual(payload["persona"]["dni"], persona_massey.dni)

    def test_redeem_uses_massey_company_without_credential_gate(self):
        empresa_massey = Empresa.objects.create(codigo="MASSEY", nombre="Massey")
        Totem.objects.update_or_create(
            codigo="TOTEM-MASSEY",
            defaults={"empresa": empresa_massey, "nombre": "Totem Massey"},
        )
        persona_massey = Persona.objects.create(
            empresa=empresa_massey,
            dni="46660003",
            nombre_apellido="Usuario Massey Canje",
            credencial="STAFF",
        )

        tickets = redeem_vouchers_batch(
            dni=persona_massey.dni,
            totem_id="TOTEM-MASSEY",
            items=[
                {
                    "comida": VoucherTipo.DESAYUNO,
                    "canjear_propio": True,
                    "invitados": 0,
                }
            ],
        )
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0].persona.empresa_id, empresa_massey.id)

    def test_redeem_batch_allows_guests_for_authorized_person_in_both_meals(self):
        tickets = redeem_vouchers_batch(
            dni=self.persona_autorizada.dni,
            totem_id="TOTEM-01",
            items=[
                {
                    "comida": VoucherTipo.DESAYUNO,
                    "canjear_propio": True,
                    "invitados": 2,
                },
                {"comida": VoucherTipo.ALMUERZO, "invitados": 5},
            ],
        )
        self.assertEqual(len(tickets), 9)
        self.assertTrue(all(ticket.operacion_id for ticket in tickets))

        cupo_almuerzo_inv = CupoDiario.objects.get(
            persona=self.persona_autorizada,
            voucher_tipo__codigo=VoucherTipo.INVITADO_ALMUERZO,
        )
        self.assertEqual(cupo_almuerzo_inv.usados, 5)
        cupo_desayuno_inv = CupoDiario.objects.get(
            persona=self.persona_autorizada,
            voucher_tipo__codigo=VoucherTipo.INVITADO_DESAYUNO,
        )
        self.assertEqual(cupo_desayuno_inv.usados, 2)

        operacion = CanjeOperacion.objects.get(id=tickets[0].operacion_id)
        self.assertEqual(operacion.persona_id, self.persona_autorizada.id)
        self.assertEqual(operacion.tickets.count(), 9)
        self.assertEqual(
            CanjeOperacionItem.objects.filter(operacion=operacion).count(),
            2,
        )

    def test_redeem_batch_blocks_guests_for_non_authorized_person(self):
        with self.assertRaises(CantidadInvalidaError):
            redeem_vouchers_batch(
                dni=self.persona.dni,
                totem_id="TOTEM-01",
                items=[{"comida": VoucherTipo.ALMUERZO, "invitados": 1}],
            )

    def test_redeem_batch_allows_guests_when_flag_is_true(self):
        persona_con_flag = Persona.objects.create(
            empresa=self.empresa,
            dni="34444555",
            nombre_apellido="Nombre No Autorizado",
            concesionario="Demo",
            credencial="STAFF",
            puede_invitar=True,
        )

        tickets = redeem_vouchers_batch(
            dni=persona_con_flag.dni,
            totem_id="TOTEM-01",
            items=[
                {
                    "comida": VoucherTipo.DESAYUNO,
                    "canjear_propio": False,
                    "invitados": 1,
                }
            ],
        )
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0].voucher_tipo.codigo, VoucherTipo.INVITADO_DESAYUNO)

    def test_redeem_batch_supports_merienda_with_own_and_guest_tickets(self):
        tickets = redeem_vouchers_batch(
            dni=self.persona_autorizada.dni,
            totem_id="TOTEM-01",
            items=[
                {
                    "comida": VoucherTipo.MERIENDA,
                    "canjear_propio": True,
                    "invitados": 2,
                }
            ],
        )
        self.assertEqual(len(tickets), 3)
        self.assertEqual(
            [ticket.voucher_tipo.codigo for ticket in tickets],
            [
                VoucherTipo.MERIENDA,
                VoucherTipo.INVITADO_MERIENDA,
                VoucherTipo.INVITADO_MERIENDA,
            ],
        )

        cupo_merienda = CupoDiario.objects.get(
            persona=self.persona_autorizada,
            voucher_tipo__codigo=VoucherTipo.MERIENDA,
        )
        self.assertEqual(cupo_merienda.usados, 1)
        cupo_merienda_inv = CupoDiario.objects.get(
            persona=self.persona_autorizada,
            voucher_tipo__codigo=VoucherTipo.INVITADO_MERIENDA,
        )
        self.assertEqual(cupo_merienda_inv.usados, 2)

        pool_merienda = PoolDiario.objects.get(
            empresa=self.empresa,
            dia=timezone.localdate(),
            scope_codigo="TOTEM-01",
            codigo=VoucherTipo.MERIENDA,
        )
        self.assertEqual(pool_merienda.usados, 3)

    def test_redeem_batch_allows_unlimited_breakfast_guests_for_authorized_person(self):
        persona_autorizada = Persona.objects.create(
            empresa=self.empresa,
            dni="41222333",
            nombre_apellido="Luna arcamone",
            concesionario="Demo",
            credencial="STAFF",
            puede_invitar=True,
        )

        tickets = redeem_vouchers_batch(
            dni=persona_autorizada.dni,
            totem_id="TOTEM-01",
            items=[
                {
                    "comida": VoucherTipo.DESAYUNO,
                    "canjear_propio": False,
                    "invitados": 12,
                }
            ],
        )
        self.assertEqual(len(tickets), 12)
        self.assertTrue(
            all(ticket.voucher_tipo.codigo == VoucherTipo.INVITADO_DESAYUNO for ticket in tickets)
        )

        cupo_desayuno_inv = CupoDiario.objects.get(
            persona=persona_autorizada,
            voucher_tipo__codigo=VoucherTipo.INVITADO_DESAYUNO,
            dia=timezone.localdate(),
        )
        self.assertEqual(cupo_desayuno_inv.usados, 12)
        pool_desayuno = PoolDiario.objects.get(
            empresa=self.empresa,
            dia=timezone.localdate(),
            scope_codigo="TOTEM-01",
            codigo=VoucherTipo.DESAYUNO,
        )
        self.assertEqual(pool_desayuno.usados, 12)

    @override_settings(
        KIOSK_TOTEM_ID_VALTRA="TOTEM-VALTRA",
        KIOSK_TOTEM_ID_FENDT="TOTEM-FENDT",
        POOL_STOCK_TOTEM_VALTRA_DESAYUNO=2,
        POOL_STOCK_TOTEM_VALTRA_ALMUERZO=2,
        POOL_STOCK_TOTEM_VALTRA_MERIENDA=2,
        POOL_STOCK_TOTEM_FENDT_DESAYUNO=1,
        POOL_STOCK_TOTEM_FENDT_ALMUERZO=1,
        POOL_STOCK_TOTEM_FENDT_MERIENDA=1,
    )
    def test_pool_is_scoped_per_totem_and_shared_by_own_and_guest_tickets(self):
        Totem.objects.create(codigo="TOTEM-VALTRA", empresa=self.empresa, nombre="Totem Valtra")
        Totem.objects.create(codigo="TOTEM-FENDT", empresa=self.empresa, nombre="Totem Fendt")
        persona_valtra = Persona.objects.create(
            empresa=self.empresa,
            dni="50000001",
            nombre_apellido="Gesica Pieditorti",
            credencial="AGCO",
            puede_invitar=True,
        )
        persona_fendt = Persona.objects.create(
            empresa=self.empresa,
            dni="50000002",
            nombre_apellido="Usuario Fendt",
            credencial="FENDT",
        )

        tickets = redeem_vouchers_batch(
            dni=persona_valtra.dni,
            totem_id="TOTEM-VALTRA",
            items=[
                {
                    "comida": VoucherTipo.DESAYUNO,
                    "canjear_propio": True,
                    "invitados": 1,
                }
            ],
        )
        self.assertEqual(len(tickets), 2)

        with self.assertRaises(StockAgotadoError):
            redeem_vouchers_batch(
                dni=persona_valtra.dni,
                totem_id="TOTEM-VALTRA",
                items=[
                    {
                        "comida": VoucherTipo.DESAYUNO,
                        "canjear_propio": False,
                        "invitados": 1,
                    }
                ],
            )

        ticket_fendt = redeem_voucher(
            dni=persona_fendt.dni,
            voucher_codigo=VoucherTipo.DESAYUNO,
            totem_id="TOTEM-FENDT",
        )
        self.assertEqual(ticket_fendt.totem_id, "TOTEM-FENDT")

        pool_valtra = PoolDiario.objects.get(
            empresa=self.empresa,
            scope_codigo="TOTEM-VALTRA",
            dia=timezone.localdate(),
            codigo=VoucherTipo.DESAYUNO,
        )
        pool_fendt = PoolDiario.objects.get(
            empresa=self.empresa,
            scope_codigo="TOTEM-FENDT",
            dia=timezone.localdate(),
            codigo=VoucherTipo.DESAYUNO,
        )
        self.assertEqual(pool_valtra.usados, 2)
        self.assertEqual(pool_valtra.stock_total, 2)
        self.assertEqual(pool_fendt.usados, 1)
        self.assertEqual(pool_fendt.stock_total, 1)

    @override_settings(
        KIOSK_TOTEM_ID_VALTRA="TOTEM-VALTRA",
        POOL_STOCK_TOTEM_VALTRA_MERIENDA=2,
    )
    def test_pool_uses_merienda_stock_per_totem(self):
        Totem.objects.create(codigo="TOTEM-VALTRA", empresa=self.empresa, nombre="Totem Valtra")
        persona_valtra = Persona.objects.create(
            empresa=self.empresa,
            dni="50000003",
            nombre_apellido="Facundo Guzman",
            credencial="AGCO",
        )

        tickets = redeem_vouchers_batch(
            dni=persona_valtra.dni,
            totem_id="TOTEM-VALTRA",
            items=[
                {
                    "comida": VoucherTipo.MERIENDA,
                    "canjear_propio": False,
                    "invitados": 2,
                }
            ],
        )
        self.assertEqual(len(tickets), 2)

        with self.assertRaises(StockAgotadoError):
            redeem_vouchers_batch(
                dni=persona_valtra.dni,
                totem_id="TOTEM-VALTRA",
                items=[
                    {
                        "comida": VoucherTipo.MERIENDA,
                        "canjear_propio": False,
                        "invitados": 1,
                    }
                ],
            )

        pool_merienda = PoolDiario.objects.get(
            empresa=self.empresa,
            scope_codigo="TOTEM-VALTRA",
            dia=timezone.localdate(),
            codigo=VoucherTipo.MERIENDA,
        )
        self.assertEqual(pool_merienda.usados, 2)
        self.assertEqual(pool_merienda.stock_total, 2)

    def test_redeem_batch_allows_guests_when_fixed_already_used(self):
        redeem_voucher(
            dni=self.persona_autorizada.dni,
            voucher_codigo=VoucherTipo.ALMUERZO,
            totem_id="TOTEM-01",
        )

        tickets = redeem_vouchers_batch(
            dni=self.persona_autorizada.dni,
            totem_id="TOTEM-01",
            items=[
                {
                    "comida": VoucherTipo.ALMUERZO,
                    "canjear_propio": False,
                    "invitados": 2,
                }
            ],
        )
        self.assertEqual(len(tickets), 2)
        self.assertTrue(
            all(
                ticket.voucher_tipo.codigo == VoucherTipo.INVITADO_ALMUERZO
                for ticket in tickets
            )
        )
        item = CanjeOperacionItem.objects.get(operacion_id=tickets[0].operacion_id)
        self.assertEqual(item.comida_codigo, VoucherTipo.ALMUERZO)
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

    def test_redeem_batch_blocks_breakfast_guests_for_non_authorized_person(self):
        persona_2 = Persona.objects.create(
            empresa=self.empresa,
            dni="30999111",
            nombre_apellido="Grace Hopper",
            concesionario="Demo",
            credencial="INVITADA",
        )

        with self.assertRaises(CantidadInvalidaError):
            redeem_vouchers_batch(
                dni=persona_2.dni,
                totem_id="TOTEM-02",
                items=[{"comida": VoucherTipo.DESAYUNO, "invitados": 1}],
            )

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

    def test_redeem_single_accepts_merienda(self):
        ticket = redeem_voucher(
            dni=self.persona.dni,
            voucher_codigo=VoucherTipo.MERIENDA,
            totem_id="TOTEM-01",
        )
        self.assertEqual(ticket.voucher_tipo.codigo, VoucherTipo.MERIENDA)

    def test_reporte_tickets_diario_includes_pools(self):
        redeem_vouchers_batch(
            dni=self.persona_autorizada.dni,
            totem_id="TOTEM-99",
            items=[
                {"comida": VoucherTipo.DESAYUNO, "canjear_propio": True, "invitados": 0},
                {"comida": VoucherTipo.ALMUERZO, "invitados": 1},
            ],
        )
        report = reporte_tickets_diario()
        self.assertGreaterEqual(report["total_tickets"], 3)
        self.assertTrue(report["pools"])
        self.assertIsNone(report["empresa"])

    def test_reporte_tickets_diario_filters_by_empresa(self):
        empresa_b = Empresa.objects.create(codigo="MASSEY", nombre="Massey")
        Totem.objects.create(codigo="TOTEM-B", empresa=empresa_b, nombre="Totem B")
        persona_b = Persona.objects.create(
            empresa=empresa_b,
            dni="39999111",
            nombre_apellido="Persona B",
            concesionario="B",
            credencial="B",
        )

        redeem_voucher(
            dni=self.persona.dni,
            voucher_codigo=VoucherTipo.DESAYUNO,
            totem_id="TOTEM-01",
        )
        redeem_voucher(
            dni=persona_b.dni,
            voucher_codigo=VoucherTipo.DESAYUNO,
            totem_id="TOTEM-B",
        )

        report_a = reporte_tickets_diario(empresa_codigo=self.empresa.codigo)
        report_b = reporte_tickets_diario(empresa_codigo=empresa_b.codigo)
        self.assertEqual(report_a["empresa"]["codigo"], self.empresa.codigo)
        self.assertEqual(report_b["empresa"]["codigo"], empresa_b.codigo)
        self.assertEqual(report_a["total_tickets"], 1)
        self.assertEqual(report_b["total_tickets"], 1)

    def test_reporte_operaciones_canje_returns_items_and_totals_for_merienda(self):
        redeem_vouchers_batch(
            dni=self.persona_autorizada.dni,
            totem_id="TOTEM-77",
            items=[
                {
                    "comida": VoucherTipo.MERIENDA,
                    "canjear_propio": True,
                    "invitados": 2,
                }
            ],
        )
        report = reporte_operaciones_canje(
            fecha_desde=None,
            fecha_hasta=None,
            dni=self.persona_autorizada.dni,
            totem_id="TOTEM-77",
            limit=50,
        )
        self.assertEqual(report["total_operaciones"], 1)
        self.assertEqual(report["total_tickets"], 3)
        self.assertEqual(report["total_tickets_propios"], 1)
        self.assertEqual(report["total_tickets_invitados"], 2)
        self.assertEqual(report["operaciones"][0]["items"][0]["comida"], VoucherTipo.MERIENDA)
        self.assertEqual(
            report["operaciones"][0]["persona"]["empresa_codigo"],
            self.empresa.codigo,
        )

    def test_lookup_and_redeem_isolated_by_empresa_and_totem(self):
        empresa_b = Empresa.objects.create(codigo="MASSEY", nombre="Massey")
        Totem.objects.create(codigo="TOTEM-B", empresa=empresa_b, nombre="Totem B")
        persona_b = Persona.objects.create(
            empresa=empresa_b,
            dni=self.persona.dni,
            nombre_apellido="Ada Empresa B",
            concesionario="Demo B",
            credencial="B",
        )

        payload_a = lookup_persona_cupos(dni=self.persona.dni, totem_id="TOTEM-01")
        payload_b = lookup_persona_cupos(dni=self.persona.dni, totem_id="TOTEM-B")
        self.assertEqual(payload_a["empresa"]["codigo"], self.empresa.codigo)
        self.assertEqual(payload_b["empresa"]["codigo"], empresa_b.codigo)
        self.assertEqual(payload_a["persona"]["nombre_apellido"], self.persona.nombre_apellido)
        self.assertEqual(payload_b["persona"]["nombre_apellido"], persona_b.nombre_apellido)

        ticket_a = redeem_voucher(
            dni=self.persona.dni,
            voucher_codigo=VoucherTipo.DESAYUNO,
            totem_id="TOTEM-01",
        )
        ticket_b = redeem_voucher(
            dni=persona_b.dni,
            voucher_codigo=VoucherTipo.DESAYUNO,
            totem_id="TOTEM-B",
        )
        self.assertEqual(ticket_a.persona.empresa_id, self.empresa.id)
        self.assertEqual(ticket_b.persona.empresa_id, empresa_b.id)

        with self.assertRaises(CupoAgotadoError):
            redeem_voucher(
                dni=self.persona.dni,
                voucher_codigo=VoucherTipo.DESAYUNO,
                totem_id="TOTEM-01",
            )
        with self.assertRaises(CupoAgotadoError):
            redeem_voucher(
                dni=persona_b.dni,
                voucher_codigo=VoucherTipo.DESAYUNO,
                totem_id="TOTEM-B",
            )

    def test_obtener_tickets_ultimo_canje_retorna_tickets_de_la_ultima_operacion(self):
        tickets_emitidos = redeem_vouchers_batch(
            dni=self.persona_autorizada.dni,
            totem_id="TOTEM-77",
            items=[
                {
                    "comida": VoucherTipo.ALMUERZO,
                    "canjear_propio": True,
                    "invitados": 2,
                }
            ],
        )

        tickets = obtener_tickets_ultimo_canje(
            dni=self.persona_autorizada.dni,
            pin="4832",
            totem_id="TOTEM-77",
        )
        self.assertEqual(len(tickets), 3)
        self.assertEqual(
            {ticket.ticket_numero for ticket in tickets},
            {ticket.ticket_numero for ticket in tickets_emitidos},
        )

    def test_obtener_tickets_ultimo_canje_rechaza_pin_invalido(self):
        redeem_vouchers_batch(
            dni=self.persona_autorizada.dni,
            totem_id="TOTEM-77",
            items=[
                {
                    "comida": VoucherTipo.DESAYUNO,
                    "canjear_propio": True,
                    "invitados": 0,
                }
            ],
        )

        with self.assertRaises(PinSoporteInvalidoError):
            obtener_tickets_ultimo_canje(
                dni=self.persona_autorizada.dni,
                pin="0000",
                totem_id="TOTEM-77",
            )


class VoucherConcurrencyPostgresTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Test de concurrencia habilitado solo para PostgreSQL.")

        self.empresa = Empresa.objects.create(codigo="PG_CO", nombre="Postgres Co")
        Totem.objects.create(codigo="TOTEM-01", empresa=self.empresa, nombre="Totem 1")
        self.persona = Persona.objects.create(
            empresa=self.empresa,
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
