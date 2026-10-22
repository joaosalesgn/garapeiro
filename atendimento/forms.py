from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.formats import number_format
from .models import Adicional, Cliente, Comanda, Fornecedor, Mesa, Pagamento, Produto, BaixaContaPagar, ContaFinanceira, OperacaoFinanceira


class ContaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = ContaFinanceira
        fields = ["nome", "tipo", "saldo_inicial", "ativa"]


class OperacaoFinanceiraForm(forms.ModelForm):
    class Meta:
        model = OperacaoFinanceira
        fields = ["nome", "tipo", "forma_pagamento", "conta_padrao", "taxa_percentual", "ativa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conta_padrao"].queryset = ContaFinanceira.objects.filter(ativa=True)
        self.fields["taxa_percentual"].help_text = "Taxa percentual aplicada somente quando o tipo for Recebimento."

    def clean(self):
        dados = super().clean()
        if dados.get("tipo") == OperacaoFinanceira.Tipo.PAGAMENTO and dados.get("taxa_percentual"):
            if dados["taxa_percentual"] != Decimal("0.000"):
                self.add_error("taxa_percentual", "Taxas não se aplicam às operações de pagamento.")
        if dados.get("tipo") == OperacaoFinanceira.Tipo.RECEBIMENTO and not dados.get("forma_pagamento"):
            self.add_error("forma_pagamento", "Informe a forma de pagamento para a operação de recebimento.")
        if dados.get("tipo") == OperacaoFinanceira.Tipo.RECEBIMENTO and dados.get("forma_pagamento") == Pagamento.Forma.DINHEIRO and dados.get("taxa_percentual") not in (None, Decimal("0.000")):
            self.add_error("taxa_percentual", "Recebimento em dinheiro não pode ter taxa.")
        conta = dados.get("conta_padrao")
        forma = dados.get("forma_pagamento")
        if dados.get("tipo") == OperacaoFinanceira.Tipo.RECEBIMENTO and conta and forma:
            tipo_esperado = ContaFinanceira.Tipo.GAVETA if forma == Pagamento.Forma.DINHEIRO else ContaFinanceira.Tipo.BANCO
            if conta.tipo != tipo_esperado:
                self.add_error("conta_padrao", "Dinheiro deve apontar para Gaveta; PIX e cartões devem apontar para Banco.")
        return dados


class TransferenciaForm(forms.Form):
    origem = forms.ModelChoiceField(queryset=ContaFinanceira.objects.filter(ativa=True), label="Conta de origem")
    destino = forms.ModelChoiceField(queryset=ContaFinanceira.objects.filter(ativa=True), label="Conta de destino")
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2, label="Valor")
    descricao = forms.CharField(max_length=180, initial="Sangria", label="Descrição")

    def clean(self):
        dados = super().clean()
        if dados.get("origem") and dados.get("destino") and dados["origem"] == dados["destino"]:
            self.add_error("destino", "A conta de origem e destino devem ser diferentes.")
        return dados


class NovaComandaForm(forms.Form):
    canal = forms.ChoiceField(choices=Comanda.Canal.choices, initial=Comanda.Canal.MESA)
    mesa = forms.ModelChoiceField(queryset=Mesa.objects.filter(ativa=True), required=False)
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.filter(ativo=True), required=False)
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def clean(self):
        dados = super().clean()
        if dados.get("canal") == Comanda.Canal.MESA and not dados.get("mesa"):
            self.add_error("mesa", "Selecione uma mesa para atendimento no salão.")
        mesa = dados.get("mesa")
        if dados.get("canal") != Comanda.Canal.MESA and mesa:
            self.add_error("mesa", "Mesa só deve ser informada para atendimento no salão.")
        elif dados.get("canal") == Comanda.Canal.MESA and mesa and Comanda.objects.filter(
            mesa=mesa, status=Comanda.Status.ABERTA
        ).exists():
            self.add_error("mesa", "Já existe uma comanda aberta nesta mesa.")
        return dados


