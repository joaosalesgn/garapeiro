from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Adicional, Cliente, Comanda, Mesa, Pagamento, Produto


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


class AdicionalChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.nome} — R$ {obj.preco:.2f}"


class AdicionarItemForm(forms.Form):
    produto = forms.ModelChoiceField(queryset=Produto.objects.filter(ativo=True).select_related("categoria"))
    quantidade = forms.IntegerField(min_value=1, max_value=999, initial=1)
    adicionais = AdicionalChoiceField(
        queryset=Adicional.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    observacao = forms.CharField(required=False, max_length=250)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        produto_id = self.data.get("produto") or self.initial.get("produto")
        if produto_id:
            self.fields["adicionais"].queryset = Adicional.objects.filter(
                ativo=True, produtos_permitidos__produto_id=produto_id
            ).distinct().order_by("nome")

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
    forma = forms.ChoiceField(choices=Pagamento.Forma.choices)
    valor = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2)
    referencia = forms.CharField(required=False, max_length=100)

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
