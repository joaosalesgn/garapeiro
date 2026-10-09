# Generated manually for the initial local system structure.
import django.core.validators
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Adicional",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=100, unique=True)),
                ("preco", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("ativo", models.BooleanField(default=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_adicional_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_adicional_criados", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["nome"]},
        ),
        migrations.CreateModel(
            name="Cliente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=150)),
                ("telefone", models.CharField(blank=True, max_length=30)),
                ("observacao", models.TextField(blank=True)),
                ("ativo", models.BooleanField(default=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_cliente_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_cliente_criados", to=settings.AUTH_USER_MODEL)),
            ], options={"ordering": ["nome"]},
        ),
        migrations.CreateModel(
            name="Mesa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("numero", models.PositiveSmallIntegerField(unique=True, validators=[django.core.validators.MinValueValidator(1)])),
                ("ativa", models.BooleanField(default=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_mesa_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_mesa_criados", to=settings.AUTH_USER_MODEL)),
            ], options={"ordering": ["numero"]},
        ),
        migrations.CreateModel(
            name="Produto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=120, unique=True)),
                ("categoria", models.CharField(blank=True, max_length=80)),
                ("preco", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("ativo", models.BooleanField(default=True)),
                ("vai_para_cozinha", models.BooleanField(default=False)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_produto_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_produto_criados", to=settings.AUTH_USER_MODEL)),
            ], options={"ordering": ["categoria", "nome"]},
        ),
        migrations.CreateModel(
            name="TipoMovimentacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(max_length=100, unique=True)),
                ("ativo", models.BooleanField(default=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_tipomovimentacao_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_tipomovimentacao_criados", to=settings.AUTH_USER_MODEL)),
            ], options={"ordering": ["nome"], "verbose_name": "tipo de movimentação", "verbose_name_plural": "tipos de movimentação"},
        ),
        migrations.CreateModel(
            name="ProdutoAdicional",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_produtoadicional_atualizados", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atendimento_produtoadicional_criados", to=settings.AUTH_USER_MODEL)),
                ("adicional", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="produtos_permitidos", to="atendimento.adicional")),
                ("produto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="adicionais_permitidos", to="atendimento.produto")),
            ],
            options={"ordering": ["produto__nome", "adicional__nome"]},
        ),
        migrations.AddConstraint(
            model_name="produtoadicional",
            constraint=models.UniqueConstraint(fields=("produto", "adicional"), name="uq_produto_adicional"),
        ),
    ]
