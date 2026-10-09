from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AdicionarItemForm, ComandaForm
from .models import (
    Caixa, Comanda, ComandaItem, ItemAdicional, MovimentacaoCaixa, Pagamento,
)


def _comanda_aberta(pk):
    comanda = get_object_or_404(
        Comanda.objects.select_related("mesa", "cliente").prefetch_related(
            Prefetch("itens", queryset=ComandaItem.objects.select_related("produto").prefetch_related("adicionais")),
            "pagamentos",
        ),
        pk=pk,
    )
    if comanda.status != Comanda.Status.ABERTA:
        raise Http404("Esta comanda não está aberta.")
    return comanda


@login_required
def atendimento(request):
    comandas = Comanda.objects.filter(status=Comanda.Status.ABERTA).select_related(
        "mesa", "cliente"
    ).prefetch_related("itens")
    caixa = Caixa.objects.filter(status=Caixa.Status.ABERTO).first()

    if request.method == "POST":
        form = ComandaForm(request.POST)
        if form.is_valid():
            mesa = form.cleaned_data.get("mesa")
            if mesa and Comanda.objects.filter(
                mesa=mesa, status=Comanda.Status.ABERTA
            ).exists():
                form.add_error("mesa", "Já existe uma comanda aberta nesta mesa.")
            else:
                try:
                    with transaction.atomic():
                        comanda = form.save(commit=False)
                        comanda.criado_por = request.user
                        comanda.atualizado_por = request.user
                        comanda.save()
                except Exception:
                    form.add_error(None, "Não foi possível abrir a comanda. Atualize a tela e tente novamente.")
                else:
                    messages.success(request, f"Comanda {comanda.pk} aberta.")
                    return redirect("atendimento:comanda", pk=comanda.pk)
    else:
        form = ComandaForm()

    return render(request, "atendimento/atendimento.html", {
        "form": form,
        "comandas": comandas,
        "caixa": caixa,
    })


@login_required
def comanda_detalhe(request, pk):
    comanda = _comanda_aberta(pk)
    caixa = Caixa.objects.filter(status=Caixa.Status.ABERTO).first()
    itens_form = AdicionarItemForm()

    if request.method == "POST":
        if "adicionar_item" in request.POST:
            itens_form = AdicionarItemForm(request.POST)
            if itens_form.is_valid():
                produto = itens_form.cleaned_data["produto"]
                quantidade = itens_form.cleaned_data["quantidade"]
                with transaction.atomic():
                    item = ComandaItem.objects.create(
                        comanda=comanda,
                        produto=produto,
                        produto_nome=produto.nome,
                        quantidade=quantidade,
                        preco_unitario=produto.preco,
                        observacao=itens_form.cleaned_data["observacao"],
                        criado_por=request.user,
                        atualizado_por=request.user,
                    )
                    for adicional in itens_form.cleaned_data["adicionais"]:
                        ItemAdicional.objects.create(
                            item=item,
                            adicional=adicional,
                            adicional_nome=adicional.nome,
                            quantidade=quantidade,
                            preco_unitario=adicional.preco,
                            criado_por=request.user,
                            atualizado_por=request.user,
                        )
                messages.success(request, f"{quantidade} × {produto.nome} adicionado à comanda.")
                return redirect("atendimento:comanda", pk=pk)

        elif "registrar_pagamento" in request.POST:
            if caixa is None:
                messages.error(request, "Não há caixa aberto. Abra o caixa antes de receber pagamentos.")
                return redirect("atendimento:comanda", pk=pk)
            try:
                valor = Decimal(request.POST.get("valor", "").replace(",", "."))
            except (InvalidOperation, AttributeError):
                valor = Decimal("0")
            forma = request.POST.get("forma")
            if valor <= 0:
                messages.error(request, "Informe um valor de pagamento maior que zero.")
            elif valor > comanda.saldo:
                messages.error(request, "O pagamento não pode ser maior que o saldo da comanda.")
            elif forma not in Pagamento.Forma.values:
                messages.error(request, "Selecione uma forma de pagamento válida.")
            else:
                with transaction.atomic():
                    caixa_atual = Caixa.objects.select_for_update().get(pk=caixa.pk)
                    comanda_atual = Comanda.objects.select_for_update().get(pk=comanda.pk)
                    if caixa_atual.status != Caixa.Status.ABERTO or comanda_atual.status != Comanda.Status.ABERTA:
                        messages.error(request, "O caixa ou a comanda deixou de estar aberto.")
                        return redirect("atendimento:comanda", pk=pk)
                    saldo = comanda_atual.saldo
                    if valor > saldo:
                        messages.error(request, "O pagamento ultrapassa o saldo atualizado da comanda.")
                    else:
                        Pagamento.objects.create(
                            comanda=comanda_atual,
                            caixa=caixa_atual,
                            forma=forma,
                            valor=valor,
                            referencia=request.POST.get("referencia", "").strip()[:100],
                            criado_por=request.user,
                            atualizado_por=request.user,
                        )
                        messages.success(request, "Pagamento registrado.")
                return redirect("atendimento:comanda", pk=pk)

        elif "fechar_comanda" in request.POST:
            with transaction.atomic():
                comanda_atual = Comanda.objects.select_for_update().get(pk=comanda.pk)
                if not comanda_atual.itens.exists():
                    messages.error(request, "Adicione pelo menos um item antes de fechar a comanda.")
                elif comanda_atual.saldo > 0:
                    messages.error(request, "Registre o pagamento do saldo antes de fechar a comanda.")
                else:
                    comanda_atual.status = Comanda.Status.FECHADA
                    comanda_atual.fechada_em = timezone.now()
                    comanda_atual.atualizado_por = request.user
                    comanda_atual.save(update_fields=["status", "fechada_em", "atualizado_por", "atualizado_em"])
                    messages.success(request, f"Comanda {comanda.pk} fechada.")
                    return redirect("atendimento:lista")
            return redirect("atendimento:comanda", pk=pk)

    comanda.refresh_from_db()
    comanda = _comanda_aberta(pk)
    return render(request, "atendimento/comanda.html", {
        "comanda": comanda,
        "itens_form": itens_form,
        "caixa": caixa,
        "formas_pagamento": Pagamento.Forma.choices,
    })


