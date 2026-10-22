from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from .status_services import set_product_active, set_user_active

from django.contrib import admin
from .models import (
    Adicional, Caixa, Categoria, Cliente, Comanda, ComandaItem,
    ItemAdicional, Mesa, MovimentacaoCaixa, Pagamento, Produto,
    ProdutoAdicional, TipoMovimentacao, ContaReceber, ContaPagar, BaixaContaPagar, Fornecedor,
    ContaFinanceira, OperacaoFinanceira, LancamentoTesouraria, StatusAuditEvent
)
User = get_user_model()


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
    actions = ("inativar_produtos", "reativar_produtos")

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + ("ativo",)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Inativar produtos selecionados")
    def inativar_produtos(self, request, queryset):
        if not request.user.has_perm("atendimento.change_produto"):
            raise PermissionDenied

        alterados = 0
        for product_id in queryset.values_list("pk", flat=True):
            alterados += bool(
                set_product_active(product_id=product_id, active=False, actor=request.user)
            )

        self.message_user(request, f"{alterados} produto(s) inativado(s).", messages.SUCCESS)

    @admin.action(description="Reativar produtos selecionados")
    def reativar_produtos(self, request, queryset):
        if not request.user.has_perm("atendimento.change_produto"):
            raise PermissionDenied

        alterados = 0
        for product_id in queryset.values_list("pk", flat=True):
            alterados += bool(
                set_product_active(product_id=product_id, active=True, actor=request.user)
            )

        self.message_user(request, f"{alterados} produto(s) reativado(s).", messages.SUCCESS)


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


@admin.register(ContaFinanceira)
class ContaFinanceiraAdmin(CriadoAtualizadoAdmin):
    list_display = ("nome", "tipo", "saldo_inicial", "ativa")
    list_filter = ("tipo", "ativa")
    search_fields = ("nome",)


@admin.register(OperacaoFinanceira)
class OperacaoFinanceiraAdmin(CriadoAtualizadoAdmin):
    list_display = ("nome", "tipo", "forma_pagamento", "conta_padrao", "taxa_percentual", "ativa")
    list_filter = ("tipo", "ativa")
    search_fields = ("nome",)


@admin.register(LancamentoTesouraria)
class LancamentoTesourariaAdmin(CriadoAtualizadoAdmin):
    list_display = ("criado_em", "conta", "tipo", "descricao", "valor_bruto", "taxa", "valor")
    list_filter = ("tipo", "conta", "criado_em")
    search_fields = ("descricao", "referencia")
    readonly_fields = CriadoAtualizadoAdmin.readonly_fields + ("conta", "caixa", "tipo", "descricao", "valor_bruto", "taxa", "valor", "pagamento", "baixa_cp", "transferencia", "referencia")


@admin.register(ContaReceber)
class ContaReceberAdmin(CriadoAtualizadoAdmin):
    list_display = ("id", "comanda", "cliente", "valor_total", "vencimento", "status")
    list_filter = ("status", "vencimento")
    search_fields = ("comanda__id", "cliente__nome")
    list_select_related = ("comanda", "cliente")


class BaixaContaPagarInline(admin.TabularInline):
    model = BaixaContaPagar
    extra = 0


@admin.register(Fornecedor)
class FornecedorAdmin(CriadoAtualizadoAdmin):
    list_display = ("nome", "documento", "telefone", "email", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "documento", "telefone", "email")


@admin.register(ContaPagar)
class ContaPagarAdmin(CriadoAtualizadoAdmin):
    list_display = ("id", "descricao", "fornecedor", "valor_total", "vencimento", "status")
    list_filter = ("status", "vencimento")
    search_fields = ("descricao", "fornecedor__nome")
    inlines = (BaixaContaPagarInline,)


@admin.register(BaixaContaPagar)
class BaixaContaPagarAdmin(CriadoAtualizadoAdmin):
    list_display = ("conta", "caixa", "forma", "valor", "criado_em")
    list_filter = ("forma", "criado_em")
    list_select_related = ("conta", "caixa")


class ProtectedUserAdmin(DjangoUserAdmin):
    actions = ("inativar_usuarios", "reativar_usuarios")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if "is_active" not in fields:
            fields.append("is_active")
        return tuple(fields)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj)

    @admin.action(description="Inativar usuários selecionados")
    def inativar_usuarios(self, request, queryset):
        if not request.user.has_perm("atendimento.manage_user_status"):
            raise PermissionDenied

        alterados = 0
        for user_id in queryset.values_list("pk", flat=True):
            try:
                alterados += bool(
                    set_user_active(user_id=user_id, active=False, actor=request.user)
                )
            except ValidationError as exc:
                self.message_user(request, str(exc), messages.ERROR)

        self.message_user(request, f"{alterados} usuário(s) inativado(s).", messages.SUCCESS)

    @admin.action(description="Reativar usuários selecionados")
    def reativar_usuarios(self, request, queryset):
        if not request.user.has_perm("atendimento.manage_user_status"):
            raise PermissionDenied

        alterados = 0
        for user_id in queryset.values_list("pk", flat=True):
            alterados += bool(
                set_user_active(user_id=user_id, active=True, actor=request.user)
            )

        self.message_user(request, f"{alterados} usuário(s) reativado(s).", messages.SUCCESS)


admin.site.unregister(User)
admin.site.register(User, ProtectedUserAdmin)


@admin.register(StatusAuditEvent)
class StatusAuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "action", "actor", "target_user", "target_product")
    list_filter = ("action", "occurred_at")
    search_fields = ("actor__username", "target_user__username", "target_product__nome")
    readonly_fields = ("action", "actor", "occurred_at", "target_user", "target_product")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False