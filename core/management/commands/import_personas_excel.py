from __future__ import annotations

from pathlib import Path
import unicodedata

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from core.models import Empresa, Persona
from core.services import normalizar_codigo_empresa, normalizar_dni

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
    "tipo de vianda": "tipo_vianda",
    "vianda": "tipo_vianda",
    "puede invitar": "puede_invitar",
    "invitar": "puede_invitar",
    "habilita invitados": "puede_invitar",
    "invitaciones": "puede_invitar",
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


def _cell_to_bool(value: object) -> bool:
    text = _cell_to_text(value).strip().lower()
    if not text:
        return False
    return text in {"1", "si", "sí", "s", "true", "x", "yes", "y"}


def _cell_to_vianda(value: object) -> str:
    text = _cell_to_text(value).strip().lower()
    if text in {"vegetariano", "veg", "vegetariana"}:
        return Persona.VIANDA_VEGETARIANO
    return Persona.VIANDA_CLASICO


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
        parser.add_argument(
            "--empresa-code",
            type=str,
            default=None,
            help="Codigo de empresa destino (si se omite usa DEFAULT_EMPRESA_CODE).",
        )
        parser.add_argument(
            "--empresa-name",
            type=str,
            default=None,
            help="Nombre de empresa (solo se usa al crear la empresa).",
        )

    def handle(self, *args, **options):
        xlsx_path = Path(options["xlsx_path"])
        if not xlsx_path.exists():
            raise CommandError(f"No existe el archivo: {xlsx_path}")

        workbook = load_workbook(filename=xlsx_path, read_only=True, data_only=True)
        worksheet = workbook[options["sheet"]] if options["sheet"] else workbook.active

        raw_empresa_code = (
            options["empresa_code"] or getattr(settings, "DEFAULT_EMPRESA_CODE", "DEFAULT")
        )
        empresa_code = normalizar_codigo_empresa(str(raw_empresa_code)) or "DEFAULT"
        empresa_name = str(options["empresa_name"] or empresa_code).strip() or empresa_code
        empresa, empresa_created = Empresa.objects.get_or_create(
            codigo=empresa_code,
            defaults={"nombre": empresa_name, "activo": True},
        )
        if empresa.nombre != empresa_name:
            empresa.nombre = empresa_name
            empresa.save(update_fields=["nombre", "actualizado_en"])
        if not empresa.activo:
            empresa.activo = True
            empresa.save(update_fields=["activo", "actualizado_en"])

        if empresa_created:
            self.stdout.write(
                self.style.SUCCESS(f"Empresa creada: {empresa.codigo} ({empresa.nombre})")
            )

        header_row, header_map = _find_header_row(worksheet)

        created = 0
        updated = 0
        relinked = 0
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

            defaults = {
                "nombre_apellido": nombre_apellido,
                "concesionario": concesionario,
                "credencial": credencial,
                "tipo_vianda": Persona.VIANDA_CLASICO,
                "activo": True,
            }
            if "tipo_vianda" in header_map:
                defaults["tipo_vianda"] = _cell_to_vianda(row[header_map["tipo_vianda"]])
            puede_invitar: bool | None = None
            if "puede_invitar" in header_map:
                puede_invitar = _cell_to_bool(row[header_map["puede_invitar"]])
                defaults["puede_invitar"] = puede_invitar

            obj = Persona.objects.filter(empresa=empresa, dni=dni).first()
            was_created = False
            relinked_document = False

            # Fix historical imports where passport letters were stripped and only digits remained.
            if obj is None and any(ch.isalpha() for ch in dni):
                candidate_qs = Persona.objects.filter(
                    empresa=empresa,
                    nombre_apellido=nombre_apellido,
                    activo=True,
                )
                if concesionario:
                    candidate_qs = candidate_qs.filter(concesionario=concesionario)
                if credencial:
                    candidate_qs = candidate_qs.filter(credencial=credencial)

                if candidate_qs.count() == 1:
                    candidate = candidate_qs.first()
                    if candidate and candidate.dni.isdigit():
                        candidate.dni = dni
                        for field, value in defaults.items():
                            setattr(candidate, field, value)
                        try:
                            candidate.save()
                            obj = candidate
                            relinked_document = True
                        except IntegrityError:
                            obj = None

            if obj is None:
                obj = Persona.objects.create(empresa=empresa, dni=dni, **defaults)
                was_created = True
            else:
                for field, value in defaults.items():
                    setattr(obj, field, value)
                obj.save(
                    update_fields=[
                        "nombre_apellido",
                        "concesionario",
                        "credencial",
                        "tipo_vianda",
                        *(["puede_invitar"] if puede_invitar is not None else []),
                        "activo",
                        "actualizado_en",
                    ]
                )

            if was_created:
                created += 1
            elif relinked_document:
                relinked += 1
                updated += 1
            else:
                updated += 1

            self.stdout.write(
                f"OK [{empresa.codigo}] {obj.dni} | {obj.nombre_apellido} | "
                f"{obj.concesionario} | {obj.credencial} | vianda={obj.tipo_vianda} | "
                f"puede_invitar={obj.puede_invitar}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Importacion finalizada para empresa={empresa.codigo}. "
                f"creados={created} actualizados={updated} relinked={relinked} omitidos={skipped_empty}"
            )
        )
