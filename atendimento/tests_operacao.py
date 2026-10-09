from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Adicional, Caixa, Categoria, Comanda, ComandaItem, ItemAdicional, Mesa, MovimentacaoCaixa, Pagamento, Produto


class OperacaoAtendimentoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="atendente", password="teste-seguro")
        self.client.force_login(self.user)
        self.categoria = Categoria.objects.create(nome="Lanches")
        self.produto = Produto.objects.create(nome="Pastel de queijo", categoria=self.categoria, preco=Decimal("12.50"), vai_para_cozinha=True)
        self.mesa = Mesa.objects.create(numero=1)

    def test_inicio_exige_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("atendimento:inicio")).status_code, 302)

    def test_abre_comanda_para_mesa(self):
        resposta = self.client.post(reverse("atendimento:nova_comanda"), {"canal": Comanda.Canal.MESA, "mesa": self.mesa.pk, "cliente": "", "observacao": ""})
        comanda = Comanda.objects.get()
        self.assertRedirects(resposta, reverse("atendimento:comanda", kwargs={"pk": comanda.pk}))
        self.assertEqual(comanda.mesa, self.mesa)

    def test_impede_duas_comandas_abertas_na_mesma_mesa(self):
        Comanda.objects.create(mesa=self.mesa)
        resposta = self.client.post(reverse("atendimento:nova_comanda"), {"canal": Comanda.Canal.MESA, "mesa": self.mesa.pk, "cliente": "", "observacao": ""})
        self.assertEqual(Comanda.objects.count(), 1)
        self.assertContains(resposta, "Já existe uma comanda aberta nesta mesa")

    def test_adiciona_item_e_impede_pagamento_acima_do_saldo(self):
        caixa = Caixa.objects.create(valor_inicial=Decimal("50.00"), criado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        self.client.post(reverse("atendimento:adicionar_item", kwargs={"pk": comanda.pk}), {"produto": self.produto.pk, "quantidade": "2", "observacao": "", "adicionais": []})
        item = ComandaItem.objects.get(comanda=comanda)
        self.assertEqual(item.total, Decimal("25.00"))
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.PENDENTE)
        url = reverse("atendimento:registrar_pagamento", kwargs={"pk": comanda.pk})
        resposta = self.client.post(url, {"forma": Pagamento.Forma.PIX, "valor": "30.00", "referencia": ""}, follow=True)
        self.assertEqual(Pagamento.objects.count(), 0)
        self.assertContains(resposta, "supera o saldo")
        self.client.post(url, {"forma": Pagamento.Forma.PIX, "valor": "25.00", "referencia": ""})
        self.assertEqual(Pagamento.objects.get().caixa, caixa)
        self.assertEqual(comanda.saldo, Decimal("0.00"))

    def test_item_cancelado_e_adicional_preservados_mas_excluidos_do_total(self):
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        item = ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome, quantidade=1, preco_unitario="12.50")
        adicional = Adicional.objects.create(nome="Queijo extra", preco="2.00")
        ItemAdicional.objects.create(item=item, adicional=adicional, adicional_nome=adicional.nome, preco_unitario="2.00")
        self.client.post(reverse("atendimento:cancelar_item", kwargs={"pk": comanda.pk, "item_id": item.pk}))
        item.refresh_from_db()
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.CANCELADO)
        self.assertTrue(item.adicionais.exists())
        self.assertEqual(comanda.total, Decimal("0.00"))

    def test_impede_cancelamento_que_supere_pagamentos(self):
        caixa = Caixa.objects.create(criado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        item = ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome, quantidade=1, preco_unitario=self.produto.preco)
        Pagamento.objects.create(comanda=comanda, caixa=caixa, forma=Pagamento.Forma.DINHEIRO, valor=self.produto.preco, criado_por=self.user)
        resposta = self.client.post(reverse("atendimento:cancelar_item", kwargs={"pk": comanda.pk, "item_id": item.pk}), follow=True)
        item.refresh_from_db()
        self.assertContains(resposta, "pagamentos já registrados")
        self.assertNotEqual(item.status_producao, ComandaItem.StatusProducao.CANCELADO)
        self.assertEqual(comanda.total, comanda.total_pago)

    def test_fecha_comanda_apenas_com_saldo_quitado_e_itens_prontos(self):
        caixa = Caixa.objects.create(criado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        item = ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome, quantidade=1, preco_unitario=self.produto.preco)
        Pagamento.objects.create(comanda=comanda, caixa=caixa, forma=Pagamento.Forma.DINHEIRO, valor=self.produto.preco, criado_por=self.user)
        resposta = self.client.post(reverse("atendimento:fechar_comanda", kwargs={"pk": comanda.pk}), follow=True)
        comanda.refresh_from_db()
        self.assertEqual(comanda.status, Comanda.Status.ABERTA)
        self.assertContains(resposta, "todos os itens ficarem prontos")
        item.status_producao = ComandaItem.StatusProducao.PRONTO
        item.save(update_fields=["status_producao"])
        self.client.post(reverse("atendimento:fechar_comanda", kwargs={"pk": comanda.pk}))
        comanda.refresh_from_db()
        self.assertEqual(comanda.status, Comanda.Status.FECHADA)

    def test_cozinha_avanca_item_pendente_ate_pronto(self):
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        item = ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome, quantidade=1, preco_unitario=self.produto.preco)
        self.assertContains(self.client.get(reverse("atendimento:cozinha")), "Pastel de queijo")
        self.client.post(reverse("atendimento:atualizar_cozinha", kwargs={"item_id": item.pk, "status": "ENVIADO"}))
        item.refresh_from_db()
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.ENVIADO)
        self.client.post(reverse("atendimento:atualizar_cozinha", kwargs={"item_id": item.pk, "status": "PRONTO"}))
        item.refresh_from_db()
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.PRONTO)

    def test_produto_fora_da_cozinha_fica_pronto(self):
        produto = Produto.objects.create(nome="Suco pronto", categoria=self.categoria, preco=Decimal("6.00"), vai_para_cozinha=False)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user)
        self.client.post(reverse("atendimento:adicionar_item", kwargs={"pk": comanda.pk}), {"produto": produto.pk, "quantidade": "1", "observacao": "", "adicionais": []})
        item = ComandaItem.objects.get(comanda=comanda)
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.PRONTO)
        resposta = self.client.get(reverse("atendimento:cozinha"))
        self.assertFalse(resposta.context["itens"].filter(pk=item.pk).exists())

    def test_abertura_movimentacao_e_fechamento_do_caixa(self):
        self.client.post(reverse("atendimento:abrir_caixa"), {"valor_inicial": "100.00", "observacao": ""})
        caixa = Caixa.objects.get(status=Caixa.Status.ABERTO)
        self.client.post(reverse("atendimento:registrar_movimentacao"), {"tipo": "SAIDA", "descricao": "Compra de gelo", "valor": "15.00"})
        self.client.post(reverse("atendimento:fechar_caixa"), {"valor_fechamento": "85.00", "observacao": ""})
        caixa.refresh_from_db()
        self.assertEqual(caixa.status, Caixa.Status.FECHADO)
        self.assertEqual(caixa.valor_fechamento, Decimal("85.00"))
        self.assertEqual(MovimentacaoCaixa.objects.count(), 1)

    def test_telas_da_cozinha_e_caixa_carregam(self):
        self.assertEqual(self.client.get(reverse("atendimento:cozinha")).status_code, 200)
        self.assertEqual(self.client.get(reverse("atendimento:caixa")).status_code, 200)
