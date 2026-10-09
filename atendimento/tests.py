from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import (
    Caixa, Categoria, Comanda, ComandaItem, Mesa, Pagamento, Produto,
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
        ComandaItem.objects.create(
            comanda=comanda, produto=self.produto, produto_nome=self.produto.nome,
            quantidade=2, preco_unitario="12.50",
        )
        self.assertEqual(comanda.total, Decimal("25.00"))
        Pagamento.objects.create(comanda=comanda, caixa=caixa, forma=Pagamento.Forma.PIX, valor="10.00")
        self.assertEqual(comanda.total_pago, Decimal("10.00"))
        self.assertEqual(comanda.saldo, Decimal("15.00"))

    def test_apenas_um_caixa_pode_ficar_aberto(self):
        Caixa.objects.create(criado_por=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Caixa.objects.create(criado_por=self.user)
