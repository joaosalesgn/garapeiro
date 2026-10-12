"""Modelos do atendimento, comandas e caixa; valores monetários usam DecimalField."""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum


class RegistroBase(models.Model):
    """Campos de auditoria comuns, mantidos em tabelas concretas."""
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_criados", null=True, blank=True,
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_atualizados", null=True, blank=True,
    )

    class Meta:
        abstract = True


class RegistroCancelavel(RegistroBase):
    """Auditoria de cancelamento lógico, sem apagar histórico financeiro."""
    cancelado_em = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_cancelados", null=True, blank=True,
    )
    motivo_cancelamento = models.TextField(blank=True)

    class Meta:
        abstract = True


class Categoria(RegistroBase):
    nome = models.CharField(max_length=80, unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "tab_categoria"
        ordering = ["nome"]
        verbose_name = "categoria"
        verbose_name_plural = "categorias"

    def __str__(self):
        return self.nome


class Produto(RegistroBase):
    nome = models.CharField(max_length=120)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="produtos")
    preco = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    ativo = models.BooleanField(default=True)
    vai_para_cozinha = models.BooleanField(default=False)

    class Meta:
        db_table = "tab_produto"
        ordering = ["categoria__nome", "nome"]
        constraints = [models.UniqueConstraint(fields=["categoria", "nome"], name="uniq_produto_categoria_nome")]

    def __str__(self):
        return self.nome


class Adicional(RegistroBase):
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "tab_adicional"
        ordering = ["nome"]
        verbose_name_plural = "adicionais"

    def __str__(self):
        return self.nome


class ProdutoAdicional(RegistroBase):
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="adicionais_permitidos")
    adicional = models.ForeignKey(Adicional, on_delete=models.PROTECT, related_name="produtos_permitidos")

    class Meta:
        db_table = "tab_produto_adicional"
        constraints = [models.UniqueConstraint(fields=["produto", "adicional"], name="uq_produto_adicional")]
        ordering = ["produto__nome", "adicional__nome"]

    def __str__(self):
        return f"{self.produto} — {self.adicional}"


class Mesa(RegistroBase):
    numero = models.PositiveSmallIntegerField(unique=True, validators=[MinValueValidator(1)])
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "tab_mesa"
        ordering = ["numero"]

    def __str__(self):
        return f"Mesa {self.numero}"


class Cliente(RegistroBase):
    nome = models.CharField(max_length=150)
    telefone = models.CharField(max_length=30, blank=True)
    observacao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "tab_cliente"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class TipoMovimentacao(RegistroBase):
    nome = models.CharField(max_length=100, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "tab_tipo_movimentacao"
        ordering = ["nome"]
        verbose_name = "tipo de movimentação"
        verbose_name_plural = "tipos de movimentação"

    def __str__(self):
        return self.nome


class Caixa(RegistroBase):
    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        FECHADO = "FECHADO", "Fechado"

    aberto_em = models.DateTimeField(auto_now_add=True)
    fechado_em = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTO)
    valor_inicial = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)])
    valor_fechamento = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    observacao = models.TextField(blank=True)
    fechado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="caixas_fechados", null=True, blank=True)

    class Meta:
        db_table = "tab_caixa"
        ordering = ["-aberto_em"]
        constraints = [
            models.UniqueConstraint(fields=["status"], condition=Q(status="ABERTO"), name="uq_caixa_unico_aberto"),
            models.CheckConstraint(condition=Q(valor_inicial__gte=0), name="ck_caixa_valor_inicial"),
            models.CheckConstraint(condition=Q(valor_fechamento__isnull=True) | Q(valor_fechamento__gte=0), name="ck_caixa_valor_fechamento"),
        ]
        verbose_name = "caixa"
        verbose_name_plural = "caixas"

    def __str__(self):
        return f"Caixa {self.pk} — {self.get_status_display()}"


