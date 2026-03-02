from __future__ import annotations

from pathlib import Path
import unicodedata

from django.core.management.base import BaseCommand, CommandError

from core.models import Persona
from core.services import normalizar_dni

try:
    from openpyxl import load_workbook
except ImportError as exc:  # pragma: no cover
    raise ImportError("openpyxl no esta instalado") from exc


COLUMN_ALIASES = {
    "dni": "dni",
    "documento": "dni",
    "nro dni": "dni",
    "nombre y apellido": "nombre_apellido",
    "nombre apellido": "nombre_apellido",
    "apellido y nombre": "nombre_apellido",
    "concesionario": "concesionario",
    "credencial": "credencial",
}
REQUIRED_FIELDS = {"dni", "nombre_apellido"}


def _normalize_header(value: object) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.replace("\n", " ").split())


def _cell_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _find_header_row(worksheet) -> tuple[int, dict[str, int]]:
    for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        header_map: dict[str, int] = {}
        for index, raw_cell in enumerate(row):
            normalized = _normalize_header(raw_cell)
            if not normalized:
                continue
            mapped = COLUMN_ALIASES.get(normalized)
            if mapped and mapped not in header_map:
                header_map[mapped] = index

        if REQUIRED_FIELDS.issubset(header_map.keys()):
            return row_index, header_map

    raise CommandError(
        "No se encontro una fila de cabecera valida. Debe incluir al menos DNI y Nombre y Apellido."
    )


class Command(BaseCommand):
    help = "Importa personas desde archivo Excel (XLSX) a la tabla Persona."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=str, help="Ruta del archivo XLSX")
        parser.add_argument(
            "--sheet",
            type=str,
            default=None,
            help="Nombre de hoja (si se omite usa la activa)",
        )

    def handle(self, *args, **options):
        xlsx_path = Path(options["xlsx_path"])
        if not xlsx_path.exists():
            raise CommandError(f"No existe el archivo: {xlsx_path}")

        workbook = load_workbook(filename=xlsx_path, read_only=True, data_only=True)
        worksheet = workbook[options["sheet"]] if options["sheet"] else workbook.active

        header_row, header_map = _find_header_row(worksheet)

        created = 0
        updated = 0
        skipped_empty = 0

        for row in worksheet.iter_rows(min_row=header_row + 1, values_only=True):
            raw_dni = _cell_to_text(row[header_map["dni"]])
            dni = normalizar_dni(raw_dni)
            if not dni:
                skipped_empty += 1
                continue

            nombre_apellido = _cell_to_text(row[header_map["nombre_apellido"]])
            if not nombre_apellido:
                skipped_empty += 1
                continue

            concesionario = ""
            if "concesionario" in header_map:
                concesionario = _cell_to_text(row[header_map["concesionario"]])

            credencial = ""
            if "credencial" in header_map:
                credencial = _cell_to_text(row[header_map["credencial"]])

            obj, was_created = Persona.objects.update_or_create(
                dni=dni,
                defaults={
                    "nombre_apellido": nombre_apellido,
                    "concesionario": concesionario,
                    "credencial": credencial,
                    "activo": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

            self.stdout.write(
                f"OK {obj.dni} | {obj.nombre_apellido} | {obj.concesionario} | {obj.credencial}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Importacion finalizada. "
                f"creados={created} actualizados={updated} omitidos={skipped_empty}"
            )
        )