@login_required
@require_POST
def remover_item(request, pk, item_id):
    comanda = _comanda_aberta(pk)
    item = get_object_or_404(ComandaItem, pk=item_id, comanda=comanda)
    if item.status_producao != ComandaItem.StatusProducao.PENDENTE:
        messages.error(request, "Só é possível remover itens que ainda não foram enviados à cozinha.")
    else:
        item.delete()
        messages.success(request, "Item removido da comanda.")
    return redirect("atendimento:comanda", pk=pk)


@login_required
def cozinha(request):
    itens = ComandaItem.objects.filter(
        comanda__status=Comanda.Status.ABERTA,
        status_producao__in=[ComandaItem.StatusProducao.PENDENTE, ComandaItem.StatusProducao.ENVIADO],
    ).select_related("comanda", "comanda__mesa").prefetch_related("adicionais")
    return render(request, "atendimento/cozinha.html", {"itens": itens})


@login_required
@require_POST
def atualizar_producao(request, item_id):
    item = get_object_or_404(
        ComandaItem.objects.select_related("comanda"),
        pk=item_id,
        comanda__status=Comanda.Status.ABERTA,
    )
    novo_status = request.POST.get("status")
    if novo_status not in (ComandaItem.StatusProducao.ENVIADO, ComandaItem.StatusProducao.PRONTO):
        messages.error(request, "Estado de produção inválido.")
    elif novo_status == ComandaItem.StatusProducao.PRONTO and item.status_producao != ComandaItem.StatusProducao.ENVIADO:
        messages.error(request, "Envie o item à cozinha antes de marcá-lo como pronto.")
    else:
        item.status_producao = novo_status
        item.atualizado_por = request.user
        item.save(update_fields=["status_producao", "atualizado_por", "atualizado_em"])
        messages.success(request, "Estado do pedido atualizado.")
    return redirect("atendimento:cozinha")


