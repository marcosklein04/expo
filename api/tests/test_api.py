import json

from django.test import TestCase

from core.models import Persona, Ticket, VoucherTipo


class ApiTests(TestCase):
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

    def test_redeem_batch_ok(self):
        response = self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {
                            "comida": VoucherTipo.DESAYUNO,
                            "canjear_propio": True,
                            "invitados": 2,
                        },
                        {
                            "comida": VoucherTipo.ALMUERZO,
                            "canjear_propio": True,
                            "invitados": 1,
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

    def test_redeem_batch_allows_guests_only_when_fixed_was_used(self):
        first = self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {
                            "comida": VoucherTipo.DESAYUNO,
                            "canjear_propio": True,
                            "invitados": 0,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {
                            "comida": VoucherTipo.DESAYUNO,
                            "canjear_propio": False,
                            "invitados": 2,
                        }
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 201)
        payload = second.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_tickets"], 2)

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

    def test_report_redeems_json_ok(self):
        self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {
                            "comida": VoucherTipo.DESAYUNO,
                            "canjear_propio": True,
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
                    "dni": self.persona.dni,
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
        self.assertIn("ALMUERZO", content)

    def test_healthz_ok(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "healthy")
