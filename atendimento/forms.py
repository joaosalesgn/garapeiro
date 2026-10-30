from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.formats import number_format
from django.utils import timezone
from .models import (Adicional, BaixaContaPagar, Cliente, Comanda, ContaFinanceira, Fornecedor, Mesa, OperacaoFinanceira, Pagamento, Produto, Cupom)


class MoneyInput(forms.NumberInput):
    def __init__(self, attrs=None):
        atributos = {
            "data-money-mask": "true",
            "inputmode": "numeric",
            "autocomplete": "off",
        }
        if attrs:
            atributos.update(attrs)
        super().__init__(attrs=atributos)


class ContaFinanceiraForm(forms.ModelForm):
    class Meta:
        model = ContaFinanceira
        fields = ["tipo", "saldo_inicial", "ativa"]
        widgets = {"saldo_inicial": MoneyInput()}

    def clean(self):
        dados = super().clean()
        tipo = dados.get("tipo")
        if (tipo in (ContaFinanceira.Tipo.GAVETA, ContaFinanceira.Tipo.DINHEIRO) and ContaFinanceira.objects.filter(tipo=tipo, ativa=True).exists()):
            self.add_error("tipo", "Já existe uma conta ativa deste tipo.")
        return dados


class OperacaoFinanceiraForm(forms.ModelForm):
    class Meta:
        model = OperacaoFinanceira
        fields = ["tipo", "forma_pagamento", "conta_padrao", "taxa_percentual", "ativa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conta_padrao"].queryset = ContaFinanceira.objects.filter(ativa=True)
        self.fields["taxa_percentual"].help_text = "Taxa percentual aplicada somente quando o tipo for Recebimento."

    def clean(self):
        dados = super().clean()

        if (dados.get("tipo") == OperacaoFinanceira.Tipo.PAGAMENTO and dados.get("taxa_percentual") and dados["taxa_percentual"] != Decimal("0.000")):
            self.add_error("taxa_percentual", "Taxas não se aplicam às operações de pagamento.")

        if dados.get("tipo") and not dados.get("forma_pagamento"):
            self.add_error("forma_pagamento", "Informe a forma de pagamento desta operação.")

        if (dados.get("tipo") == OperacaoFinanceira.Tipo.RECEBIMENTO and dados.get("forma_pagamento") == Pagamento.Forma.DINHEIRO and dados.get("taxa_percentual") not in (None, Decimal("0.000"))):
            self.add_error("taxa_percentual", "Recebimento em dinheiro não pode ter taxa.")

        conta = dados.get("conta_padrao")
        forma = dados.get("forma_pagamento")
        if (dados.get("tipo") == OperacaoFinanceira.Tipo.RECEBIMENTO and conta and forma):
            tipo_esperado = (ContaFinanceira.Tipo.GAVETA if forma == Pagamento.Forma.DINHEIRO else ContaFinanceira.Tipo.BANCO)
            if conta.tipo != tipo_esperado:
                self.add_error("conta_padrao", "Dinheiro deve apontar para Gaveta; PIX e cartões devem apontar para Banco.")

        return dados


class TransferenciaForm(forms.Form):
    origem = forms.ModelChoiceField(queryset=ContaFinanceira.objects.filter(ativa=True), label="Conta de origem")
    destino = forms.ModelChoiceField(queryset=ContaFinanceira.objects.filter(ativa=True), label="Conta de destino")
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2, label="Valor", widget=MoneyInput())
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
        elif dados.get("canal") == Comanda.Canal.MESA and mesa and Comanda.objects.filter(mesa=mesa, status=Comanda.Status.ABERTA).exists():
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



