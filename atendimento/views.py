from decimal import Decimal
import os

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
    TesteImpressaoForm,
)
from .impressao import ErroImpressao, imprimir_itens_cozinha, imprimir_itens_consumo, imprimir_teste_produto
from .models import (
    Caixa, Cliente, Comanda, ComandaItem, ItemAdicional, MovimentacaoCaixa, Pagamento,
    ContaReceber, ContaPagar, BaixaContaPagar, Mesa,
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


def _total_caixa(caixa):
    entradas_pagamentos = caixa.pagamentos.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    movimentos = list(caixa.movimentacoes.values("tipo").annotate(total=Sum("valor")))
    entradas_avulsas = sum((m["total"] for m in movimentos if m["tipo"] == MovimentacaoCaixa.Tipo.ENTRADA), Decimal("0.00"))
    saidas = sum((m["total"] for m in movimentos if m["tipo"] == MovimentacaoCaixa.Tipo.SAIDA), Decimal("0.00"))
    saidas_contas_pagar = caixa.baixas_contas_pagar.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
    saidas += saidas_contas_pagar
    esperado = caixa.valor_inicial + entradas_pagamentos + entradas_avulsas - saidas
    return {
        "pagamentos": entradas_pagamentos,
        "entradas_avulsas": entradas_avulsas,
        "saidas": saidas,
        "saidas_contas_pagar": saidas_contas_pagar,
        "esperado": esperado,
    }


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
@permission_required("atendimento.view_comanda", raise_exception=True)
def comandas(request):
    abertas = Comanda.objects.filter(status=Comanda.Status.ABERTA).select_related("mesa", "cliente")
    encerradas = Comanda.objects.exclude(status=Comanda.Status.ABERTA).select_related("mesa", "cliente")[:30]
    return render(request, "comandas.html", {"abertas": abertas, "encerradas": encerradas})


@login_required
@permission_required("atendimento.view_produto", raise_exception=True)
def teste_impressao_produto(request):
    nome_impressora = os.environ.get("GARAPEIRO_IMPRESSORA", "POS-80").strip() or "POS-80"
    form = TesteImpressaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            imprimir_teste_produto(form.cleaned_data["produto"], form.cleaned_data["quantidade"], nome_impressora)
        except ErroImpressao as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Comprovante de teste enviado para {nome_impressora}.")
            form = TesteImpressaoForm()
    return render(request, "teste_impressao.html", {"form": form, "nome_impressora": nome_impressora})


@login_required
@permission_required("atendimento.add_comanda", raise_exception=True)
def nova_comanda(request):
    form = NovaComandaForm(
        request.POST or None,
        initial={"mesa": request.GET.get("mesa")} if request.method == "GET" else None,
    )
    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        comanda = Comanda.objects.create(
            canal=dados["canal"], mesa=dados["mesa"], cliente=dados["cliente"],
            observacao=dados["observacao"], criado_por=request.user, atualizado_por=request.user,
        )
        messages.success(request, f"Comanda #{comanda.pk} aberta.")
        return redirect("atendimento:comanda", pk=comanda.pk)
    return render(request, "formulario.html", {"form": form, "titulo": "Abrir comanda", "voltar": "atendimento:comandas"})


@login_required
@permission_required("atendimento.view_comanda", raise_exception=True)
def detalhe_comanda(request, pk):
    comanda = get_object_or_404(Comanda.objects.select_related("mesa", "cliente"), pk=pk)
    caixa = _caixa_aberto()
    item_form = AdicionarItemForm(initial={"produto": request.GET.get("produto")} if request.GET.get("produto") else None)
    pagamento_form = PagamentoForm(initial={"valor": max(comanda.saldo, Decimal("0.01"))})
    return render(request, "comanda.html", {
        "comanda": comanda, "caixa": caixa, "item_form": item_form,
        "pagamento_form": pagamento_form, "clientes": Cliente.objects.filter(ativo=True),
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
    form = PagamentoForm(request.POST)
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
        elif comanda.total <= 0:
            messages.error(request, "Adicione pelo menos um item antes do recebimento.")
        elif form.cleaned_data["valor"] > comanda.saldo:
            messages.error(request, f"O valor supera o saldo de R$ {comanda.saldo:.2f}.")
        else:
            Pagamento.objects.create(
                comanda=comanda, caixa=caixa, forma=form.cleaned_data["forma"],
                valor=form.cleaned_data["valor"], referencia=form.cleaned_data["referencia"],
                criado_por=request.user, atualizado_por=request.user,
            )
            if conta:
                conta.atualizar_status()
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
                    conta.atualizar_status()
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
            messages.error(request, "Confira o cliente e o vencimento informados.")
        elif comanda.status != Comanda.Status.ABERTA:
            messages.error(request, "A comanda já está encerrada.")
        elif not comanda.itens.exclude(status_producao=ComandaItem.StatusProducao.CANCELADO).exists():
            messages.error(request, "Adicione pelo menos um item válido antes de encerrar.")
        elif comanda.saldo < 0:
            messages.error(request, "O total recebido não pode superar o valor da comanda.")
        else:
            cliente = form.cleaned_data.get("cliente") or comanda.cliente
            if comanda.saldo > 0 and not cliente:
                messages.error(request, "Selecione um cliente para encerrar a comanda a prazo.")
            elif comanda.saldo > 0 and not form.cleaned_data.get("vencimento"):
                messages.error(request, "Informe o vencimento da conta a receber.")
            else:
                comanda.cliente = cliente
                comanda.status = Comanda.Status.FECHADA
                comanda.fechada_em = timezone.now()
                comanda.atualizado_por = request.user
                comanda.save(update_fields=["cliente", "status", "fechada_em", "atualizado_por", "atualizado_em"])
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
                conta.atualizar_status()
                if conta.status == ContaReceber.Status.QUITADA:
                    messages.success(request, "Comanda encerrada e CR gerado como quitado.")
                else:
                    messages.success(request, f"Comanda encerrada a prazo. CR #{conta.pk} criado para {cliente}.")
                return redirect("atendimento:contas_receber")
    return redirect("atendimento:comanda", pk=pk)


@login_required
@permission_required("atendimento.view_contareceber", raise_exception=True)
def contas_receber(request):
    contas = ContaReceber.objects.select_related("cliente", "comanda").order_by("vencimento", "-criado_em")
    return render(request, "contas_receber.html", {"contas": contas, "caixa_aberto": _caixa_aberto(), "pode_receber": request.user.has_perm("atendimento.add_pagamento")})


@login_required
@permission_required("atendimento.add_pagamento", raise_exception=True)
@require_POST
def receber_conta(request, pk):
    form = PagamentoForm(request.POST)
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
            Pagamento.objects.create(
                comanda=conta.comanda, caixa=caixa, forma=form.cleaned_data["forma"],
                valor=form.cleaned_data["valor"], referencia=form.cleaned_data["referencia"],
                criado_por=request.user, atualizado_por=request.user,
            )
            conta.atualizar_status()
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
    })


@login_required
@require_POST
@permission_required("atendimento.add_baixacontapagar", raise_exception=True)
def baixar_conta_pagar(request, pk):
    form = BaixaContaPagarForm(request.POST)
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
        else:
            BaixaContaPagar.objects.create(
                conta=conta, caixa=caixa, forma=form.cleaned_data["forma"],
                valor=form.cleaned_data["valor"], referencia=form.cleaned_data["referencia"],
                criado_por=request.user, atualizado_por=request.user,
            )
            conta.atualizar_status()
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
@permission_required("atendimento.view_caixa", raise_exception=True)
def caixa(request):
    aberto = _caixa_aberto()
    resumo = _total_caixa(aberto) if aberto else None
    historico = Caixa.objects.filter(status=Caixa.Status.FECHADO)[:10]
    historico_resumo = [(c, _total_caixa(c)) for c in historico]
    return render(request, "caixa.html", {
        "caixa": aberto, "resumo": resumo, "historico": historico_resumo,
        "movimentacoes": aberto.movimentacoes.all()[:20] if aberto else [],
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
    try:
        with transaction.atomic():
            Caixa.objects.create(
                valor_inicial=form.cleaned_data["valor_inicial"],
                observacao=form.cleaned_data["observacao"],
                criado_por=request.user, atualizado_por=request.user,
            )
        messages.success(request, "Caixa aberto.")
    except IntegrityError:
        messages.error(request, "Já existe um caixa aberto.")
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
            MovimentacaoCaixa.objects.create(
                caixa=caixa, tipo=dados["tipo"], descricao=dados["descricao"], valor=dados["valor"],
                criado_por=request.user, atualizado_por=request.user,
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
            resumo = _total_caixa(caixa)
            caixa.status = Caixa.Status.FECHADO
            caixa.fechado_em = timezone.now()
            caixa.fechado_por = request.user
            caixa.valor_fechamento = form.cleaned_data["valor_fechamento"]
            observacao = form.cleaned_data["observacao"].strip()
            if observacao:
                caixa.observacao = (caixa.observacao + "\n" + observacao).strip()
            caixa.atualizado_por = request.user
            caixa.save(update_fields=["status", "fechado_em", "fechado_por", "valor_fechamento", "observacao", "atualizado_por", "atualizado_em"])
            diferenca = caixa.valor_fechamento - resumo["esperado"]
            messages.success(request, f"Caixa fechado. Esperado: R$ {resumo['esperado']:.2f}; contado: R$ {caixa.valor_fechamento:.2f}; diferença: R$ {diferenca:.2f}.")
    return redirect("atendimento:caixa")
