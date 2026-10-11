from django.contrib import admin
from .models import (
    Adicional, Caixa, Categoria, Cliente, Comanda, ComandaItem,
    ItemAdicional, Mesa, MovimentacaoCaixa, Pagamento, Produto,
    ProdutoAdicional, TipoMovimentacao, ContaReceber, ContaPagar, BaixaContaPagar,
)


class CriadoAtualizadoAdmin(admin.ModelAdmin):
    readonly_fields = ("criado_em", "atualizado_em", "criado_por", "atualizado_por")
    list_per_page = 50

    def save_model(self, request, obj, form, change):
        if not change and hasattr(obj, "criado_por_id") and not obj.criado_por_id:
            obj.criado_por = request.user
        if hasattr(obj, "atualizado_por_id"):
            obj.atualizado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(Categoria)
class CategoriaAdmin(CriadoAtualizadoAdmin):
    list_display = ("nome", "ativa", "criado_em", "atualizado_em")
    list_filter = ("ativa",)
    search_fields = ("nome",)


@admin.register(Produto)
class ProdutoAdmin(CriadoAtualizadoAdmin):
    list_display = ("nome", "categoria", "preco", "vai_para_cozinha", "ativo")
    list_filter = ("categoria", "vai_para_cozinha", "ativo")
    search_fields = ("nome", "categoria__nome")


@admin.register(Adicional)
class AdicionalAdmin(CriadoAtualizadoAdmin):
    list_display = ("nome", "preco", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(ProdutoAdicional)
class ProdutoAdicionalAdmin(CriadoAtualizadoAdmin):
    list_display = ("produto", "adicional")
    list_select_related = ("produto", "adicional")
    search_fields = ("produto__nome", "adicional__nome")


@admin.register(Mesa)
class MesaAdmin(CriadoAtualizadoAdmin):
    list_display = ("numero", "ativa")
    list_filter = ("ativa",)


@admin.register(Cliente)
class ClienteAdmin(CriadoAtualizadoAdmin):
    list_display = ("nome", "telefone", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "telefone")


@admin.register(TipoMovimentacao)
class TipoMovimentacaoAdmin(CriadoAtualizadoAdmin):
    list_display = ("nome", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome",)


class ItemAdicionalInline(admin.TabularInline):
    model = ItemAdicional
    extra = 0


class ComandaItemInline(admin.TabularInline):
    model = ComandaItem
    extra = 0
    show_change_link = True


class PagamentoInline(admin.TabularInline):
    model = Pagamento
    extra = 0


@admin.register(Comanda)
class ComandaAdmin(CriadoAtualizadoAdmin):
    list_display = ("id", "status", "canal", "mesa", "cliente", "criado_em", "total", "total_pago", "saldo")
    list_filter = ("status", "canal", "criado_em")
    search_fields = ("id", "cliente__nome", "mesa__numero")
    list_select_related = ("mesa", "cliente")
    inlines = (ComandaItemInline, PagamentoInline)
    readonly_fields = CriadoAtualizadoAdmin.readonly_fields + ("cancelado_em", "cancelado_por")


@admin.register(ComandaItem)
class ComandaItemAdmin(CriadoAtualizadoAdmin):
    list_display = ("comanda", "produto_nome", "quantidade", "preco_unitario", "status_producao")
    list_filter = ("status_producao", "criado_em")
    search_fields = ("produto_nome", "comanda__id")
    list_select_related = ("comanda", "produto")
    inlines = (ItemAdicionalInline,)


@admin.register(Caixa)
class CaixaAdmin(CriadoAtualizadoAdmin):
    list_display = ("id", "status", "aberto_em", "fechado_em", "valor_inicial", "valor_fechamento")
    list_filter = ("status", "aberto_em")
    readonly_fields = CriadoAtualizadoAdmin.readonly_fields + ("aberto_em",)


@admin.register(Pagamento)
class PagamentoAdmin(CriadoAtualizadoAdmin):
    list_display = ("comanda", "caixa", "forma", "valor", "criado_em")
    list_filter = ("forma", "criado_em")
    search_fields = ("comanda__id", "referencia")
    list_select_related = ("comanda", "caixa")


@admin.register(MovimentacaoCaixa)
class MovimentacaoCaixaAdmin(CriadoAtualizadoAdmin):
    list_display = ("caixa", "tipo", "descricao", "valor", "criado_em")
    list_filter = ("tipo", "criado_em")
    search_fields = ("descricao",)
    list_select_related = ("caixa",)


@admin.register(ContaReceber)
class ContaReceberAdmin(CriadoAtualizadoAdmin):
    list_display = ("id", "comanda", "cliente", "valor_total", "vencimento", "status")
    list_filter = ("status", "vencimento")
    search_fields = ("comanda__id", "cliente__nome")
    list_select_related = ("comanda", "cliente")


class BaixaContaPagarInline(admin.TabularInline):
    model = BaixaContaPagar
    extra = 0


@admin.register(ContaPagar)
class ContaPagarAdmin(CriadoAtualizadoAdmin):
    list_display = ("id", "descricao", "fornecedor", "valor_total", "vencimento", "status")
    list_filter = ("status", "vencimento")
    search_fields = ("descricao", "fornecedor")
    inlines = (BaixaContaPagarInline,)


@admin.register(BaixaContaPagar)
class BaixaContaPagarAdmin(CriadoAtualizadoAdmin):
    list_display = ("conta", "caixa", "forma", "valor", "criado_em")
    list_filter = ("forma", "criado_em")
    list_select_related = ("conta", "caixa")
