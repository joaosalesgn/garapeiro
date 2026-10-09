from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Caixa, Categoria, Comanda, ComandaItem, Mesa, Pagamento, Produto


class OperacaoAtendimentoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="atendente", password="teste-seguro")
        self.client.force_login(self.user)
        self.categoria = Categoria.objects.create(nome="Lanches")
        self.produto = Produto.objects.create(
            nome="Pastel de queijo", categoria=self.categoria, preco=Decimal("12.50")
        )
        self.mesa = Mesa.objects.create(numero=1)

    def test_tela_principal_exige_login_e_abre_comanda(self):
        self.client.logout()
        resposta = self.client.get(reverse("atendimento:lista"))
        self.assertEqual(resposta.status_code, 302)
        self.client.force_login(self.user)
        resposta = self.client.post(reverse("atendimento:lista"), {
            "canal": Comanda.Canal.MESA,
            "mesa": self.mesa.pk,
            "cliente": "",
            "observacao": "",
        })
        comanda = Comanda.objects.get()
        self.assertRedirects(resposta, reverse("atendimento:comanda", kwargs={"pk": comanda.pk}))
        self.assertEqual(comanda.mesa, self.mesa)

    def test_impede_duas_comandas_abertas_na_mesma_mesa(self):
        Comanda.objects.create(mesa=self.mesa)
        resposta = self.client.post(reverse("atendimento:lista"), {
            "canal": Comanda.Canal.MESA,
            "mesa": self.mesa.pk,
            "cliente": "",
            "observacao": "",
        })
        self.assertEqual(Comanda.objects.count(), 1)
        self.assertContains(resposta, "Já existe uma comanda aberta nesta mesa")

    def test_adiciona_item_e_registra_pagamento_sem_ultrapassar_saldo(self):
        caixa = Caixa.objects.create(valor_inicial=Decimal("50.00"), criado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        url = reverse("atendimento:comanda", kwargs={"pk": comanda.pk})
        resposta = self.client.post(url, {
            "adicionar_item": "1", "produto": self.produto.pk,
            "quantidade": "2", "observacao": "", "adicionais": [],
        })
        self.assertEqual(resposta.status_code, 302)
        item = ComandaItem.objects.get(comanda=comanda)
        self.assertEqual(item.total, Decimal("25.00"))
        resposta = self.client.post(url, {
            "registrar_pagamento": "1", "forma": Pagamento.Forma.PIX,
            "valor": "30.00", "referencia": "",
        })
        self.assertEqual(Pagamento.objects.count(), 0)
        self.assertContains(resposta, "maior que o saldo")
        resposta = self.client.post(url, {
            "registrar_pagamento": "1", "forma": Pagamento.Forma.PIX,
            "valor": "25.00", "referencia": "",
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Pagamento.objects.get().caixa, caixa)
        self.assertEqual(comanda.saldo, Decimal("0.00"))

    def test_fecha_comanda_quando_quitada(self):
        caixa = Caixa.objects.create(criado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        ComandaItem.objects.create(
            comanda=comanda, produto=self.produto, produto_nome=self.produto.nome,
            quantidade=1, preco_unitario=self.produto.preco,
        )
        Pagamento.objects.create(
            comanda=comanda, caixa=caixa, forma=Pagamento.Forma.DINHEIRO,
            valor=self.produto.preco, criado_por=self.user,
        )
        resposta = self.client.post(reverse("atendimento:comanda", kwargs={"pk": comanda.pk}), {"fechar_comanda": "1"})
        comanda.refresh_from_db()
        self.assertEqual(comanda.status, Comanda.Status.FECHADA)
        self.assertIsNotNone(comanda.fechada_em)
        self.assertRedirects(resposta, reverse("atendimento:lista"))

    def test_cozinha_avanca_pedido_enviado_para_pronto(self):
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        item = ComandaItem.objects.create(
            comanda=comanda, produto=self.produto, produto_nome=self.produto.nome,
            quantidade=1, preco_unitario=self.produto.preco,
        )
        resposta = self.client.post(reverse("atendimento:atualizar_producao", kwargs={"item_id": item.pk}), {"status": "ENVIADO"})
        self.assertEqual(resposta.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.ENVIADO)
        self.client.post(reverse("atendimento:atualizar_producao", kwargs={"item_id": item.pk}), {"status": "PRONTO"})
        item.refresh_from_db()
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.PRONTO)

    def test_abertura_movimentacao_e_fechamento_do_caixa(self):
        url = reverse("atendimento:caixa")
        resposta = self.client.post(url, {"acao": "abrir", "valor_inicial": "100.00"})
        self.assertEqual(resposta.status_code, 302)
        caixa = Caixa.objects.get(status=Caixa.Status.ABERTO)
        self.client.post(url, {"acao": "movimentar", "tipo": "SAIDA", "descricao": "Compra de gelo", "valor": "15.00"})
        resposta = self.client.post(url, {"acao": "fechar", "valor_fechamento": "85.00"})
        caixa.refresh_from_db()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(caixa.status, Caixa.Status.FECHADO)
        self.assertEqual(caixa.valor_fechamento, Decimal("85.00"))

    def test_tela_da_cozinha_e_caixa_carregam(self):
        self.assertEqual(self.client.get(reverse("atendimento:cozinha")).status_code, 200)
        self.assertEqual(self.client.get(reverse("atendimento:caixa")).status_code, 200)
