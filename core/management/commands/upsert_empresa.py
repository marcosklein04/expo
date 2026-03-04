from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.models import Empresa
from core.services import normalizar_codigo_empresa


class Command(BaseCommand):
    help = "Crea o actualiza una empresa para el esquema multiempresa."

    def add_arguments(self, parser):
        parser.add_argument("--codigo", required=True, type=str, help="Codigo de empresa.")
        parser.add_argument(
            "--nombre",
            required=False,
            type=str,
            default="",
            help="Nombre de empresa.",
        )
        parser.add_argument(
            "--inactivo",
            action="store_true",
            help="Marca la empresa como inactiva.",
        )

    def handle(self, *args, **options):
        codigo = normalizar_codigo_empresa(options["codigo"])
        if not codigo:
            raise CommandError("Debe enviar un codigo de empresa valido.")

        nombre = str(options["nombre"] or codigo).strip() or codigo
        activo = not bool(options["inactivo"])

        empresa, created = Empresa.objects.update_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "activo": activo,
            },
        )

        status = "creada" if created else "actualizada"
        self.stdout.write(
            self.style.SUCCESS(
                f"Empresa {status}: codigo={empresa.codigo} nombre={empresa.nombre} activo={empresa.activo}"
            )
        )