class CupomForm(forms.ModelForm):
    class Meta:
        model = Cupom
        fields = ["codigo", "tipo_desconto", "valor_desconto", "valido_de", "valido_ate", "ativo"]
        widgets = {
            "valido_de": forms.DateInput(attrs={"type": "date"}),
            "valido_ate": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip().upper()

    def clean(self):
        dados = super().clean()
        if dados.get("tipo_desconto") == Cupom.TipoDesconto.PERCENTUAL and dados.get("valor_desconto") and dados["valor_desconto"] > 100:
            self.add_error("valor_desconto", "O percentual não pode ultrapassar 100%.")
        if dados.get("valido_de") and dados.get("valido_ate") and dados["valido_ate"] < dados["valido_de"]:
            self.add_error("valido_ate", "A data final não pode ser anterior à data inicial.")
        return dados


def _campos_desconto():
    return {
        "cupom": forms.ModelChoiceField(
            queryset=Cupom.objects.none(), required=False, label="Cupom",
            empty_label="Sem cupom", help_text="São exibidos somente cupons ativos e válidos hoje.",
        ),
        "desconto_percentual": forms.DecimalField(
            required=False, min_value=Decimal("0.01"), max_value=Decimal("100.00"),
            max_digits=5, decimal_places=2, label="Desconto (%)",
        ),
        "desconto_valor": forms.DecimalField(
            required=False, min_value=Decimal("0.00"), max_digits=10,
            decimal_places=2, widget=MoneyInput(attrs={"class": "form-control"}),
        )
    }


def _inicializar_cupons(form):
    form.fields["cupom"].queryset = Cupom.objects.filter(
        ativo=True, valido_de__lte=timezone.localdate(), valido_ate__gte=timezone.localdate()
    ).order_by("codigo")


class PagamentoForm(forms.Form):
    cupom = _campos_desconto()["cupom"]
    desconto_percentual = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        max_digits=5,
        decimal_places=2,
    )
    desconto_valor = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        max_digits=10,
        decimal_places=2,
        widget=MoneyInput(attrs={"class": "form-control"}),
    )
    forma = forms.ChoiceField(choices=(), label="Forma de recebimento", widget=forms.Select(attrs={"class": "form-select"}))
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2, label="Valor", widget=MoneyInput(attrs={"class": "form-control", "step": "0.01"}))
    referencia = forms.CharField(
        required=False,
        max_length=100,
        label="Referência",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Documento ou código da transação"}),
        help_text=("Opcional. Use para número do comprovante, nota fiscal ou código PIX; deixe em branco se não houver."),
    )

    def __init__(self, *args, operacoes=None, **kwargs):
        super().__init__(*args, **kwargs)
        _inicializar_cupons(self)
        operacoes = (
            operacoes
            if operacoes is not None
            else OperacaoFinanceira.objects.filter(tipo=OperacaoFinanceira.Tipo.RECEBIMENTO, ativa=True, conta_padrao__ativa=True).select_related("conta_padrao")
        )
        self.fields["forma"].choices = [("", "Selecione")] + list(
            dict.fromkeys(
                (op.forma_pagamento, op.get_forma_pagamento_display())
                for op in operacoes
            )
        )

    def clean_valor(self):
        valor = self.cleaned_data["valor"]
        if valor <= 0:
            raise ValidationError("O pagamento precisa ser maior que zero.")
        return valor


class AbrirCaixaForm(forms.Form):
    valor_inicial = forms.DecimalField(min_value=Decimal("0.00"), max_digits=10, decimal_places=2, initial=Decimal("0.00"), widget=MoneyInput())
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class FecharCaixaForm(forms.Form):
    valor_fechamento = forms.DecimalField(min_value=Decimal("0.00"), max_digits=10, decimal_places=2, label="Valor contado antes da sangria", widget=MoneyInput())
    valor_sangria = forms.DecimalField(min_value=Decimal("0.00"), max_digits=10, decimal_places=2, initial=Decimal("0.00"), label="Valor da sangria", widget=MoneyInput())
    observacao = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class MovimentacaoForm(forms.Form):
    tipo = forms.ChoiceField(choices=(("ENTRADA", "Entrada avulsa"), ("SAIDA", "Saída avulsa")))
    descricao = forms.CharField(max_length=150)
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2, widget=MoneyInput())


class EncerrarComandaForm(forms.Form):
    cupom = _campos_desconto()["cupom"]
    desconto_percentual = _campos_desconto()["desconto_percentual"]
    desconto_valor = _campos_desconto()["desconto_valor"]
    cliente = forms.ModelChoiceField(queryset=Cliente.objects.filter(ativo=True), required=False, label="Cliente")
    vencimento = forms.DateField(required=False, label="Vencimento", widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _inicializar_cupons(self)


class NovaContaPagarForm(forms.Form):
    descricao = forms.CharField(max_length=180, label="Descrição")
    fornecedor = forms.ModelChoiceField(queryset=Fornecedor.objects.filter(ativo=True).order_by("nome"), required=False, label="Fornecedor", empty_label="Selecione um fornecedor")
    valor_total = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2, label="Valor", widget=MoneyInput())
    vencimento = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Vencimento")
    observacao = forms.CharField(required=False, label="Observação", widget=forms.Textarea(attrs={"rows": 2}))


class BaixaContaPagarForm(forms.Form):
    conta_saida = forms.ModelChoiceField(queryset=ContaFinanceira.objects.filter(ativa=True), label="Conta de saída")
    forma = forms.ChoiceField(choices=(), label="Forma de pagamento")

    def __init__(self, *args, operacoes=None, **kwargs):
        super().__init__(*args, **kwargs)
        operacoes = (
            operacoes
            if operacoes is not None
            else OperacaoFinanceira.objects.filter(tipo=OperacaoFinanceira.Tipo.PAGAMENTO, ativa=True, conta_padrao__ativa=True)
        )
        self.fields["forma"].choices = list(
            dict.fromkeys(
                (op.forma_pagamento, op.get_forma_pagamento_display())
                for op in operacoes
            )
        )

    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2, label="Valor pago", widget=MoneyInput())
    referencia = forms.CharField(required=False, max_length=100, label="Referência", help_text=("Opcional. Informe o número do documento ou código da transação; deixe em branco se não houver."))