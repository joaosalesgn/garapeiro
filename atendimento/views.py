from decimal import Decimal, ROUND_HALF_UP
import os
import uuid

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AbrirCaixaForm, AdicionarItemForm, FecharCaixaForm, MovimentacaoForm,
    NovaComandaForm, PagamentoForm, EncerrarComandaForm, NovaContaPagarForm, BaixaContaPagarForm,
    ContaFinanceiraForm, OperacaoFinanceiraForm, TransferenciaForm, CupomForm,
)
from .impressao import ErroImpressao, imprimir_itens_cozinha, imprimir_itens_consumo
from .models import (
    Caixa, Cliente, Comanda, ComandaItem, ItemAdicional, MovimentacaoCaixa, Pagamento,
    ContaReceber, ContaPagar, BaixaContaPagar, Mesa, ContaFinanceira, OperacaoFinanceira, LancamentoTesouraria, Cupom,
)



class LoginSistemaView(auth_views.LoginView):
    template_name = "login.html"
    redirect_authenticated_user = True


@require_POST
def logout_sistema(request):
    auth_logout(request)
    return redirect("atendimento:login")

def _caixa_aberto():
    return Caixa.objects.filter(status=Caixa.Status.ABERTO).first()


def _conta_por_tipo(tipo):
    return ContaFinanceira.objects.filter(tipo=tipo, ativa=True).order_by("pk").first()


def _operacoes(tipo):
    return OperacaoFinanceira.objects.filter(
        tipo=tipo, ativa=True, conta_padrao__ativa=True
    ).select_related("conta_padrao").order_by("forma_pagamento", "pk")


def _operacao_recebimento(forma):
    return _operacoes(OperacaoFinanceira.Tipo.RECEBIMENTO).filter(forma_pagamento=forma).first()


def _operacao_pagamento(forma):
    return _operacoes(OperacaoFinanceira.Tipo.PAGAMENTO).filter(forma_pagamento=forma).first()


def _destino_recebimento(forma):
    operacao = _operacao_recebimento(forma)
    conta = operacao.conta_padrao if operacao else None
    tipo_esperado = ContaFinanceira.Tipo.GAVETA if forma == Pagamento.Forma.DINHEIRO else ContaFinanceira.Tipo.BANCO
    if conta and conta.tipo != tipo_esperado:
        return None, None
    return conta, operacao


