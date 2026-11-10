from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("atendimento", "0017_ifood_pedidos"),
    ]

    operations = [
        migrations.AddField(
            model_name="comanda",
            name="endereco_entrega",
            field=models.CharField(
                blank=True,
                default="",
                max_length=300,
                verbose_name="Endereço de entrega",
            ),
        ),
    ]
