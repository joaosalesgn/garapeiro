from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrar_fornecedores(apps, schema_editor):
    ContaPagar = apps.get_model("atendimento", "ContaPagar")
    Fornecedor = apps.get_model("atendimento", "Fornecedor")
    banco = schema_editor.connection.alias
    nomes = ContaPagar.objects.using(banco).values_list("fornecedor", flat=True).distinct()
    registros = {}
    for valor in nomes:
        nome = (valor or "").strip()
        if nome:
            fornecedor, _ = Fornecedor.objects.using(banco).get_or_create(nome=nome)
            registros[valor] = fornecedor.pk
    for valor, fornecedor_id in registros.items():
        ContaPagar.objects.using(banco).filter(fornecedor=valor).update(fornecedor_rel_id=fornecedor_id)


def restaurar_fornecedores(apps, schema_editor):
    ContaPagar = apps.get_model("atendimento", "ContaPagar")
    Fornecedor = apps.get_model("atendimento", "Fornecedor")
    banco = schema_editor.connection.alias
    nomes = dict(Fornecedor.objects.using(banco).values_list("id", "nome"))
    for conta in ContaPagar.objects.using(banco).exclude(fornecedor_rel_id__isnull=True).iterator():
        ContaPagar.objects.using(banco).filter(pk=conta.pk).update(fornecedor=nomes.get(conta.fornecedor_rel_id, ""))


class Migration(migrations.Migration):
    dependencies = [
        ("atendimento", "0008_contas_financeiras"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Fornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=150)),
                ("telefone", models.CharField(blank=True, max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("documento", models.CharField(blank=True, max_length=30, verbose_name="CPF/CNPJ")),
                ("ativo", models.BooleanField(default=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_fornecedor_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_fornecedor_criados", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "tab_fornecedor", "ordering": ["nome"], "verbose_name": "fornecedor", "verbose_name_plural": "fornecedores"},
        ),
        migrations.AddField(
            model_name="contapagar", name="fornecedor_rel",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contas_pagar", to="atendimento.fornecedor"),
        ),
        migrations.RunPython(migrar_fornecedores, restaurar_fornecedores),
        migrations.RemoveField(model_name="contapagar", name="fornecedor"),
        migrations.RenameField(model_name="contapagar", old_name="fornecedor_rel", new_name="fornecedor"),
        migrations.AlterField(
            model_name="contapagar", name="fornecedor",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contas_pagar", to="atendimento.fornecedor"),
        ),
    ]
