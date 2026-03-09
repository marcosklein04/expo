from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings
from openpyxl import Workbook

from core.models import Empresa, Persona


class ImportPersonasExcelTests(TestCase):
    def _save_workbook(self, tmpdir: str, filename: str, build_rows) -> str:
        wb = Workbook()
        ws = wb.active
        build_rows(ws)
        path = Path(tmpdir) / filename
        wb.save(path)
        return str(path)

    @override_settings(KIOSK_SPECIAL_GUEST_NAMES=["Gesica Pieditorti"])
    def test_imports_layout_with_dni(self):
        with TemporaryDirectory() as tmpdir:
            path = self._save_workbook(
                tmpdir,
                "massey.xlsx",
                lambda ws: [
                    ws.append(["#", "Concesionario", "Nombre y apellido", "DNI", "Menú"]),
                    ws.append([1, "Dealer Massey", "Gesica Pieditorti", "30111222", "Vegetariano"]),
                ],
            )

            call_command(
                "import_personas_excel",
                path,
                empresa_code="MASSEY",
                empresa_name="Massey Ferguson",
                layout="dni",
                verbosity=0,
            )

        persona = Persona.objects.get(empresa__codigo="MASSEY", dni="30111222")
        self.assertEqual(persona.tipo_vianda, Persona.VIANDA_VEGETARIANO)
        self.assertEqual(persona.concesionario, "Dealer Massey")
        self.assertTrue(persona.puede_invitar)

    @override_settings(KIOSK_SPECIAL_GUEST_NAMES=["Facundo Guzman"])
    def test_updates_valtra_fendt_layout_by_name(self):
        empresa = Empresa.objects.create(codigo="VALTRA_FENDT", nombre="Valtra Fendt")
        persona = Persona.objects.create(
            empresa=empresa,
            dni="30999111",
            nombre_apellido="Facundo Guzman",
            concesionario="Viejo concesionario",
            credencial="OLD",
            tipo_vianda=Persona.VIANDA_CLASICO,
            puede_invitar=False,
        )

        with TemporaryDirectory() as tmpdir:
            path = self._save_workbook(
                tmpdir,
                "valtra_fendt.xlsx",
                lambda ws: [
                    ws.append(["", "", "", "", "", "", "", "", "", "", "", "", ""]),
                    ws.append(["", "", "", "", "", "", "", "", "", "", "", "", ""]),
                    ws.append(["TURNO", "Concesionarios", "", "CREDENCIAL", "Vendedores", "", "", "", "DIAS"]),
                    ws.append(["", "", "", "", "", "", "", "", "", "", "", "", ""]),
                    ws.append(["", "", "", "", "Nombre", "Apellido", "Personas", "Tipo de Vianda", "MARTES 11", "MIERCOLES 12", "JUEVES 13", "VIERNES 14", "Total"]),
                    ws.append(["PRIMER TURNO", "Nuevo concesionario", "", "AGCO", "Facundo", "Guzman", 1, "Celiaco", 1, 1, 1, 1, 4]),
                ],
            )

            call_command(
                "import_personas_excel",
                path,
                empresa_code="VALTRA_FENDT",
                empresa_name="Valtra Fendt",
                layout="valtra_fendt",
                verbosity=0,
            )

        persona.refresh_from_db()
        self.assertEqual(persona.dni, "30999111")
        self.assertEqual(persona.concesionario, "Nuevo concesionario")
        self.assertEqual(persona.credencial, "AGCO")
        self.assertEqual(persona.tipo_vianda, Persona.VIANDA_CELIACO)
        self.assertTrue(persona.puede_invitar)
