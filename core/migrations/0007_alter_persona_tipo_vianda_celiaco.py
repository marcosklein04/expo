from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_persona_tipo_vianda"),
    ]

    operations = [
        migrations.AlterField(
            model_name="persona",
            name="tipo_vianda",
            field=models.CharField(
                choices=[
                    ("CLASICO", "Clasico"),
                    ("VEGETARIANO", "Vegetariano"),
                    ("CELIACO", "Celiaco"),
                ],
                default="CLASICO",
                max_length=12,
            ),
        ),
    ]
