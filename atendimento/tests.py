from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import (
    Caixa, Categoria, Comanda, ComandaItem, ItemAdicional,
    Mesa, Pagamento, Produto, Adicional,
)


class CadastrosEAtendimentoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="teste", password="senha-segura-123")
        self.categoria = Categoria.objects.create(nome="Pastéis")
        self.produto = Produto.objects.create(nome="Pastel de queijo", categoria=self.categoria, preco="12.50")

    def test_auditoria_registra_criacao(self):
        self.assertIsNotNone(self.produto.criado_em)
        self.assertIsNotNone(self.produto.atualizado_em)

    def test_unicidade_de_produto_por_categoria(self):
        outra = Categoria.objects.create(nome="Bebidas")
        Produto.objects.create(nome="Pastel de queijo", categoria=outra, preco="12.50")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Produto.objects.create(nome="Pastel de queijo", categoria=self.categoria, preco="13.00")

    def test_mesa_tem_numero_unico(self):
        Mesa.objects.create(numero=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Mesa.objects.create(numero=1)

    def test_comanda_calcula_total_saldo_e_pagamento(self):
        caixa = Caixa.objects.create(criado_por=self.user, valor_inicial="100.00")
        comanda = Comanda.objects.create(criado_por=self.user)
        item = ComandaItem.objects.create(
            comanda=comanda, produto=self.produto, produto_nome=self.produto.nome,
            quantidade=2, preco_unitario="12.50",
        )
        adicional = Adicional.objects.create(nome="Queijo extra", preco="2.00")
        ItemAdicional.objects.create(item=item, adicional=adicional, adicional_nome=adicional.nome, quantidade=1, preco_unitario="2.00")
        self.assertEqual(comanda.total, Decimal("27.00"))
        Pagamento.objects.create(comanda=comanda, caixa=caixa, forma=Pagamento.Forma.PIX, valor="10.00")
        self.assertEqual(comanda.total_pago, Decimal("10.00"))
        self.assertEqual(comanda.saldo, Decimal("17.00"))

    def test_apenas_um_caixa_pode_ficar_aberto(self):
        Caixa.objects.create(criado_por=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Caixa.objects.create(criado_por=self.user)

    def test_cancelar_item_preserva_historico_e_recalcula_total_sem_adicional(self):
        comanda = Comanda.objects.create(criado_por=self.user)
        item = ComandaItem.objects.create(
            comanda=comanda, produto=self.produto, produto_nome=self.produto.nome,
            quantidade=1, preco_unitario="12.50",
        )
        adicional = Adicional.objects.create(nome="Queijo extra", preco="2.00")
        ItemAdicional.objects.create(item=item, adicional=adicional, adicional_nome=adicional.nome, quantidade=1, preco_unitario="2.00")
        item.status_producao = ComandaItem.StatusProducao.CANCELADO
        item.save()
        item.refresh_from_db()
        self.assertTrue(ItemAdicional.objects.filter(item=item).exists())
        self.assertEqual(comanda.total, Decimal("0.00"))

    def test_produto_exibe_categoria_no_seletor(self):
        from .forms import AdicionarItemForm

        form = AdicionarItemForm()
        self.assertEqual(
            form.fields["produto"].label_from_instance(self.produto),
            "Pastéis — Pastel de queijo",
        )
