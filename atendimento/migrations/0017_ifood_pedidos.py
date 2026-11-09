from decimal import Decimal

from django.db import migrations, models
import django.core.validators
from django.db.models import F, Q


def copiar_preco_normal_para_ifood(apps, schema_editor):
    Produto = apps.get_model("atendimento", "Produto")
    Produto.objects.using(schema_editor.connection.alias).update(preco_ifood=F("preco"))


class Migration(migrations.Migration):
    dependencies = [("atendimento", "0016_contapagar_tipo_movimentacao")]

    operations = [
        migrations.AddField(
            model_name="produto", name="preco_ifood",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name="Preço iFood"),
            preserve_default=False,
        ),
        migrations.RunPython(copiar_preco_normal_para_ifood, migrations.RunPython.noop),
        migrations.AddField(
            model_name="comanda", name="codigo_ifood",
            field=models.CharField(blank=True, max_length=40, verbose_name="Código do pedido iFood"),
        ),
        migrations.AlterField(
            model_name="comanda", name="canal",
            field=models.CharField(choices=[("MESA", "Mesa"), ("BALCAO", "Balcão/retirada"), ("ENTREGA", "Entrega"), ("IFOOD", "iFood")], default="MESA", max_length=10),
        ),
        migrations.AlterField(
            model_name="pagamento", name="forma",
            field=models.CharField(choices=[("DINHEIRO", "Dinheiro"), ("PIX", "PIX"), ("CREDITO", "Cartão de crédito"), ("DEBITO", "Cartão de débito"), ("OUTRO", "Outro"), ("IFOOD", "iFood")], max_length=10),
        ),
        migrations.AddConstraint(
            model_name="comanda",
            constraint=models.CheckConstraint(condition=(Q(("canal", "IFOOD"), ("codigo_ifood__gt", "")) | (~Q(("canal", "IFOOD")) & Q(("codigo_ifood", "")))), name="ck_comanda_codigo_ifood_canal"),
        ),
    ]
