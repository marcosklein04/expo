import json
from django.test import TestCase, override_settings
from core.models import Empresa, Persona, Ticket, Totem, VoucherTipo


class ApiTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(codigo="VALTRA_FENDT", nombre="Valtra Fendt")
        Totem.objects.create(codigo="TOTEM-01", empresa=self.empresa, nombre="Totem 1")
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
            dni="45555666",
            nombre_apellido="Emiliano Ferrari",
            concesionario="Demo",
            credencial="STAFF",
            puede_invitar=True,
        )
        VoucherTipo.objects.create(codigo=VoucherTipo.DESAYUNO, cupo_por_dia=1)
        VoucherTipo.objects.create(codigo=VoucherTipo.ALMUERZO, cupo_por_dia=1)
        VoucherTipo.objects.create(codigo=VoucherTipo.INVITADO, cupo_por_dia=5)
        VoucherTipo.objects.create(codigo=VoucherTipo.INVITADO_DESAYUNO, cupo_por_dia=5)
        VoucherTipo.objects.create(codigo=VoucherTipo.INVITADO_ALMUERZO, cupo_por_dia=5)

    def test_lookup_ok(self):
        response = self.client.post(
            "/api/lookup",
            data=json.dumps({"dni": self.persona.dni}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["persona"]["dni"], self.persona.dni)
        self.assertEqual(len(payload["comidas"]), 2)
        codigos = {item["codigo"] for item in payload["comidas"]}
        self.assertEqual(codigos, {VoucherTipo.DESAYUNO, VoucherTipo.ALMUERZO})

    def test_lookup_accepts_passport_alphanumeric(self):
        persona_pasaporte = Persona.objects.create(
            empresa=self.empresa,
            dni="AB123456",
            nombre_apellido="Katherine Johnson",
            concesionario="Demo",
            credencial="INV",
        )
        response = self.client.post(
            "/api/lookup",
            data=json.dumps({"dni": "ab-123456"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["persona"]["dni"], persona_pasaporte.dni)

    def test_lookup_sets_unlimited_guests_for_authorized_person(self):
        response = self.client.post(
            "/api/lookup",
            data=json.dumps({"dni": self.persona_autorizada.dni, "totem_id": "TOTEM-01"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        comidas = {item["codigo"]: item for item in payload["comidas"]}
        self.assertTrue(comidas[VoucherTipo.DESAYUNO]["invitados"]["habilitado"])
        self.assertTrue(comidas[VoucherTipo.DESAYUNO]["invitados"]["ilimitado"])
        self.assertFalse(comidas[VoucherTipo.ALMUERZO]["invitados"]["agotado_persona"])
        self.assertTrue(comidas[VoucherTipo.ALMUERZO]["invitados"]["habilitado"])
        self.assertTrue(comidas[VoucherTipo.ALMUERZO]["invitados"]["ilimitado"])

    @override_settings(KIOSK_TOTEM_ID_MASSEY="TOTEM-MASSEY")
    def test_lookup_restricts_massey_totem_to_agco_credential(self):
        self.persona.credencial = "VALTRA"
        self.persona.save(update_fields=["credencial", "actualizado_en"])

        response = self.client.post(
            "/api/lookup",
            data=json.dumps({"dni": self.persona.dni, "totem_id": "TOTEM-MASSEY"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "persona_not_found")
        self.assertIn("No se encuentra en esta base de datos", payload["error"]["message"])

    def test_redeem_batch_ok(self):
        response = self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona_autorizada.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {
                            "comida": VoucherTipo.DESAYUNO,
                            "canjear_propio": True,
                            "invitados": 1,
                        },
                        {
                            "comida": VoucherTipo.ALMUERZO,
                            "canjear_propio": True,
                            "invitados": 2,
                        },
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_tickets"], 5)
        self.assertEqual(Ticket.objects.count(), 5)

    def test_redeem_batch_invalid_payload(self):
        response = self.client.post(
            "/api/redeem-batch",
            data=json.dumps({"dni": self.persona.dni, "items": "bad"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "domain_error")

    def test_redeem_batch_invalid_meal(self):
        response = self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona.dni,
                    "totem_id": "TOTEM-01",
                    "items": [{"comida": "CENA", "invitados": 1}],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_voucher")

    def test_redeem_batch_blocks_guests_for_non_authorized_person(self):
        response = self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {
                            "comida": VoucherTipo.ALMUERZO,
                            "canjear_propio": False,
                            "invitados": 2,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_quantity")

    def test_report_daily_ok(self):
        self.client.post(
            "/api/redeem",
            data=json.dumps({"dni": self.persona.dni, "voucher": VoucherTipo.DESAYUNO}),
            content_type="application/json",
        )
        response = self.client.get("/api/reports/daily")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["total_tickets"], 1)

    def test_report_daily_filter_by_empresa(self):
        self.client.post(
            "/api/redeem",
            data=json.dumps({"dni": self.persona.dni, "voucher": VoucherTipo.DESAYUNO}),
            content_type="application/json",
        )
        response = self.client.get("/api/reports/daily", {"empresa_codigo": self.empresa.codigo})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["empresa"]["codigo"], self.empresa.codigo)
        self.assertGreaterEqual(payload["total_tickets"], 1)

    def test_report_redeems_json_ok(self):
        self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona_autorizada.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {
                            "comida": VoucherTipo.ALMUERZO,
                            "canjear_propio": False,
                            "invitados": 2,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        response = self.client.get("/api/reports/redeems")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["total_operaciones"], 1)
        self.assertGreaterEqual(payload["total_tickets_invitados"], 2)

    def test_report_redeems_csv_ok(self):
        self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona_autorizada.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {
                            "comida": VoucherTipo.ALMUERZO,
                            "canjear_propio": True,
                            "invitados": 1,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        response = self.client.get("/api/reports/redeems.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        content = response.content.decode("utf-8")
        self.assertIn("operacion_id,creado_en,dia,totem_id", content)
        self.assertIn("empresa_codigo", content.splitlines()[0])
        self.assertIn("ALMUERZO", content)

    def test_healthz_ok(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "healthy")

    def test_lookup_resolves_empresa_by_totem(self):
        empresa_b = Empresa.objects.create(codigo="MASSEY", nombre="Massey")
        Totem.objects.create(codigo="TOTEM-B", empresa=empresa_b, nombre="Totem B")
        Persona.objects.create(
            empresa=empresa_b,
            dni=self.persona.dni,
            nombre_apellido="Ada Empresa B",
            concesionario="Demo B",
            credencial="B",
        )

        response = self.client.post(
            "/api/lookup",
            data=json.dumps({"dni": self.persona.dni, "totem_id": "TOTEM-B"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["empresa"]["codigo"], "MASSEY")
        self.assertEqual(payload["persona"]["nombre_apellido"], "Ada Empresa B")