class Comanda(RegistroCancelavel):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        FECHADA = "FECHADA", "Fechada"
        CANCELADA = "CANCELADA", "Cancelada"

    class Canal(models.TextChoices):
        MESA = "MESA", "Mesa"
        BALCAO = "BALCAO", "Balcão/retirada"
        ENTREGA = "ENTREGA", "Entrega"

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA)
    canal = models.CharField(max_length=10, choices=Canal.choices, default=Canal.MESA)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="comandas", null=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="comandas", null=True, blank=True)
    fechada_em = models.DateTimeField(null=True, blank=True)
    observacao = models.TextField(blank=True)

    class Meta:
        db_table = "tab_comanda"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["status", "criado_em"], name="ix_comanda_status_data")]
        verbose_name = "comanda"
        verbose_name_plural = "comandas"

    def __str__(self):
        return f"Comanda {self.pk} — {self.get_status_display()}"

    @property
    def total(self):
        valor_item = models.DecimalField(max_digits=12, decimal_places=2)
        itens_validos = self.itens.exclude(status_producao=ComandaItem.StatusProducao.CANCELADO)
        produtos = itens_validos.aggregate(
            valor=Sum(models.F("preco_unitario") * models.F("quantidade"), output_field=valor_item)
        )["valor"] or Decimal("0.00")
        adicionais = ItemAdicional.objects.filter(
            item__comanda=self
        ).exclude(item__status_producao=ComandaItem.StatusProducao.CANCELADO).aggregate(
            valor=Sum(models.F("preco_unitario") * models.F("quantidade"), output_field=valor_item)
        )["valor"] or Decimal("0.00")
        return produtos + adicionais

    @property
    def total_pago(self):
        return self.pagamentos.aggregate(valor=Sum("valor"))["valor"] or Decimal("0.00")

    @property
    def saldo(self):
        return self.total - self.total_pago


class ComandaItem(RegistroBase):
    class StatusProducao(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        ENVIADO = "ENVIADO", "Enviado à cozinha"
        PRONTO = "PRONTO", "Pronto"
        CANCELADO = "CANCELADO", "Cancelado"

    comanda = models.ForeignKey(Comanda, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="itens_comanda")
    produto_nome = models.CharField(max_length=120, help_text="Nome registrado na venda, preservado como histórico.")
    quantidade = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    status_producao = models.CharField(max_length=10, choices=StatusProducao.choices, default=StatusProducao.PENDENTE)
    observacao = models.CharField(max_length=250, blank=True)

    class Meta:
        db_table = "tab_comanda_item"
        ordering = ["criado_em", "id"]
        indexes = [models.Index(fields=["comanda", "status_producao"], name="ix_item_comanda_status")]
        constraints = [
            models.CheckConstraint(condition=Q(quantidade__gte=1), name="ck_item_quantidade_positiva"),
            models.CheckConstraint(condition=Q(preco_unitario__gte=0), name="ck_item_preco_nao_negativo"),
        ]
        verbose_name = "item da comanda"
        verbose_name_plural = "itens da comanda"

    def __str__(self):
        return f"{self.quantidade} × {self.produto_nome}"

    @property
    def total(self):
        return self.preco_unitario * self.quantidade


class ItemAdicional(RegistroBase):
    item = models.ForeignKey(ComandaItem, on_delete=models.CASCADE, related_name="adicionais")
    adicional = models.ForeignKey(Adicional, on_delete=models.PROTECT, related_name="itens_vendidos")
    adicional_nome = models.CharField(max_length=100, help_text="Nome registrado na venda para preservar o histórico.")
    quantidade = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        db_table = "tab_item_adicional"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantidade__gte=1), name="ck_adic_quantidade_positiva"),
            models.CheckConstraint(condition=Q(preco_unitario__gte=0), name="ck_adic_preco_nao_negativo"),
        ]
        verbose_name = "adicional vendido"
        verbose_name_plural = "adicionais vendidos"

    def __str__(self):
        return f"{self.quantidade} × {self.adicional_nome}"

    @property
    def total(self):
        return self.preco_unitario * self.quantidade


class Pagamento(RegistroBase):
    class Forma(models.TextChoices):
        DINHEIRO = "DINHEIRO", "Dinheiro"
        PIX = "PIX", "PIX"
        CREDITO = "CREDITO", "Cartão de crédito"
        DEBITO = "DEBITO", "Cartão de débito"
        OUTRO = "OUTRO", "Outro"

    comanda = models.ForeignKey(Comanda, on_delete=models.PROTECT, related_name="pagamentos")
    caixa = models.ForeignKey(Caixa, on_delete=models.PROTECT, related_name="pagamentos")
    forma = models.CharField(max_length=10, choices=Forma.choices)
    valor = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    referencia = models.CharField(max_length=100, blank=True, help_text="Opcional; por exemplo, identificador da transação.")

    class Meta:
        db_table = "tab_pagamento"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["caixa", "forma"], name="ix_pag_caixa_forma")]
        constraints = [models.CheckConstraint(condition=Q(valor__gt=0), name="ck_pagamento_valor_positivo")]
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"

    def __str__(self):
        return f"{self.get_forma_display()} — R$ {self.valor}"


