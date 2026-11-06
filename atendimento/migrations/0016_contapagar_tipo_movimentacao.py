from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("atendimento", "0015_remove_cupom_ck_cupom_percentual_ate_100_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="contapagar",
            name="tipo_movimentacao",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="contas_pagar",
                to="atendimento.tipomovimentacao",
                verbose_name="Tipo de movimentação",
            ),
        ),
        migrations.AlterModelOptions(
            name="contapagar",
            options={
                "db_table": "tab_conta_pagar",
                "ordering": ["-criado_em", "-pk"],
                "verbose_name": "conta a pagar",
                "verbose_name_plural": "contas a pagar",
            },
        ),
    ]
