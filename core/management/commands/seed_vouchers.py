from django.core.management.base import BaseCommand

from core.models import VoucherTipo


class Command(BaseCommand):
    help = "Crea/actualiza los 3 vouchers fijos con cupos diarios."

    def handle(self, *args, **options):
        defaults = [
            (VoucherTipo.DESAYUNO, 1),
            (VoucherTipo.ALMUERZO, 1),
            (VoucherTipo.INVITADO, 5),
        ]

        for codigo, cupo in defaults:
            obj, _ = VoucherTipo.objects.update_or_create(
                codigo=codigo,
                defaults={"cupo_por_dia": cupo},
            )
            self.stdout.write(
                self.style.SUCCESS(f"OK {obj.codigo} cupo={obj.cupo_por_dia}")
            )