@login_required
def caixa(request):
    caixa_atual = Caixa.objects.filter(status=Caixa.Status.ABERTO).first()
    historico = Caixa.objects.order_by("-aberto_em")[:15]
    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "abrir":
            try:
                inicial = Decimal(request.POST.get("valor_inicial", "0").replace(",", "."))
            except (InvalidOperation, AttributeError):
                inicial = Decimal("-1")
            if inicial < 0:
                messages.error(request, "Informe um valor inicial válido, igual ou maior que zero.")
            elif Caixa.objects.filter(status=Caixa.Status.ABERTO).exists():
                messages.error(request, "Já existe um caixa aberto.")
            else:
                try:
                    with transaction.atomic():
                        caixa_atual = Caixa.objects.create(
                            valor_inicial=inicial,
                            criado_por=request.user,
                            atualizado_por=request.user,
                        )
                except Exception:
                    messages.error(request, "Não foi possível abrir o caixa. Atualize a página e tente novamente.")
                else:
                    messages.success(request, "Caixa aberto.")
                    return redirect("atendimento:caixa")
        elif acao == "movimentar" and caixa_atual:
            tipo = request.POST.get("tipo")
            descricao = request.POST.get("descricao", "").strip()
            try:
                valor = Decimal(request.POST.get("valor", "").replace(",", "."))
            except (InvalidOperation, AttributeError):
                valor = Decimal("0")
            if tipo not in MovimentacaoCaixa.Tipo.values or not descricao or valor <= 0:
                messages.error(request, "Preencha corretamente o tipo, a descrição e um valor maior que zero.")
            else:
                with transaction.atomic():
                    caixa_bloqueado = Caixa.objects.select_for_update().get(pk=caixa_atual.pk)
                    if caixa_bloqueado.status != Caixa.Status.ABERTO:
                        messages.error(request, "Este caixa já foi fechado.")
                    else:
                        MovimentacaoCaixa.objects.create(
                            caixa=caixa_bloqueado, tipo=tipo, descricao=descricao[:150], valor=valor,
                            criado_por=request.user, atualizado_por=request.user,
                        )
                        messages.success(request, "Movimentação registrada.")
                        return redirect("atendimento:caixa")
        elif acao == "fechar" and caixa_atual:
            try:
                contado = Decimal(request.POST.get("valor_fechamento", "").replace(",", "."))
            except (InvalidOperation, AttributeError):
                contado = Decimal("-1")
            if contado < 0:
                messages.error(request, "Informe o valor contado no fechamento, igual ou maior que zero.")
            else:
                with transaction.atomic():
                    caixa_bloqueado = Caixa.objects.select_for_update().get(pk=caixa_atual.pk)
                    if caixa_bloqueado.status != Caixa.Status.ABERTO:
                        messages.error(request, "Este caixa já foi fechado.")
                    else:
                        caixa_bloqueado.status = Caixa.Status.FECHADO
                        caixa_bloqueado.fechado_em = timezone.now()
                        caixa_bloqueado.valor_fechamento = contado
                        caixa_bloqueado.fechado_por = request.user
                        caixa_bloqueado.atualizado_por = request.user
                        caixa_bloqueado.save()
                        messages.success(request, "Caixa fechado e valor contado registrado.")
                        return redirect("atendimento:caixa")

    if caixa_atual:
        pagamentos = Pagamento.objects.filter(caixa=caixa_atual)
        entradas = MovimentacaoCaixa.objects.filter(caixa=caixa_atual, tipo=MovimentacaoCaixa.Tipo.ENTRADA)
        saidas = MovimentacaoCaixa.objects.filter(caixa=caixa_atual, tipo=MovimentacaoCaixa.Tipo.SAIDA)
        recebido = sum((p.valor for p in pagamentos), Decimal("0.00"))
        total_entradas = sum((m.valor for m in entradas), Decimal("0.00"))
        total_saidas = sum((m.valor for m in saidas), Decimal("0.00"))
        esperado = caixa_atual.valor_inicial + recebido + total_entradas - total_saidas
        movimentos = list(pagamentos.select_related("comanda")) + list(entradas) + list(saidas)
        movimentos.sort(key=lambda mov: mov.criado_em, reverse=True)
    else:
        recebido = total_entradas = total_saidas = esperado = Decimal("0.00")
        movimentos = []

    return render(request, "atendimento/caixa.html", {
        "caixa": caixa_atual,
        "historico": historico,
        "recebido": recebido,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "esperado": esperado,
        "movimentos": movimentos,
    })
