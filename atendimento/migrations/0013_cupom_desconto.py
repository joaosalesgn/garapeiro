# Migração dos cupons promocionais e descontos aplicados às comandas.
import decimal
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("atendimento", "0012_statusauditevent")]
    operations = [
        migrations.CreateModel(
            name="Cupom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("codigo", models.CharField(max_length=40, unique=True)),
                ("tipo_desconto", models.CharField(choices=[("VALOR", "Valor fixo"), ("PERCENTUAL", "Percentual")], max_length=12)),
                ("valor_desconto", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))])),
                ("valido_de", models.DateField()),
                ("valido_ate", models.DateField()),
                ("ativo", models.BooleanField(default=True)),
                ("atualizado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(app_label)s_%(class)s_atualizados", to="auth.user")),
                ("criado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(app_label)s_%(class)s_criados", to="auth.user")),
            ],
            options={"db_table": "tab_cupom", "ordering": ["codigo"], "permissions": [("manage_cupons", "Pode cadastrar e gerenciar cupons")], "verbose_name": "cupom", "verbose_name_plural": "cupons"},
        ),
        migrations.AddField(model_name="comanda", name="cupom", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="comandas", to="atendimento.cupom")),
        migrations.AddField(model_name="comanda", name="desconto_percentual", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))])),
        migrations.AddField(model_name="comanda", name="desconto_valor", field=models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
        migrations.AddConstraint(model_name="cupom", constraint=models.CheckConstraint(condition=models.Q(("valor_desconto__gt", 0)), name="ck_cupom_desconto_positivo")),
        migrations.AddConstraint(model_name="cupom", constraint=models.CheckConstraint(condition=models.Q(("tipo_desconto", "VALOR"), models.Q(("valor_desconto__lte", 100), _connector="OR")), name="ck_cupom_percentual_ate_100")),
        migrations.AddConstraint(model_name="cupom", constraint=models.CheckConstraint(condition=models.Q(("valido_ate__gte", models.F("valido_de"))), name="ck_cupom_validade_ordem")),
    ]