class MovimentacaoCaixa(RegistroBase):
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada avulsa"
        SAIDA = "SAIDA", "Saída"

    caixa = models.ForeignKey(Caixa, on_delete=models.PROTECT, related_name="movimentacoes")
    tipo = models.CharField(max_length=7, choices=Tipo.choices)
    descricao = models.CharField(max_length=150)
    valor = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])

    class Meta:
        db_table = "tab_movimentacao_caixa"
        ordering = ["-criado_em"]
        constraints = [models.CheckConstraint(condition=Q(valor__gt=0), name="ck_mov_caixa_valor_positivo")]
        verbose_name = "movimentação de caixa"
        verbose_name_plural = "movimentações de caixa"

    def __str__(self):
        return f"{self.get_tipo_display()} — R$ {self.valor}"


class ContaReceber(RegistroBase):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Em aberto"
        PARCIAL = "PARCIAL", "Parcialmente recebida"
        QUITADA = "QUITADA", "Quitada"

    comanda = models.OneToOneField(Comanda, on_delete=models.PROTECT, related_name="conta_receber")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="contas_receber", null=True, blank=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    vencimento = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA)
    observacao = models.TextField(blank=True)

    class Meta:
        db_table = "tab_conta_receber"
        ordering = ["vencimento", "-criado_em"]
        verbose_name = "conta a receber"
        verbose_name_plural = "contas a receber"

    @property
    def total_recebido(self):
        return self.comanda.pagamentos.aggregate(valor=Sum("valor"))["valor"] or Decimal("0.00")

    @property
    def saldo(self):
        return max(self.valor_total - self.total_recebido, Decimal("0.00"))

    def atualizar_status(self):
        recebido = self.total_recebido
        self.status = self.Status.QUITADA if recebido >= self.valor_total else (
            self.Status.PARCIAL if recebido > 0 else self.Status.ABERTA
        )
        self.save(update_fields=["status", "atualizado_em"])

    def __str__(self):
        return f"CR #{self.pk} — Comanda #{self.comanda_id}"


class Fornecedor(RegistroBase):
    """Cadastro reutilizável de fornecedores para as contas a pagar."""
    nome = models.CharField(max_length=150)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    documento = models.CharField(max_length=30, blank=True, verbose_name="CPF/CNPJ")
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "tab_fornecedor"
        ordering = ["nome"]
        verbose_name = "fornecedor"
        verbose_name_plural = "fornecedores"

    def __str__(self):
        return self.nome


class ContaPagar(RegistroBase):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Em aberto"
        PARCIAL = "PARCIAL", "Parcialmente paga"
        QUITADA = "QUITADA", "Quitada"

    descricao = models.CharField(max_length=180)
    fornecedor = models.ForeignKey(
        Fornecedor, on_delete=models.SET_NULL, related_name="contas_pagar",
        null=True, blank=True,
    )
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    vencimento = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA)
    observacao = models.TextField(blank=True)

    class Meta:
        db_table = "tab_conta_pagar"
        ordering = ["vencimento", "-criado_em"]
        verbose_name = "conta a pagar"
        verbose_name_plural = "contas a pagar"

    @property
    def total_pago(self):
        return self.baixas.aggregate(valor=Sum("valor"))["valor"] or Decimal("0.00")

    @property
    def saldo(self):
        return max(self.valor_total - self.total_pago, Decimal("0.00"))

    def atualizar_status(self):
        pago = self.total_pago
        self.status = self.Status.QUITADA if pago >= self.valor_total else (
            self.Status.PARCIAL if pago > 0 else self.Status.ABERTA
        )
        self.save(update_fields=["status", "atualizado_em"])

    def __str__(self):
        return f"CP #{self.pk} — {self.descricao}"


class BaixaContaPagar(RegistroBase):
    class Forma(models.TextChoices):
        DINHEIRO = "DINHEIRO", "Dinheiro"
        PIX = "PIX", "PIX"
        CREDITO = "CREDITO", "Cartão de crédito"
        DEBITO = "DEBITO", "Cartão de débito"
        OUTRO = "OUTRO", "Outro"

    conta = models.ForeignKey(ContaPagar, on_delete=models.PROTECT, related_name="baixas")
    caixa = models.ForeignKey(Caixa, on_delete=models.PROTECT, related_name="baixas_contas_pagar")
    forma = models.CharField(max_length=10, choices=Forma.choices)
    valor = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    referencia = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "tab_baixa_conta_pagar"
        ordering = ["-criado_em"]
        constraints = [models.CheckConstraint(condition=Q(valor__gt=0), name="ck_baixa_cp_valor_positivo")]
        verbose_name = "pagamento de conta a pagar"
        verbose_name_plural = "pagamentos de contas a pagar"
