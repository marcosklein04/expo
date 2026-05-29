from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_postre'),
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
                ],
                max_length=20,
            ),
        ),
    ]
