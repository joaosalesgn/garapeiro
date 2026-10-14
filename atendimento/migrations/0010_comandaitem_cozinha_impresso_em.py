from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("atendimento", "0009_fornecedor_contapagar")]

    operations = [
        migrations.AddField(
            model_name="comandaitem",
            name="cozinha_impresso_em",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Data e hora em que o item foi enviado à impressora da cozinha.",
            ),
        ),
    ]
