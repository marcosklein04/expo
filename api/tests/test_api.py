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

    def test_redeem_batch_ok(self):
        response = self.client.post(
            "/api/redeem-batch",
            data=json.dumps(
                {
                    "dni": self.persona.dni,
                    "totem_id": "TOTEM-01",
                    "items": [
                        {"voucher": VoucherTipo.DESAYUNO, "cantidad": 1},
                        {"voucher": VoucherTipo.INVITADO, "cantidad": 2},
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_tickets"], 3)
        self.assertEqual(Ticket.objects.count(), 3)

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

    def test_healthz_ok(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "healthy")

