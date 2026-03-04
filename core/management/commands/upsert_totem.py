from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.models import Empresa, Totem
from core.services import normalizar_codigo_empresa


class Command(BaseCommand):
    help = "Crea o actualiza un totem y lo vincula a una empresa."

    def add_arguments(self, parser):
        parser.add_argument("--codigo", required=True, type=str, help="Codigo de totem.")
        parser.add_argument(
            "--empresa-code",
            required=True,
            type=str,
            help="Codigo de empresa dueña del totem.",
        )
        parser.add_argument(
            "--nombre",
            required=False,
            type=str,
            default="",
            help="Nombre del totem.",
        )
        parser.add_argument(
            "--inactivo",
            action="store_true",
            help="Marca el totem como inactivo.",
        )

    def handle(self, *args, **options):
        codigo = str(options["codigo"] or "").strip().upper()
        if not codigo:
            raise CommandError("Debe enviar un codigo de totem valido.")

        empresa_code = normalizar_codigo_empresa(options["empresa_code"])
        if not empresa_code:
            raise CommandError("Debe enviar un codigo de empresa valido.")

        empresa = Empresa.objects.filter(codigo=empresa_code).first()
        if not empresa:
            raise CommandError(
                f"No existe la empresa '{empresa_code}'. Crear primero con upsert_empresa."
            )

        nombre = str(options["nombre"] or codigo).strip() or codigo
        activo = not bool(options["inactivo"])

        totem, created = Totem.objects.update_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "empresa": empresa,
                "activo": activo,
            },
        )

        status = "creado" if created else "actualizado"
        self.stdout.write(
            self.style.SUCCESS(
                f"Totem {status}: codigo={totem.codigo} empresa={totem.empresa.codigo} activo={totem.activo}"
            )
        )
