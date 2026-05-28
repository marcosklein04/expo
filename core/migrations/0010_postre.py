from django.db import migrations, models


def seed_postre_vouchers(apps, schema_editor):
    VoucherTipo = apps.get_model("core", "VoucherTipo")
    for codigo, cupo in (
        ("POSTRE", 1),
        ("INVITADO_POSTRE", 5),
    ):
        VoucherTipo.objects.update_or_create(
            codigo=codigo,
            defaults={"cupo_por_dia": cupo},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_alter_canjeoperacionitem_comida_codigo_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='canjeoperacionitem',
            name='comida_codigo',
            field=models.CharField(
                choices=[
                    ('DESAYUNO', 'Desayuno'),
                    ('ALMUERZO', 'Almuerzo'),
                    ('MERIENDA', 'Merienda'),
                    ('POSTRE', 'Postre'),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='pooldiario',
            name='codigo',
            field=models.CharField(
                choices=[
                    ('DESAYUNO', 'Pool fijos desayuno'),
                    ('ALMUERZO', 'Pool fijos almuerzo'),
                    ('MERIENDA', 'Pool fijos merienda'),
                    ('POSTRE', 'Pool fijos postre'),
                    ('INVITADO_DESAYUNO', 'Pool invitados desayuno'),
                    ('INVITADO_ALMUERZO', 'Pool invitados almuerzo'),
                    ('INVITADO_MERIENDA', 'Pool invitados merienda'),
                    ('INVITADO_POSTRE', 'Pool invitados postre'),
                ],
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name='vouchertipo',
            name='codigo',
            field=models.CharField(
                choices=[
                    ('DESAYUNO', 'Desayuno'),
                    ('ALMUERZO', 'Almuerzo'),
                    ('MERIENDA', 'Merienda'),
                    ('POSTRE', 'Postre'),
                    ('INVITADO', 'Invitado'),
                    ('INVITADO_DESAYUNO', 'Invitado desayuno'),
                    ('INVITADO_ALMUERZO', 'Invitado almuerzo'),
                    ('INVITADO_MERIENDA', 'Invitado merienda'),
                    ('INVITADO_POSTRE', 'Invitado postre'),
                ],
                max_length=20,
                unique=True,
            ),
        ),
        migrations.RunPython(seed_postre_vouchers, migrations.RunPython.noop),
    ]
