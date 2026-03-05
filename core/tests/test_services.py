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
    PersonaNoEncontradaError,
    StockAgotadoError,
    lookup_persona_cupos,
    obtener_tickets_ultimo_canje,
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
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["fijos"]["usados_persona"], 0)
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["fijos"]["cupo_persona"], 1)
        self.assertFalse(comidas[VoucherTipo.DESAYUNO]["invitados"]["habilitado"])
        self.assertEqual(comidas[VoucherTipo.DESAYUNO]["invitados"]["cupo_persona"], 0)
        self.assertFalse(comidas[VoucherTipo.ALMUERZO]["invitados"]["habilitado"])
        self.assertEqual(comidas[VoucherTipo.ALMUERZO]["invitados"]["cupo_persona"], 0)
        self.assertFalse(comidas[VoucherTipo.ALMUERZO]["invitados"]["ilimitado"])

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

    @override_settings(KIOSK_TOTEM_ID_MASSEY="TOTEM-MASSEY")
    def test_lookup_restricts_massey_totem_to_agco_credential(self):
        persona_no_agco = Persona.objects.create(
            empresa=self.empresa,
            dni="46660001",
            nombre_apellido="Usuario No AGCO",
            credencial="VALTRA",
        )
        persona_agco = Persona.objects.create(
            empresa=self.empresa,
            dni="46660002",
            nombre_apellido="Usuario AGCO",
            credencial="AGCO",
        )

        with self.assertRaises(PersonaNoEncontradaError):
            lookup_persona_cupos(dni=persona_no_agco.dni, totem_id="TOTEM-MASSEY")

        payload = lookup_persona_cupos(dni=persona_agco.dni, totem_id="TOTEM-MASSEY")
        self.assertEqual(payload["persona"]["dni"], persona_agco.dni)

    @override_settings(KIOSK_TOTEM_ID_MASSEY="TOTEM-MASSEY")
    def test_redeem_blocks_massey_totem_for_non_agco_credential(self):
        persona_no_agco = Persona.objects.create(
            empresa=self.empresa,
            dni="46660003",
            nombre_apellido="Usuario Bloqueado",
            credencial="STAFF",
        )

        with self.assertRaises(PersonaNoEncontradaError):
            redeem_vouchers_batch(
                dni=persona_no_agco.dni,
                totem_id="TOTEM-MASSEY",
                items=[
                    {
                        "comida": VoucherTipo.DESAYUNO,
                        "canjear_propio": True,
                        "invitados": 0,
                    }
                ],
            )

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
        self.assertFalse(
            PoolDiario.objects.filter(
                empresa=self.empresa,
                dia=timezone.localdate(),
                codigo=VoucherTipo.INVITADO_DESAYUNO,
            ).exists()
        )

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

    def test_reporte_operaciones_canje_returns_items_and_totals(self):
        redeem_vouchers_batch(
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
        self.assertEqual(report["operaciones"][0]["items"][0]["comida"], VoucherTipo.ALMUERZO)
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


class VoucherConcurrencyMySQLTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != "mysql":
            self.skipTest("Test de concurrencia habilitado solo para MySQL.")

        self.empresa = Empresa.objects.create(codigo="MYSQL_CO", nombre="MySQL Co")
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