class AdicionarItemForm(forms.Form):
    produto = forms.ModelChoiceField(queryset=Produto.objects.filter(ativo=True).select_related("categoria"))
    quantidade = forms.IntegerField(min_value=1, max_value=999, initial=1)
    adicionais = forms.ModelMultipleChoiceField(queryset=Adicional.objects.none(), required=False)
    observacao = forms.CharField(required=False, max_length=250)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["produto"].label_from_instance = lambda produto: (f"{produto.nome} ——— {produto.categoria.nome} —— " f"R$ {number_format(produto.preco, decimal_pos=2, use_l10n=True)}")

        campo_adicionais = self.fields["adicionais"]
        campo_adicionais.widget = forms.CheckboxSelectMultiple()
        campo_adicionais.label_from_instance = lambda adicional: (f"{adicional.nome} — R$ " f"{number_format(adicional.preco, decimal_pos=2, use_l10n=True)}")

        produto_id = self.data.get("produto") or self.initial.get("produto")
        if produto_id:
            campo_adicionais.queryset = Adicional.objects.filter(ativo=True, produtos_permitidos__produto_id=produto_id).distinct().order_by("nome")

    def clean(self):
        dados = super().clean()
        produto = dados.get("produto")
        adicionais = dados.get("adicionais")
        if produto and adicionais:
            permitidos = set(produto.adicionais_permitidos.values_list("adicional_id", flat=True))
            if any(adicional.pk not in permitidos for adicional in adicionais):
                raise ValidationError("Um ou mais adicionais não estão habilitados para este produto.")
        return dados


class PagamentoForm(forms.Form):
    forma = forms.ChoiceField(choices=Pagamento.Forma.choices, label="Forma de pagamento", widget=forms.Select(attrs={"class": "form-select"}))
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2, label="Valor", widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "inputmode": "decimal"}))
    referencia = forms.CharField(required=False, max_length=100, label="Referência", widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Documento ou código da transação"}), help_text="Opcional. Use para número do comprovante, nota fiscal ou código PIX; deixe em branco se não houver.")

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if valor <= 0:
            raise ValidationError("O pagamento precisa ser maior que zero.")
        return valor


class AbrirCaixaForm(forms.Form):
    valor_inicial = forms.DecimalField(min_value=Decimal("0.00"), max_digits=10, decimal_places=2, initial=Decimal("0.00"))
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class FecharCaixaForm(forms.Form):
    valor_fechamento = forms.DecimalField(min_value=Decimal("0.00"), max_digits=10, decimal_places=2)
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class MovimentacaoForm(forms.Form):
    tipo = forms.ChoiceField(choices=(("ENTRADA", "Entrada avulsa"), ("SAIDA", "Saída")))
    descricao = forms.CharField(max_length=150)
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2)


class EncerrarComandaForm(forms.Form):
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.filter(ativo=True), required=False, label="Cliente")
    vencimento = forms.DateField(required=False, label="Vencimento", widget=forms.DateInput(attrs={"type": "date"}))


class NovaContaPagarForm(forms.Form):
    descricao = forms.CharField(max_length=180, label="Descrição")
    fornecedor = forms.ModelChoiceField(
        queryset=Fornecedor.objects.filter(ativo=True).order_by("nome"),
        required=False, label="Fornecedor", empty_label="Selecione um fornecedor",
    )
    valor_total = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2, label="Valor")
    vencimento = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Vencimento")
    observacao = forms.CharField(required=False, label="Observação", widget=forms.Textarea(attrs={"rows": 2}))


class BaixaContaPagarForm(forms.Form):
    conta_saida = forms.ModelChoiceField(queryset=ContaFinanceira.objects.filter(ativa=True, tipo__in=[ContaFinanceira.Tipo.BANCO, ContaFinanceira.Tipo.DINHEIRO]), label="Conta de saída")
    forma = forms.ChoiceField(choices=BaixaContaPagar.Forma.choices, label="Forma de pagamento")
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2, label="Valor pago")
    referencia = forms.CharField(
        required=False, max_length=100, label="Referência",
        help_text="Opcional. Informe o número do documento ou código da transação; deixe em branco se não houver.",
    )
