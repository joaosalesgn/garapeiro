# Nova etapa financeira incremental; preserva as tabelas e os dados anteriores.
import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("atendimento", "0007_alter_adicional_options_caixa_comanda_comandaitem_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContaReceber",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("valor_total", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("vencimento", models.DateField()),
                ("status", models.CharField(choices=[("ABERTA", "Em aberto"), ("PARCIAL", "Parcialmente recebida"), ("QUITADA", "Quitada")], default="ABERTA", max_length=10)),
                ("observacao", models.TextField(blank=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_contareceber_atualizados", to=settings.AUTH_USER_MODEL)),
                ("cliente", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="contas_receber", to="atendimento.cliente")),
                ("comanda", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="conta_receber", to="atendimento.comanda")),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_contareceber_criados", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "tab_conta_receber", "ordering": ["vencimento", "-criado_em"], "verbose_name": "conta a receber", "verbose_name_plural": "contas a receber"},
        ),
        migrations.CreateModel(
            name="ContaPagar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("descricao", models.CharField(max_length=180)),
                ("fornecedor", models.CharField(blank=True, max_length=150)),
                ("valor_total", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("vencimento", models.DateField()),
                ("status", models.CharField(choices=[("ABERTA", "Em aberto"), ("PARCIAL", "Parcialmente paga"), ("QUITADA", "Quitada")], default="ABERTA", max_length=10)),
                ("observacao", models.TextField(blank=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_contapagar_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_contapagar_criados", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "tab_conta_pagar", "ordering": ["vencimento", "-criado_em"], "verbose_name": "conta a pagar", "verbose_name_plural": "contas a pagar"},
        ),
        migrations.CreateModel(
            name="BaixaContaPagar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("forma", models.CharField(choices=[("DINHEIRO", "Dinheiro"), ("PIX", "PIX"), ("CREDITO", "Cartão de crédito"), ("DEBITO", "Cartão de débito"), ("OUTRO", "Outro")], max_length=10)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("referencia", models.CharField(blank=True, max_length=100)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_baixacontapagar_atualizados", to=settings.AUTH_USER_MODEL)),
                ("caixa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="baixas_contas_pagar", to="atendimento.caixa")),
                ("conta", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="baixas", to="atendimento.contapagar")),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_baixacontapagar_criados", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "tab_baixa_conta_pagar", "ordering": ["-criado_em"], "verbose_name": "pagamento de conta a pagar", "verbose_name_plural": "pagamentos de contas a pagar"},
        ),
        migrations.AddConstraint(
            model_name="baixacontapagar",
            constraint=models.CheckConstraint(condition=models.Q(("valor__gt", 0)), name="ck_baixa_cp_valor_positivo"),
        ),
    ]