def _gravar_recebimento(*, caixa, pagamento, forma, valor, usuario):
    """Grava bruto, taxa e líquido em caixa financeira, garantindo o link do pagamento."""
    conta, operacao = _destino_recebimento(forma)
    taxa_pct = operacao.taxa_percentual if operacao and forma != Pagamento.Forma.DINHEIRO else Decimal("0.000")
    taxa = (valor * taxa_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if not conta:
        raise ValueError("Configure uma conta financeira e uma operação para esta forma de recebimento antes de usá-la.")
    liquido = valor - taxa
    LancamentoTesouraria.objects.create(
        conta=conta, caixa=caixa, tipo=LancamentoTesouraria.Tipo.RECEBIMENTO,
        descricao=f"Recebimento {pagamento.get_forma_display()} — Comanda #{pagamento.comanda_id}",
        valor_bruto=valor, taxa=taxa, valor=liquido, operacao=operacao,
        pagamento=pagamento, referencia=pagamento.referencia,
        criado_por=usuario, atualizado_por=usuario,
    )


def _saldo_conta(conta):
    lancamentos = conta.lancamentos.filter(cancelado_em__isnull=True).exclude(
        descricao="Fundo inicial do caixa"
    )
    entradas = lancamentos.exclude(tipo__in=[
        LancamentoTesouraria.Tipo.PAGAMENTO,
        LancamentoTesouraria.Tipo.TRANSFERENCIA_SAIDA,
        LancamentoTesouraria.Tipo.AJUSTE_SAIDA,
        LancamentoTesouraria.Tipo.SALDO_INICIAL,
    ]).aggregate(v=Sum("valor"))["v"] or Decimal("0.00")
    saidas = lancamentos.filter(tipo__in=[
        LancamentoTesouraria.Tipo.PAGAMENTO,
        LancamentoTesouraria.Tipo.TRANSFERENCIA_SAIDA,
        LancamentoTesouraria.Tipo.AJUSTE_SAIDA,
    ]).aggregate(v=Sum("valor"))["v"] or Decimal("0.00")
    return conta.saldo_inicial + entradas - saidas


def _registrar_pagamento_cp(*, conta, caixa, baixa, forma, valor, usuario, referencia):
    operacao = _operacao_pagamento(forma)
    LancamentoTesouraria.objects.create(
        conta=conta, caixa=caixa, tipo=LancamentoTesouraria.Tipo.PAGAMENTO,
        descricao=f"Pagamento CP #{baixa.conta_id} — {baixa.conta.descricao}",
        valor_bruto=valor, taxa=Decimal("0.00"), valor=valor, baixa_cp=baixa,
        operacao=operacao, referencia=referencia, criado_por=usuario, atualizado_por=usuario,
    )


def _total_caixa(caixa):
    entradas_pagamentos = caixa.pagamentos.filter(forma=Pagamento.Forma.DINHEIRO).aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    movimentos = list(caixa.movimentacoes.values("tipo").annotate(total=Sum("valor")))
    entradas_avulsas = sum((m["total"] for m in movimentos if m["tipo"] == MovimentacaoCaixa.Tipo.ENTRADA), Decimal("0.00"))
    saidas = sum((m["total"] for m in movimentos if m["tipo"] == MovimentacaoCaixa.Tipo.SAIDA), Decimal("0.00"))
    # CP é paga da conta financeira selecionada, não da gaveta.
    saidas_contas_pagar = caixa.baixas_contas_pagar.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    sangrias = caixa.lancamentos_tesouraria.filter(
        conta__tipo=ContaFinanceira.Tipo.GAVETA,
        tipo=LancamentoTesouraria.Tipo.TRANSFERENCIA_SAIDA,
        cancelado_em__isnull=True,
    ).exclude(descricao__startswith="Sangria do fechamento do caixa #").aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    saidas += sangrias
    esperado = caixa.valor_inicial + entradas_pagamentos + entradas_avulsas - saidas
    return {
        "pagamentos": entradas_pagamentos,
        "entradas_avulsas": entradas_avulsas,
        "saidas": saidas,
        "saidas_contas_pagar": saidas_contas_pagar,
        "esperado": esperado,
    }



def _aplicar_desconto_comanda(comanda, dados, usuario):
    """Valida e atualiza em memória o desconto da comanda."""
    cupom = dados.get("cupom")
    percentual = dados.get("desconto_percentual")
    valor_informado = dados.get("desconto_valor")
    if cupom:
        if not cupom.valido_em(timezone.localdate()):
            return "Este cupom não está ativo ou não é válido hoje."
        if cupom.tipo_desconto == Cupom.TipoDesconto.PERCENTUAL:
            if valor_informado is not None or (percentual is not None and percentual != cupom.valor_desconto):
                return "Use o desconto do cupom ou remova o cupom para informar outro desconto."
            percentual = cupom.valor_desconto
            valor = (comanda.subtotal * percentual / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            if percentual is not None or (valor_informado is not None and valor_informado != cupom.valor_desconto):
                return "Use o desconto do cupom ou remova o cupom para informar outro desconto."
            valor = cupom.valor_desconto
            percentual = None
    elif percentual is not None and valor_informado is not None:
        return "Informe o desconto em percentual ou em reais, não ambos."
    elif percentual is not None:
        if percentual > Decimal("100"):
            return "O percentual de desconto não pode ultrapassar 100%."
        valor = (comanda.subtotal * percentual / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif valor_informado is not None:
        valor = valor_informado
        percentual = None
    else:
        # Pagamento parcelado posterior sem desconto informado mantém o desconto salvo.
        return None
    valor = min(valor, comanda.subtotal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if comanda.total_pago > comanda.subtotal - valor:
        return "O desconto deixaria o total menor que os pagamentos já registrados."
    comanda.cupom = cupom
    comanda.desconto_percentual = percentual
    comanda.desconto_valor = valor
    comanda.atualizado_por = usuario
    return None


def _salvar_desconto_comanda(comanda):
    comanda.save(update_fields=["cupom", "desconto_percentual", "desconto_valor", "atualizado_por", "atualizado_em"])


@login_required
def inicio(request):
    pode_atendimento = request.user.has_perm("atendimento.view_comanda")
    pode_cozinha = request.user.has_perm("atendimento.view_comandaitem")
    pode_caixa = request.user.has_perm("atendimento.view_caixa")
    pode_abrir_comanda = request.user.has_perm("atendimento.add_comanda")
    comandas_abertas = (
        Comanda.objects.filter(status=Comanda.Status.ABERTA)
        if pode_atendimento else Comanda.objects.none()
    )
    mesas = (
        Mesa.objects.filter(ativa=True).order_by("numero").prefetch_related(
            Prefetch(
                "comandas",
                queryset=Comanda.objects.filter(status=Comanda.Status.ABERTA).only("pk", "mesa_id"),
                to_attr="comandas_abertas",
            )
        )
        if pode_atendimento or pode_abrir_comanda
        else Mesa.objects.none()
    )
    comandas_balcao_entrega = (
        Comanda.objects.filter(
            status=Comanda.Status.ABERTA,
            canal__in=[Comanda.Canal.BALCAO, Comanda.Canal.ENTREGA],
        ).select_related("cliente").order_by("canal", "-criado_em")
        if pode_atendimento else Comanda.objects.none()
    )
    return render(request, "inicio.html", {
        "mesas": mesas, "total_mesas": mesas.count(),
        "comandas_balcao_entrega": comandas_balcao_entrega,
        "total_comandas": comandas_abertas.count(),
        "itens_cozinha": ComandaItem.objects.filter(
            status_producao=ComandaItem.StatusProducao.ENVIADO,
            comanda__status=Comanda.Status.ABERTA,
        ).count() if pode_cozinha else 0,
        "caixa": _caixa_aberto() if pode_caixa else None,
        "pode_atendimento": pode_atendimento,
        "pode_cozinha": pode_cozinha,
        "pode_caixa": pode_caixa,
        "pode_abrir_comanda": pode_abrir_comanda,
        "pode_movimentar": request.user.has_perm("atendimento.add_movimentacaocaixa"),
        "movimentacao_form": MovimentacaoForm() if request.user.has_perm("atendimento.add_movimentacaocaixa") else None,
        "caixa_disponivel": _caixa_aberto() is not None if request.user.has_perm("atendimento.add_movimentacaocaixa") else False,
    })



@login_required
@permission_required("atendimento.manage_cupons", raise_exception=True)
def cupons(request, pk=None):
    cupom = get_object_or_404(Cupom, pk=pk) if pk else None
    if request.method == "POST":
        cupom_id = request.POST.get("cupom_id")
        if cupom_id:
            cupom = get_object_or_404(Cupom, pk=cupom_id)
        form = CupomForm(request.POST, instance=cupom)
        if form.is_valid():
            registro = form.save(commit=False)
            if not registro.pk:
                registro.criado_por = request.user
            registro.atualizado_por = request.user
            registro.save()
            messages.success(request, f"Cupom {registro.codigo} salvo.")
            return redirect("atendimento:cupons")
    else:
        form = CupomForm(instance=cupom)
    return render(request, "cupons.html", {
        "form": form, "editando": cupom,
        "cupons": Cupom.objects.all().order_by("-valido_ate", "codigo"),
        "hoje": timezone.localdate(),
    })

@login_required
@permission_required("atendimento.view_comanda", raise_exception=True)
def comandas(request):
    abertas = Comanda.objects.filter(status=Comanda.Status.ABERTA).select_related("mesa", "cliente")
    encerradas = Comanda.objects.exclude(status=Comanda.Status.ABERTA).select_related("mesa", "cliente")[:30]
    return render(request, "comandas.html", {"abertas": abertas, "encerradas": encerradas})


@login_required
@permission_required("atendimento.add_comanda", raise_exception=True)
def nova_comanda(request):
    if not Caixa.objects.filter(status=Caixa.Status.ABERTO).exists():
        messages.error(request, "Abra o caixa antes de criar uma comanda.")
        return redirect("atendimento:inicio")

    if request.method == "GET":
        mesa_id = request.GET.get("mesa")

        initial = {"canal": (Comanda.Canal.MESA if mesa_id else Comanda.Canal.BALCAO )}

        if mesa_id:
            initial["mesa"] = mesa_id

        form = NovaComandaForm(initial=initial)
    else:
        form = NovaComandaForm(request.POST)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            caixa = Caixa.objects.select_for_update().filter(status=Caixa.Status.ABERTO).first()

            if not caixa:
                messages.error(request, "O caixa foi fechado. Abra-o antes de criar uma comanda.")
                return redirect("atendimento:inicio")

            dados = form.cleaned_data
            comanda = Comanda.objects.create(canal=dados["canal"], mesa=dados["mesa"], cliente=dados["cliente"], observacao=dados["observacao"], criado_por=request.user, atualizado_por=request.user)

        messages.success(request, f"Comanda #{comanda.pk} aberta.")
        return redirect("atendimento:comanda", pk=comanda.pk)

    return render(request, "formulario.html", {
        "form": form,
        "titulo": "Abrir comanda",
        "voltar": "atendimento:inicio",
    })


@login_required
@permission_required("atendimento.view_comanda", raise_exception=True)
def detalhe_comanda(request, pk):
    comanda = get_object_or_404(Comanda.objects.select_related("mesa", "cliente"), pk=pk)
    caixa = _caixa_aberto()
    item_form = AdicionarItemForm(initial={"produto": request.GET.get("produto")} if request.GET.get("produto") else None)
    pagamento_form = PagamentoForm(
        initial={
            "valor": max(comanda.saldo, Decimal("0.01")),
            "cupom": comanda.cupom_id,
            "desconto_percentual": comanda.desconto_percentual,
            "desconto_valor": comanda.desconto_valor if not comanda.desconto_percentual else None,
        },
        operacoes=_operacoes(OperacaoFinanceira.Tipo.RECEBIMENTO),
    )
    return render(request, "comanda.html", {
        "comanda": comanda, "caixa": caixa, "item_form": item_form,
        "pagamento_form": pagamento_form,
        "encerrar_form": EncerrarComandaForm(initial={
            "cupom": comanda.cupom_id,
            "desconto_percentual": comanda.desconto_percentual,
            "desconto_valor": comanda.desconto_valor if not comanda.desconto_percentual else None,
        }),
        "cupons_js": list(Cupom.objects.filter(
            ativo=True, valido_de__lte=timezone.localdate(), valido_ate__gte=timezone.localdate()
        ).values("id", "tipo_desconto", "valor_desconto")),
        "clientes": Cliente.objects.filter(ativo=True),
        "itens_cozinha_total": ComandaItem.objects.filter(comanda=comanda, produto__vai_para_cozinha=True).exclude(status_producao=ComandaItem.StatusProducao.CANCELADO).count(),
        "itens_cozinha_pendentes": ComandaItem.objects.filter(comanda=comanda, produto__vai_para_cozinha=True, cozinha_impresso_em__isnull=True).exclude(status_producao=ComandaItem.StatusProducao.CANCELADO).count(),
        "itens_consumo_total": comanda.itens.exclude(status_producao=ComandaItem.StatusProducao.CANCELADO).count(),
    })


@login_required
@require_POST
@permission_required("atendimento.view_comanda", raise_exception=True)
def imprimir_comanda_cozinha(request, pk):
    nome_impressora = os.environ.get("GARAPEIRO_IMPRESSORA", "POS-80").strip() or "POS-80"
    reimprimir_tudo = request.POST.get("reimprimir_tudo") == "1"
    try:
        with transaction.atomic():
            comanda = get_object_or_404(Comanda.objects.select_for_update().select_related("mesa", "cliente"), pk=pk)
            base = ComandaItem.objects.select_for_update().filter(
                comanda=comanda, produto__vai_para_cozinha=True
            ).exclude(status_producao=ComandaItem.StatusProducao.CANCELADO)
            itens = list(base.prefetch_related("adicionais")) if reimprimir_tudo else list(
                base.filter(cozinha_impresso_em__isnull=True).prefetch_related("adicionais")
            )
            if not itens:
                messages.info(request, "Todos os produtos da cozinha já foram impressos.")
                return redirect("atendimento:comanda", pk=pk)
            if comanda.status != Comanda.Status.ABERTA:
                messages.error(request, "Só é possível enviar produtos de uma comanda aberta à cozinha.")
                return redirect("atendimento:comanda", pk=pk)
            # Marca após envio aceito pelo spooler: falha não consome itens pendentes.
            imprimir_itens_cozinha(comanda, itens, nome_impressora)
            ComandaItem.objects.filter(pk__in=[item.pk for item in itens]).update(cozinha_impresso_em=timezone.now())
    except ErroImpressao as exc:
        messages.error(request, str(exc))
    else:
        mensagem = "Todos os produtos da cozinha foram reimpressos." if reimprimir_tudo else f"{len(itens)} item(ns) enviado(s) à cozinha."
        messages.success(request, mensagem)
    return redirect("atendimento:comanda", pk=pk)


@login_required
@require_POST
@permission_required("atendimento.view_comanda", raise_exception=True)
def imprimir_comanda_consumo(request, pk):
    comanda = get_object_or_404(Comanda.objects.select_related("mesa", "cliente"), pk=pk)
    itens = list(comanda.itens.exclude(
        status_producao=ComandaItem.StatusProducao.CANCELADO
    ).prefetch_related("adicionais"))
    if not itens:
        messages.info(request, "Esta comanda ainda não possui itens para imprimir.")
        return redirect("atendimento:comanda", pk=pk)
    nome_impressora = os.environ.get("GARAPEIRO_IMPRESSORA", "POS-80").strip() or "POS-80"
    try:
        imprimir_itens_consumo(comanda, itens, nome_impressora)
    except ErroImpressao as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Conferência de consumo enviada para impressão.")
    return redirect("atendimento:comanda", pk=pk)


@login_required
@require_POST
@permission_required("atendimento.add_comandaitem", raise_exception=True)
def adicionar_item(request, pk):
    comanda = get_object_or_404(Comanda, pk=pk)
    if comanda.status != Comanda.Status.ABERTA:
        messages.error(request, "Não é possível alterar uma comanda encerrada.")
        return redirect("atendimento:comanda", pk=pk)
    form = AdicionarItemForm(request.POST)
    if not form.is_valid():
        for erro in form.errors.values():
            messages.error(request, " ".join(erro))
        return redirect("atendimento:comanda", pk=pk)
    dados = form.cleaned_data
    produto = dados["produto"]
    with transaction.atomic():
        item = ComandaItem.objects.create(
            comanda=comanda, produto=produto, produto_nome=produto.nome,
            quantidade=dados["quantidade"], preco_unitario=produto.preco,
            observacao=dados["observacao"], status_producao=(
                ComandaItem.StatusProducao.ENVIADO if produto.vai_para_cozinha
                else ComandaItem.StatusProducao.PRONTO
            ), criado_por=request.user, atualizado_por=request.user,
        )
        for adicional in dados["adicionais"]:
            ItemAdicional.objects.create(
                item=item, adicional=adicional, adicional_nome=adicional.nome,
                quantidade=1, preco_unitario=adicional.preco,
                criado_por=request.user, atualizado_por=request.user,
            )
    messages.success(request, f"{dados['quantidade']} × {produto.nome} adicionado à comanda.")
    return redirect("atendimento:comanda", pk=pk)


@login_required
@require_POST
@permission_required("atendimento.change_comandaitem", raise_exception=True)
def cancelar_item(request, pk, item_id):
    with transaction.atomic():
        comanda = get_object_or_404(Comanda.objects.select_for_update(), pk=pk)
        item = get_object_or_404(ComandaItem.objects.select_for_update(), pk=item_id, comanda=comanda)
        if comanda.status != Comanda.Status.ABERTA:
            messages.error(request, "A comanda já foi encerrada.")
        elif item.status_producao == ComandaItem.StatusProducao.CANCELADO:
            messages.info(request, "Este item já foi cancelado.")
        else:
            adicionais = sum((ad.total for ad in item.adicionais.all()), Decimal("0.00"))
            if comanda.total - item.total - adicionais < comanda.total_pago:
                messages.error(request, "Não é possível cancelar este item: há pagamentos já registrados que superariam o novo total da comanda.")
                return redirect("atendimento:comanda", pk=pk)
            item.status_producao = ComandaItem.StatusProducao.CANCELADO
            item.atualizado_por = request.user
            item.save(update_fields=["status_producao", "atualizado_por", "atualizado_em"])
            messages.success(request, "Item cancelado; o histórico foi preservado.")
    return redirect("atendimento:comanda", pk=pk)


@login_required
@require_POST
@permission_required("atendimento.add_pagamento", raise_exception=True)
def registrar_pagamento(request, pk):
    form = PagamentoForm(request.POST, operacoes=_operacoes(OperacaoFinanceira.Tipo.RECEBIMENTO))
    if not form.is_valid():
        for erro in form.errors.values():
            messages.error(request, " ".join(erro))
        return redirect("atendimento:comanda", pk=pk)
    with transaction.atomic():
        comanda = get_object_or_404(Comanda.objects.select_for_update(), pk=pk)
        caixa = Caixa.objects.select_for_update().filter(status=Caixa.Status.ABERTO).first()
        conta = ContaReceber.objects.select_for_update().filter(comanda=comanda).first()
        if comanda.status != Comanda.Status.ABERTA and not conta:
            messages.error(request, "Não existe conta a receber aberta para esta comanda encerrada.")
        elif not caixa:
            messages.error(request, "Abra o caixa antes de registrar recebimentos.")
        elif comanda.subtotal <= 0:
            messages.error(request, "Adicione pelo menos um item antes do recebimento.")
        else:
            erro_desconto = _aplicar_desconto_comanda(comanda, form.cleaned_data, request.user) if comanda.status == Comanda.Status.ABERTA else None
            if erro_desconto:
                messages.error(request, erro_desconto)
            elif comanda.total <= 0:
                messages.error(request, "O total da comanda após o desconto precisa ser maior que zero.")
            elif form.cleaned_data["valor"] > comanda.saldo:
                messages.error(request, f"O valor supera o saldo de R$ {comanda.saldo:.2f}.")
            else:
                forma = form.cleaned_data["forma"]
                destino_financeiro, operacao = _destino_recebimento(forma)
                if not destino_financeiro:
                    messages.error(request, "Configure o destino financeiro desta forma de recebimento na Tesouraria.")
                    return redirect("atendimento:comanda", pk=pk)
                if comanda.status == Comanda.Status.ABERTA:
                    _salvar_desconto_comanda(comanda)
                pagamento = Pagamento.objects.create(
                    comanda=comanda, caixa=caixa, forma=forma,
                    valor=form.cleaned_data["valor"], referencia=form.cleaned_data["referencia"],
                    criado_por=request.user, atualizado_por=request.user,
                )
                _gravar_recebimento(caixa=caixa, pagamento=pagamento, forma=forma, valor=pagamento.valor, usuario=request.user)
                if conta:
                    conta.atualizar_status(request.user)
                if comanda.saldo == 0:
                    if comanda.status == Comanda.Status.ABERTA:
                        comanda.status = Comanda.Status.FECHADA
                        comanda.fechada_em = timezone.now()
                        comanda.atualizado_por = request.user
                        comanda.save(update_fields=["status", "fechada_em", "atualizado_por", "atualizado_em"])
                        conta, _ = ContaReceber.objects.get_or_create(
                            comanda=comanda,
                            defaults={"cliente": comanda.cliente, "valor_total": comanda.total,
                                      "vencimento": timezone.localdate(), "criado_por": request.user,
                                      "atualizado_por": request.user},
                        )
                        conta.atualizar_status(request.user)
                        messages.success(request, "Recebimento quitado. Comanda encerrada e CR gerado como quitado.")
                        return redirect("atendimento:inicio")
                    messages.success(request, "Recebimento registrado; conta a receber quitada.")
                else:
                    messages.success(request, f"Recebimento registrado. Saldo restante: R$ {comanda.saldo:.2f}.")
    if comanda.status == Comanda.Status.FECHADA:
        return redirect("atendimento:contas_receber")
    return redirect("atendimento:comanda", pk=pk)


@login_required
@require_POST
@permission_required("atendimento.change_comanda", raise_exception=True)
def fechar_comanda(request, pk):
    with transaction.atomic():
        comanda = get_object_or_404(Comanda.objects.select_for_update().select_related("cliente"), pk=pk)
        form = EncerrarComandaForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Confira o cupom e os descontos informados.")
        elif comanda.status != Comanda.Status.ABERTA:
            messages.error(request, "A comanda já está encerrada.")
        elif not comanda.itens.exclude(status_producao=ComandaItem.StatusProducao.CANCELADO).exists():
            messages.error(request, "Adicione pelo menos um item válido antes de encerrar.")
        else:
            erro_desconto = _aplicar_desconto_comanda(comanda, form.cleaned_data, request.user)
            if erro_desconto:
                messages.error(request, erro_desconto)
            elif comanda.saldo < 0:
                messages.error(request, "O total recebido não pode superar o valor da comanda.")
            else:
                cliente = form.cleaned_data.get("cliente") or comanda.cliente
                if comanda.saldo > 0 and not cliente:
                    messages.error(request, "Selecione um cliente para encerrar a comanda a prazo.")
                elif comanda.saldo > 0 and not form.cleaned_data.get("vencimento"):
                    messages.error(request, "Informe o vencimento da conta a receber.")
                else:
                    comanda.itens.exclude(
                        status_producao=ComandaItem.StatusProducao.CANCELADO
                    ).exclude(
                        status_producao=ComandaItem.StatusProducao.PRONTO
                    ).update(status_producao=ComandaItem.StatusProducao.PRONTO)
                    comanda.cliente = cliente
                    comanda.status = Comanda.Status.FECHADA
                    comanda.fechada_em = timezone.now()
                    comanda.atualizado_por = request.user
                    comanda.save(update_fields=[
                        "cliente", "status", "fechada_em", "cupom", "desconto_percentual",
                        "desconto_valor", "atualizado_por", "atualizado_em",
                    ])
                    conta, _ = ContaReceber.objects.get_or_create(
                        comanda=comanda,
                        defaults={"cliente": cliente, "valor_total": comanda.total,
                                  "vencimento": form.cleaned_data.get("vencimento") or timezone.localdate(),
                                  "criado_por": request.user, "atualizado_por": request.user},
                    )
                    conta.cliente = cliente
                    conta.valor_total = comanda.total
                    conta.atualizado_por = request.user
                    conta.save(update_fields=["cliente", "valor_total", "atualizado_por", "atualizado_em"])
                    conta.atualizar_status(request.user)
                    if conta.status == ContaReceber.Status.QUITADA:
                        messages.success(request, "Comanda encerrada e CR gerado como quitado.")
                    else:
                        messages.success(request, f"Comanda encerrada a prazo. CR #{conta.pk} criado para {cliente}.")
                    return redirect("atendimento:inicio")
    return redirect("atendimento:comanda", pk=pk)


@login_required
@permission_required("atendimento.view_contareceber", raise_exception=True)
def contas_receber(request):
    contas = ContaReceber.objects.select_related("cliente", "comanda").order_by("vencimento", "-criado_em")
    return render(request, "contas_receber.html", {
        "contas": contas, "caixa_aberto": _caixa_aberto(),
        "pode_receber": request.user.has_perm("atendimento.add_pagamento"),
        "operacoes_recebimento": _operacoes(OperacaoFinanceira.Tipo.RECEBIMENTO),
    })


@login_required
@permission_required("atendimento.add_pagamento", raise_exception=True)
@require_POST
def receber_conta(request, pk):
    form = PagamentoForm(request.POST, operacoes=_operacoes(OperacaoFinanceira.Tipo.RECEBIMENTO))
    if not form.is_valid():
        for erro in form.errors.values():
            messages.error(request, " ".join(erro))
        return redirect("atendimento:contas_receber")
    with transaction.atomic():
        conta = get_object_or_404(ContaReceber.objects.select_for_update().select_related("comanda"), pk=pk)
        caixa = Caixa.objects.select_for_update().filter(status=Caixa.Status.ABERTO).first()
        if conta.status == ContaReceber.Status.QUITADA:
            messages.error(request, "Esta conta a receber já está quitada.")
        elif not caixa:
            messages.error(request, "Abra o caixa antes de registrar o recebimento.")
        elif form.cleaned_data["valor"] > conta.saldo:
            messages.error(request, f"O valor supera o saldo de R$ {conta.saldo:.2f}.")
        else:
            forma = form.cleaned_data["forma"]
            destino_financeiro, operacao = _destino_recebimento(forma)
            if not destino_financeiro:
                messages.error(request, "Configure o destino financeiro desta forma de recebimento na Tesouraria.")
                return redirect("atendimento:contas_receber")
            pagamento = Pagamento.objects.create(
                comanda=conta.comanda, caixa=caixa, forma=forma,
                valor=form.cleaned_data["valor"], referencia=form.cleaned_data["referencia"],
                criado_por=request.user, atualizado_por=request.user,
            )
            _gravar_recebimento(caixa=caixa, pagamento=pagamento, forma=forma, valor=pagamento.valor, usuario=request.user)
            conta.atualizar_status(request.user)
            messages.success(request, f"Recebimento registrado no CR #{conta.pk}.")
    return redirect("atendimento:contas_receber")


@login_required
@permission_required("atendimento.view_contapagar", raise_exception=True)
def contas_pagar(request):
    form = NovaContaPagarForm()
    if request.method == "POST":
        if not request.user.has_perm("atendimento.add_contapagar"):
            raise PermissionDenied
        form = NovaContaPagarForm(request.POST)
        if form.is_valid():
            conta = ContaPagar.objects.create(**form.cleaned_data, criado_por=request.user, atualizado_por=request.user)
            messages.success(request, f"Conta a pagar #{conta.pk} cadastrada.")
            return redirect("atendimento:contas_pagar")
    return render(request, "contas_pagar.html", {
        "contas": ContaPagar.objects.prefetch_related("baixas").order_by("vencimento", "-criado_em"),
        "form": form,
        "pode_adicionar": request.user.has_perm("atendimento.add_contapagar"),
        "pode_baixar": request.user.has_perm("atendimento.add_baixacontapagar"),
        "caixa_aberto": _caixa_aberto(),
        "contas_saida": ContaFinanceira.objects.filter(ativa=True).order_by("tipo", "pk"),
        "operacoes_pagamento": _operacoes(OperacaoFinanceira.Tipo.PAGAMENTO),
    })


@login_required
@require_POST
@permission_required("atendimento.add_baixacontapagar", raise_exception=True)
def baixar_conta_pagar(request, pk):
    form = BaixaContaPagarForm(request.POST, operacoes=_operacoes(OperacaoFinanceira.Tipo.PAGAMENTO))
    if not form.is_valid():
        for erro in form.errors.values():
            messages.error(request, " ".join(erro))
        return redirect("atendimento:contas_pagar")
    with transaction.atomic():
        conta = get_object_or_404(ContaPagar.objects.select_for_update(), pk=pk)
        caixa = Caixa.objects.select_for_update().filter(status=Caixa.Status.ABERTO).first()
        if not caixa:
            messages.error(request, "Abra o caixa para registrar um pagamento de conta.")
        elif form.cleaned_data["valor"] > conta.saldo:
            messages.error(request, f"O valor supera o saldo de R$ {conta.saldo:.2f}.")
        elif form.cleaned_data["valor"] > _saldo_conta(form.cleaned_data["conta_saida"]):
            messages.error(request, "O valor supera o saldo disponível na conta de saída escolhida.")
        else:
            baixa = BaixaContaPagar.objects.create(
                conta=conta, caixa=caixa, forma=form.cleaned_data["forma"],
                valor=form.cleaned_data["valor"], referencia=form.cleaned_data["referencia"],
                criado_por=request.user, atualizado_por=request.user,
            )
            _registrar_pagamento_cp(conta=form.cleaned_data["conta_saida"], caixa=caixa, baixa=baixa, forma=baixa.forma, valor=baixa.valor, usuario=request.user, referencia=baixa.referencia)
            conta.atualizar_status(request.user)
            messages.success(request, f"Pagamento registrado na CP #{conta.pk}.")
    return redirect("atendimento:contas_pagar")


@login_required
@permission_required("atendimento.view_comandaitem", raise_exception=True)
def cozinha(request):
    itens = ComandaItem.objects.filter(
        comanda__status__in=[Comanda.Status.ABERTA, Comanda.Status.FECHADA],
        status_producao__in=[ComandaItem.StatusProducao.PENDENTE, ComandaItem.StatusProducao.ENVIADO],
        produto__vai_para_cozinha=True,
    ).select_related("comanda", "comanda__mesa", "produto").prefetch_related("adicionais")
    return render(request, "cozinha.html", {"itens": itens})


@login_required
@require_POST
@permission_required("atendimento.change_comandaitem", raise_exception=True)
def atualizar_cozinha(request, item_id, status):
    permitidos = {ComandaItem.StatusProducao.ENVIADO, ComandaItem.StatusProducao.PRONTO}
    if status not in permitidos:
        raise Http404
    with transaction.atomic():
        item = get_object_or_404(ComandaItem.objects.select_for_update(), pk=item_id)
        if item.comanda.status not in {Comanda.Status.ABERTA, Comanda.Status.FECHADA} or item.status_producao == ComandaItem.StatusProducao.CANCELADO:
            messages.error(request, "Este item não está disponível para atualização.")
        else:
            transicoes = {
                ComandaItem.StatusProducao.PENDENTE: ComandaItem.StatusProducao.ENVIADO,
                ComandaItem.StatusProducao.ENVIADO: ComandaItem.StatusProducao.PRONTO,
            }
            if transicoes.get(item.status_producao) != status:
                messages.error(request, "Transição de status inválida para este item.")
                return redirect("atendimento:cozinha")
            item.status_producao = status
            item.atualizado_por = request.user
            item.save(update_fields=["status_producao", "atualizado_por", "atualizado_em"])
            messages.success(request, "Status atualizado na cozinha.")
    return redirect("atendimento:cozinha")


@login_required
@permission_required("atendimento.view_contafinanceira", raise_exception=True)
def tesouraria(request):
    contas_form = ContaFinanceiraForm(prefix="conta")
    operacao_form = OperacaoFinanceiraForm(prefix="operacao")
    transferencia_form = TransferenciaForm(prefix="transferencia")
    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "conta" and request.user.has_perm("atendimento.add_contafinanceira"):
            contas_form = ContaFinanceiraForm(request.POST, prefix="conta")
            if contas_form.is_valid():
                conta = contas_form.save(commit=False)
                base = conta.tipo
                nome = base
                sufixo = 2
                while ContaFinanceira.objects.filter(nome=nome).exists():
                    nome = f"{base}_{sufixo}"
                    sufixo += 1
                conta.nome = nome
                conta.criado_por = conta.atualizado_por = request.user
                conta.save()
                if conta.saldo_inicial > 0:
                    LancamentoTesouraria.objects.create(conta=conta, tipo=LancamentoTesouraria.Tipo.SALDO_INICIAL, descricao="Saldo inicial", valor_bruto=conta.saldo_inicial, valor=conta.saldo_inicial, criado_por=request.user, atualizado_por=request.user)
                messages.success(request, f"Conta financeira {conta.nome} cadastrada.")
                return redirect("atendimento:tesouraria")
        elif acao == "operacao" and request.user.has_perm("atendimento.add_operacaofinanceira"):
            operacao_form = OperacaoFinanceiraForm(request.POST, prefix="operacao")
            if operacao_form.is_valid():
                op = operacao_form.save(commit=False)
                existente = OperacaoFinanceira.objects.filter(tipo=op.tipo, forma_pagamento=op.forma_pagamento).first()
                if existente:
                    op.pk = existente.pk
                    op.nome = existente.nome
                    op.criado_em = existente.criado_em
                    op.criado_por = existente.criado_por
                else:
                    op.nome = f"{op.tipo}_{op.forma_pagamento}"
                    op.criado_por = request.user
                op.atualizado_por = request.user
                op.save()
                messages.success(request, "Operação financeira cadastrada/atualizada.")
                return redirect("atendimento:tesouraria")
        elif acao == "transferencia" and request.user.has_perm("atendimento.add_lancamentotesouraria"):
            transferencia_form = TransferenciaForm(request.POST, prefix="transferencia")
            if transferencia_form.is_valid():
                dados = transferencia_form.cleaned_data
                caixa_atual = _caixa_aberto()
                transferencia_invalida = (
                    dados["origem"].tipo == ContaFinanceira.Tipo.GAVETA
                    and dados["destino"].tipo == ContaFinanceira.Tipo.DINHEIRO
                    and dados["descricao"].strip().casefold() != "sangria"
                ) or (
                    dados["descricao"].strip().casefold() == "sangria"
                    and (dados["origem"].tipo != ContaFinanceira.Tipo.GAVETA
                         or dados["destino"].tipo != ContaFinanceira.Tipo.DINHEIRO)
                )
                if not caixa_atual:
                    messages.error(request, "Abra o caixa antes de registrar uma transferência.")
                elif transferencia_invalida:
                    messages.error(request, "A transferência da Gaveta para Dinheiro físico guardado deve ser registrada como sangria.")
                elif dados["valor"] > _saldo_conta(dados["origem"]):
                    messages.error(request, "O valor da transferência supera o saldo disponível na conta de origem.")
                else:
                    tid = uuid.uuid4()
                    comum = {"caixa": caixa_atual, "valor_bruto": dados["valor"], "valor": dados["valor"], "transferencia": tid, "criado_por": request.user, "atualizado_por": request.user}
                    LancamentoTesouraria.objects.create(conta=dados["origem"], tipo=LancamentoTesouraria.Tipo.TRANSFERENCIA_SAIDA, descricao=dados["descricao"], **comum)
                    LancamentoTesouraria.objects.create(conta=dados["destino"], tipo=LancamentoTesouraria.Tipo.TRANSFERENCIA_ENTRADA, descricao=dados["descricao"], **comum)
                    messages.success(request, "Transferência registrada nas duas contas.")
                    return redirect("atendimento:tesouraria")
        else:
            raise PermissionDenied
    contas = ContaFinanceira.objects.filter(ativa=True)
    saldos = [(conta, _saldo_conta(conta)) for conta in contas]
    return render(request, "tesouraria.html", {
        "contas": saldos,
        "operacoes": _operacoes(OperacaoFinanceira.Tipo.RECEBIMENTO) | _operacoes(OperacaoFinanceira.Tipo.PAGAMENTO),
        "lancamentos": LancamentoTesouraria.objects.filter(cancelado_em__isnull=True).select_related("conta", "operacao", "caixa")[:100],
        "contas_form": contas_form, "operacao_form": operacao_form,
        "transferencia_form": transferencia_form, "caixa_aberto": _caixa_aberto(),
        "pode_cadastrar_conta": request.user.has_perm("atendimento.add_contafinanceira"),
        "pode_cadastrar_operacao": request.user.has_perm("atendimento.add_operacaofinanceira"),
        "pode_transferir": request.user.has_perm("atendimento.add_lancamentotesouraria"),
    })


@login_required
@permission_required("atendimento.view_caixa", raise_exception=True)
def caixa(request):
    aberto = _caixa_aberto()
    resumo = _total_caixa(aberto) if aberto else None
    historico = Caixa.objects.filter(status=Caixa.Status.FECHADO)[:10]
    historico_resumo = [(c, _total_caixa(c)) for c in historico]
    gaveta = _conta_por_tipo(ContaFinanceira.Tipo.GAVETA)
    valor_sugerido = _saldo_conta(gaveta) if gaveta else Decimal("0.00")
    return render(request, "caixa.html", {
        "caixa": aberto, "resumo": resumo, "historico": historico_resumo,
        "movimentacoes": aberto.movimentacoes.all()[:20] if aberto else [],
        "abrir_form": AbrirCaixaForm(initial={"valor_inicial": valor_sugerido}),
        "valor_sugerido": valor_sugerido,
    })


@login_required
@require_POST
@permission_required("atendimento.add_caixa", raise_exception=True)
def abrir_caixa(request):
    form = AbrirCaixaForm(request.POST)
    if not form.is_valid():
        for erro in form.errors.values():
            messages.error(request, " ".join(erro))
        return redirect("atendimento:caixa")

    valor_inicial = form.cleaned_data["valor_inicial"]

    try:
        with transaction.atomic():
            gaveta = (ContaFinanceira.objects.select_for_update().filter(tipo=ContaFinanceira.Tipo.GAVETA, ativa=True).order_by("pk").first())

            if not gaveta:
                raise ValueError("Cadastre a conta Gaveta na Tesouraria antes de abrir o caixa.")

            saldo_atual_gaveta = _saldo_conta(gaveta)
            diferenca = valor_inicial - saldo_atual_gaveta

            caixa = Caixa.objects.create(valor_inicial=valor_inicial, observacao=form.cleaned_data["observacao"], criado_por=request.user, atualizado_por=request.user)

            if diferenca != Decimal("0.00"):
                valor_ajuste = abs(diferenca)
                tipo_ajuste = (LancamentoTesouraria.Tipo.AJUSTE_ENTRADA if diferenca > 0 else LancamentoTesouraria.Tipo.AJUSTE_SAIDA)

                LancamentoTesouraria.objects.create(conta=gaveta, caixa=caixa, tipo=tipo_ajuste, descricao=f"Ajuste de saldo na abertura do caixa #{caixa.pk}", valor_bruto=valor_ajuste, taxa=Decimal("0.00"), valor=valor_ajuste, criado_por=request.user, atualizado_por=request.user)

        if diferenca == Decimal("0.00"):
            messages.success(request, "Caixa aberto.")
        else:
            messages.success(request, "Caixa aberto. O saldo da Gaveta foi ajustado conforme o valor inicial informado.")

    except IntegrityError:
        messages.error(request, "Já existe um caixa aberto.")
    except ValueError as exc:
        messages.error(request, str(exc))

    return redirect("atendimento:caixa")


@login_required
@require_POST
@permission_required("atendimento.add_movimentacaocaixa", raise_exception=True)
def registrar_movimentacao(request):
    destino = "atendimento:inicio" if request.POST.get("origem") == "inicio" else "atendimento:caixa"
    form = MovimentacaoForm(request.POST)
    if not form.is_valid():
        for erro in form.errors.values():
            messages.error(request, " ".join(erro))
        return redirect(destino)
    with transaction.atomic():
        caixa = Caixa.objects.select_for_update().filter(status=Caixa.Status.ABERTO).first()
        if not caixa:
            messages.error(request, "Não há caixa aberto. Peça ao responsável para abrir o caixa antes de lançar a movimentação.")
        else:
            dados = form.cleaned_data
            gaveta = _conta_por_tipo(ContaFinanceira.Tipo.GAVETA)
            if not gaveta:
                messages.error(request, "Cadastre a conta Gaveta na Tesouraria antes de lançar movimentações.")
            elif dados["tipo"] == MovimentacaoCaixa.Tipo.SAIDA and dados["valor"] > _saldo_conta(gaveta):
                messages.error(request, "O valor da saída supera o saldo disponível na gaveta.")
            else:
                mov = MovimentacaoCaixa.objects.create(
                    caixa=caixa, tipo=dados["tipo"], descricao=dados["descricao"], valor=dados["valor"],
                    criado_por=request.user, atualizado_por=request.user,
                )
                LancamentoTesouraria.objects.create(
                    conta=gaveta, caixa=caixa,
                    tipo=(LancamentoTesouraria.Tipo.AJUSTE_ENTRADA if mov.tipo == MovimentacaoCaixa.Tipo.ENTRADA else LancamentoTesouraria.Tipo.AJUSTE_SAIDA),
                    descricao=mov.descricao, valor_bruto=mov.valor, valor=mov.valor,
                    referencia=f"Movimentação de caixa #{mov.pk}", criado_por=request.user, atualizado_por=request.user,
                )
                messages.success(request, "Movimentação registrada.")
    return redirect(destino)


@login_required
@require_POST
@permission_required("atendimento.change_caixa", raise_exception=True)
def fechar_caixa(request):
    form = FecharCaixaForm(request.POST)
    if not form.is_valid():
        for erro in form.errors.values():
            messages.error(request, " ".join(erro))
        return redirect("atendimento:caixa")
    with transaction.atomic():
        caixa = Caixa.objects.select_for_update().filter(status=Caixa.Status.ABERTO).first()
        if not caixa:
            messages.error(request, "Não há caixa aberto.")
        elif Comanda.objects.filter(status=Comanda.Status.ABERTA, pagamentos__caixa=caixa).distinct().exists():
            messages.error(request, "Há comandas ainda abertas com pagamentos neste caixa. Conclua-as antes de fechar o caixa.")
        else:
            valor_sangria = form.cleaned_data["valor_sangria"]
            gaveta = _conta_por_tipo(ContaFinanceira.Tipo.GAVETA)
            guardado = _conta_por_tipo(ContaFinanceira.Tipo.DINHEIRO)
            if valor_sangria > form.cleaned_data["valor_fechamento"]:
                messages.error(request, "A sangria não pode superar o valor contado no caixa.")
            elif valor_sangria and (not gaveta or not guardado):
                messages.error(request, "Cadastre as contas Gaveta e Dinheiro físico guardado antes de registrar a sangria.")
            else:
                resumo = _total_caixa(caixa)
                diferenca = form.cleaned_data["valor_fechamento"] - resumo["esperado"]
                saldo_gaveta_atual = _saldo_conta(gaveta)
                ajuste = form.cleaned_data["valor_fechamento"] - saldo_gaveta_atual
                if ajuste:
                    tipo_ajuste = LancamentoTesouraria.Tipo.AJUSTE_ENTRADA if ajuste > 0 else LancamentoTesouraria.Tipo.AJUSTE_SAIDA
                    LancamentoTesouraria.objects.create(
                        conta=gaveta, caixa=caixa, tipo=tipo_ajuste,
                        descricao=f"Conferência do fechamento do caixa #{caixa.pk}",
                        valor_bruto=abs(ajuste), valor=abs(ajuste),
                        criado_por=request.user, atualizado_por=request.user,
                    )
                if valor_sangria:
                    tid = uuid.uuid4()
                    comum = {"caixa": caixa, "valor_bruto": valor_sangria, "valor": valor_sangria, "transferencia": tid, "criado_por": request.user, "atualizado_por": request.user}
                    LancamentoTesouraria.objects.create(conta=gaveta, tipo=LancamentoTesouraria.Tipo.TRANSFERENCIA_SAIDA, descricao=f"Sangria do fechamento do caixa #{caixa.pk}", **comum)
                    LancamentoTesouraria.objects.create(conta=guardado, tipo=LancamentoTesouraria.Tipo.TRANSFERENCIA_ENTRADA, descricao=f"Sangria do fechamento do caixa #{caixa.pk}", **comum)
                caixa.status = Caixa.Status.FECHADO
                caixa.fechado_em = timezone.now()
                caixa.fechado_por = request.user
                caixa.valor_fechamento = form.cleaned_data["valor_fechamento"]
                observacao = form.cleaned_data["observacao"].strip()
                if observacao:
                    caixa.observacao = (caixa.observacao + "\n" + observacao).strip()
                caixa.atualizado_por = request.user
                caixa.save(update_fields=["status", "fechado_em", "fechado_por", "valor_fechamento", "observacao", "atualizado_por", "atualizado_em"])
                messages.success(request, f"Caixa fechado. Esperado: R$ {resumo['esperado']:.2f}; contado: R$ {caixa.valor_fechamento:.2f}; sangria: R$ {valor_sangria:.2f}; diferença: R$ {diferenca:.2f}.")
    return redirect("atendimento:caixa")
