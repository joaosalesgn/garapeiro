from django import forms

from .models import Adicional, Cliente, Comanda, Mesa, Produto


class ComandaForm(forms.ModelForm):
    class Meta:
        model = Comanda
        fields = ("canal", "mesa", "cliente", "observacao")
        widgets = {"observacao": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mesa"].queryset = Mesa.objects.filter(ativa=True)
        self.fields["mesa"].required = False
        self.fields["cliente"].queryset = Cliente.objects.filter(ativo=True)
        self.fields["cliente"].required = False
        self.fields["mesa"].empty_label = "Selecione uma mesa"
        self.fields["cliente"].empty_label = "Sem cliente vinculado"

    def clean(self):
        cleaned_data = super().clean()
        canal = cleaned_data.get("canal")
        mesa = cleaned_data.get("mesa")
        if canal == Comanda.Canal.MESA and mesa is None:
            self.add_error("mesa", "Selecione a mesa para atendimento no salão.")
        if canal != Comanda.Canal.MESA and mesa is not None:
            cleaned_data["mesa"] = None
        return cleaned_data


class AdicionarItemForm(forms.Form):
    produto = forms.ModelChoiceField(
        queryset=Produto.objects.none(),
        empty_label="Selecione um produto",
        label="Produto",
    )
    adicionais = forms.ModelMultipleChoiceField(
        queryset=Adicional.objects.none(),
        required=False,
        label="Adicionais",
        widget=forms.CheckboxSelectMultiple,
    )
    quantidade = forms.IntegerField(min_value=1, max_value=999, initial=1, label="Quantidade")
    observacao = forms.CharField(
        required=False,
        max_length=250,
        label="Observação do item",
        widget=forms.TextInput(attrs={"placeholder": "Ex.: sem cebola"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["produto"].queryset = Produto.objects.filter(ativo=True).select_related("categoria")
        self.fields["produto"].label_from_instance = lambda produto: (
            f"{produto.categoria.nome} — {produto.nome} (R$ {produto.preco:.2f})"
        )
        self.fields["adicionais"].queryset = Adicional.objects.filter(ativo=True).order_by("nome")
        self.fields["adicionais"].label_from_instance = lambda adicional: (
            f"{adicional.nome} (+ R$ {adicional.preco:.2f})"
        )

    def clean(self):
        cleaned_data = super().clean()
        produto = cleaned_data.get("produto")
        adicionais = cleaned_data.get("adicionais")
        if produto and adicionais:
            permitidos = set(produto.adicionais_permitidos.values_list("adicional_id", flat=True))
            nao_vinculados = [adicional.nome for adicional in adicionais if adicional.pk not in permitidos]
            if nao_vinculados:
                self.add_error(
                    "adicionais",
                    "Estes adicionais não estão vinculados ao produto: " + ", ".join(nao_vinculados),
                )
        return cleaned_data
