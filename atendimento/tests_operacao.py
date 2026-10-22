from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Adicional, Caixa, Categoria, Comanda, ComandaItem, ItemAdicional, Mesa, MovimentacaoCaixa, Pagamento, Produto, ProdutoAdicional, ContaReceber, ContaPagar, ContaFinanceira, OperacaoFinanceira


class OperacaoAtendimentoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="atendente", password="teste-seguro", email="atendente@example.local")
        self.client.force_login(self.user)
        self.categoria = Categoria.objects.create(nome="Lanches", criado_por=self.user, atualizado_por=self.user)
        self.produto = Produto.objects.create(nome="Pastel de queijo", categoria=self.categoria, preco=Decimal("12.50"), vai_para_cozinha=True, criado_por=self.user, atualizado_por=self.user)
        self.mesa = Mesa.objects.create(numero=1, criado_por=self.user, atualizado_por=self.user)
        self.gaveta = ContaFinanceira.objects.create(nome="Gaveta", tipo=ContaFinanceira.Tipo.GAVETA, criado_por=self.user, atualizado_por=self.user)
        self.banco = ContaFinanceira.objects.create(nome="Banco", tipo=ContaFinanceira.Tipo.BANCO, criado_por=self.user, atualizado_por=self.user)
        OperacaoFinanceira.objects.create(nome="PIX", tipo=OperacaoFinanceira.Tipo.RECEBIMENTO, forma_pagamento=Pagamento.Forma.PIX, conta_padrao=self.banco, criado_por=self.user, atualizado_por=self.user)

    def test_inicio_exige_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("atendimento:inicio")).status_code, 302)

    def test_inicio_exibe_mesas_ativas_com_estado_e_links_corretos(self):
        mesa_livre = Mesa.objects.create(numero=2, criado_por=self.user, atualizado_por=self.user)
        Mesa.objects.create(numero=3, ativa=False, criado_por=self.user, atualizado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)

        resposta = self.client.get(reverse("atendimento:inicio"))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Mesa 1, ocupada")
        self.assertContains(resposta, reverse("atendimento:comanda", kwargs={"pk": comanda.pk}))
        self.assertContains(resposta, f"{reverse('atendimento:nova_comanda')}?mesa={mesa_livre.pk}")
        self.assertContains(resposta, "Mesa 2, livre")
        self.assertNotContains(resposta, "Mesa 3")
        self.assertNotContains(resposta, "Comandas em andamento")
        self.assertEqual(resposta.context["total_mesas"], 2)

    def test_mesa_selecionada_no_painel_preenche_formulario_de_nova_comanda(self):
        resposta = self.client.get(reverse("atendimento:nova_comanda"), {"mesa": self.mesa.pk})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(str(resposta.context["form"]["mesa"].value()), str(self.mesa.pk))
        self.assertContains(resposta, f'<option value="{self.mesa.pk}" selected')

    def test_abre_comanda_para_mesa(self):
        resposta = self.client.post(reverse("atendimento:nova_comanda"), {"canal": Comanda.Canal.MESA, "mesa": self.mesa.pk, "cliente": "", "observacao": ""})
        comanda = Comanda.objects.get()
        self.assertRedirects(resposta, reverse("atendimento:comanda", kwargs={"pk": comanda.pk}))
        self.assertEqual(comanda.mesa, self.mesa)

    def test_impede_duas_comandas_abertas_na_mesma_mesa(self):
        Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        resposta = self.client.post(reverse("atendimento:nova_comanda"), {"canal": Comanda.Canal.MESA, "mesa": self.mesa.pk, "cliente": "", "observacao": ""})
        self.assertEqual(Comanda.objects.count(), 1)
        self.assertContains(resposta, "Já existe uma comanda aberta nesta mesa")

    def test_adiciona_item_e_impede_pagamento_acima_do_saldo(self):
        caixa = Caixa.objects.create(valor_inicial=Decimal("50.00"), criado_por=self.user, atualizado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        self.client.post(reverse("atendimento:adicionar_item", kwargs={"pk": comanda.pk}), {"produto": self.produto.pk, "quantidade": "2", "observacao": "", "adicionais": []})
        item = ComandaItem.objects.get(comanda=comanda)
        self.assertEqual(item.total, Decimal("25.00"))
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.ENVIADO)
        url = reverse("atendimento:registrar_pagamento", kwargs={"pk": comanda.pk})
        resposta = self.client.post(url, {"forma": Pagamento.Forma.PIX, "valor": "30.00", "referencia": ""}, follow=True)
        self.assertEqual(Pagamento.objects.count(), 0)
        self.assertContains(resposta, "supera o saldo")
        self.client.post(url, {"forma": Pagamento.Forma.PIX, "valor": "25.00", "referencia": ""})
        self.assertEqual(Pagamento.objects.get().caixa, caixa)
        self.assertEqual(comanda.saldo, Decimal("0.00"))


    def test_adicionais_vinculados_aparecem_e_sao_salvos_na_comanda(self):
        adicional = Adicional.objects.create(nome="Queijo extra", preco=Decimal("2.00"), criado_por=self.user, atualizado_por=self.user)
        ProdutoAdicional.objects.create(produto=self.produto, adicional=adicional, criado_por=self.user, atualizado_por=self.user)
        url = reverse("atendimento:comanda", kwargs={"pk": Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user).pk})
        resposta = self.client.get(url, {"produto": self.produto.pk})
        self.assertContains(resposta, "Queijo extra — R$ 2,00")
        comanda = Comanda.objects.get()
        self.client.post(reverse("atendimento:adicionar_item", kwargs={"pk": comanda.pk}), {"produto": self.produto.pk, "quantidade": "1", "observacao": "", "adicionais": [adicional.pk]})
        self.assertEqual(ItemAdicional.objects.get().adicional, adicional)
        self.assertEqual(comanda.total, Decimal("14.50"))

    def test_pagamentos_parciais_quitam_e_encerram_comanda_automaticamente(self):
        caixa = Caixa.objects.create(criado_por=self.user, atualizado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        item = ComandaItem.objects.create(
            comanda=comanda, produto=self.produto, produto_nome=self.produto.nome,
            quantidade=1, preco_unitario=self.produto.preco, status_producao=ComandaItem.StatusProducao.ENVIADO,
         criado_por=self.user, atualizado_por=self.user)
        url = reverse("atendimento:registrar_pagamento", kwargs={"pk": comanda.pk})
        resposta = self.client.post(url, {"forma": Pagamento.Forma.PIX, "valor": "5.00", "referencia": ""})
        self.assertRedirects(resposta, reverse("atendimento:comanda", kwargs={"pk": comanda.pk}))
        comanda.refresh_from_db()
        self.assertEqual(comanda.status, Comanda.Status.ABERTA)
        self.assertEqual(comanda.saldo, Decimal("7.50"))
        resposta = self.client.post(url, {"forma": Pagamento.Forma.DINHEIRO, "valor": "7.50", "referencia": ""})
        self.assertRedirects(resposta, reverse("atendimento:inicio"))
        comanda.refresh_from_db()
        self.assertEqual(comanda.status, Comanda.Status.FECHADA)
        self.assertIsNotNone(comanda.fechada_em)
        self.assertEqual(comanda.total_pago, Decimal("12.50"))
        self.assertEqual(Pagamento.objects.filter(caixa=caixa).count(), 2)
        # O item permanece acessível à cozinha mesmo após a quitação automática.
        self.assertContains(self.client.get(reverse("atendimento:cozinha")), self.produto.nome)

    def test_item_cancelado_e_adicional_preservados_mas_excluidos_do_total(self):
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        item = ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome, quantidade=1, preco_unitario="12.50", criado_por=self.user, atualizado_por=self.user)
        adicional = Adicional.objects.create(nome="Queijo extra", preco="2.00", criado_por=self.user, atualizado_por=self.user)
        ItemAdicional.objects.create(item=item, adicional=adicional, adicional_nome=adicional.nome, preco_unitario="2.00", criado_por=self.user, atualizado_por=self.user)
        self.client.post(reverse("atendimento:cancelar_item", kwargs={"pk": comanda.pk, "item_id": item.pk}))
        item.refresh_from_db()
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.CANCELADO)
        self.assertTrue(item.adicionais.exists())
        self.assertEqual(comanda.total, Decimal("0.00"))

    def test_impede_cancelamento_que_supere_pagamentos(self):
        caixa = Caixa.objects.create(criado_por=self.user, atualizado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        item = ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome, quantidade=1, preco_unitario=self.produto.preco, criado_por=self.user, atualizado_por=self.user)
        Pagamento.objects.create(comanda=comanda, caixa=caixa, forma=Pagamento.Forma.DINHEIRO, valor=self.produto.preco, criado_por=self.user, atualizado_por=self.user)
        resposta = self.client.post(reverse("atendimento:cancelar_item", kwargs={"pk": comanda.pk, "item_id": item.pk}), follow=True)
        item.refresh_from_db()
        self.assertContains(resposta, "pagamentos já registrados")
        self.assertNotEqual(item.status_producao, ComandaItem.StatusProducao.CANCELADO)
        self.assertEqual(comanda.total, comanda.total_pago)

    def test_fecha_comanda_apenas_com_saldo_quitado_e_itens_prontos(self):
        caixa = Caixa.objects.create(criado_por=self.user, atualizado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        item = ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome, quantidade=1, preco_unitario=self.produto.preco, criado_por=self.user, atualizado_por=self.user)
        Pagamento.objects.create( comanda=comanda, caixa=caixa, forma=Pagamento.Forma.DINHEIRO, valor=self.produto.preco, criado_por=self.user, atualizado_por=self.user)

        self.client.post(reverse("atendimento:fechar_comanda", kwargs={"pk": comanda.pk}), follow=True)

        comanda.refresh_from_db()
        item.refresh_from_db()

        self.assertEqual(comanda.status, Comanda.Status.FECHADA)
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.PRONTO)

    def test_cozinha_avanca_item_pendente_ate_pronto(self):
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        item = ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome, quantidade=1, preco_unitario=self.produto.preco, criado_por=self.user, atualizado_por=self.user)
        self.assertContains(self.client.get(reverse("atendimento:cozinha")), "Pastel de queijo")
        self.client.post(reverse("atendimento:atualizar_cozinha", kwargs={"item_id": item.pk, "status": "ENVIADO"}))
        item.refresh_from_db()
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.ENVIADO)
        self.client.post(reverse("atendimento:atualizar_cozinha", kwargs={"item_id": item.pk, "status": "PRONTO"}))
        item.refresh_from_db()
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.PRONTO)

    def test_produto_fora_da_cozinha_fica_pronto(self):
        produto = Produto.objects.create(nome="Suco pronto", categoria=self.categoria, preco=Decimal("6.00"), vai_para_cozinha=False, criado_por=self.user, atualizado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        self.client.post(reverse("atendimento:adicionar_item", kwargs={"pk": comanda.pk}), {"produto": produto.pk, "quantidade": "1", "observacao": "", "adicionais": []})
        item = ComandaItem.objects.get(comanda=comanda)
        self.assertEqual(item.status_producao, ComandaItem.StatusProducao.PRONTO)
        resposta = self.client.get(reverse("atendimento:cozinha"))
        self.assertFalse(resposta.context["itens"].filter(pk=item.pk).exists())

    def test_abertura_movimentacao_e_fechamento_do_caixa(self):
        self.client.post(reverse("atendimento:abrir_caixa"), {"valor_inicial": "100.00", "observacao": ""})
        caixa = Caixa.objects.get(status=Caixa.Status.ABERTO)
        resposta = self.client.post(
            reverse("atendimento:registrar_movimentacao"),
            {
                "origem": "caixa",
                "tipo": "SAIDA",
                "descricao": "Compra de gelo",
                "valor": "15.00",
            },
            follow=True,
        )
        mensagens = (
            [str(mensagem) for mensagem in resposta.context["messages"]]
            if resposta.context
            else []
        )
        self.assertEqual(MovimentacaoCaixa.objects.count(), 1, f"A movimentação não foi criada. Mensagens da tela: {mensagens}")
        self.client.post(reverse("atendimento:fechar_caixa"), {"valor_fechamento": "85.00", "observacao": ""})
        caixa.refresh_from_db()
        self.assertEqual(caixa.status, Caixa.Status.FECHADO)
        self.assertEqual(caixa.valor_fechamento, Decimal("85.00"))

    def test_comanda_a_prazo_cria_conta_receber_com_cliente_e_vencimento(self):
        from datetime import date
        from .models import Cliente
        cliente = Cliente.objects.create(nome="Cliente devedor", criado_por=self.user, atualizado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome,
                                   quantidade=1, preco_unitario=self.produto.preco,
                                   status_producao=ComandaItem.StatusProducao.PRONTO, criado_por=self.user, atualizado_por=self.user)
        resposta = self.client.post(reverse("atendimento:fechar_comanda", kwargs={"pk": comanda.pk}),
                                    {"cliente": cliente.pk, "vencimento": "2026-11-10"})
        self.assertRedirects(resposta, reverse("atendimento:contas_receber"))
        comanda.refresh_from_db()
        cr = ContaReceber.objects.get(comanda=comanda)
        self.assertEqual(cr.cliente, cliente)
        self.assertEqual(cr.valor_total, Decimal("12.50"))
        self.assertEqual(cr.vencimento, date(2026, 11, 10))
        self.assertEqual(cr.status, ContaReceber.Status.ABERTA)

    def test_comanda_paga_gera_cr_quitado(self):
        caixa = Caixa.objects.create(criado_por=self.user, atualizado_por=self.user)
        comanda = Comanda.objects.create(mesa=self.mesa, criado_por=self.user, atualizado_por=self.user)
        ComandaItem.objects.create(comanda=comanda, produto=self.produto, produto_nome=self.produto.nome,
                                   quantidade=1, preco_unitario=self.produto.preco,
                                   status_producao=ComandaItem.StatusProducao.PRONTO, criado_por=self.user, atualizado_por=self.user)
        self.client.post(reverse("atendimento:registrar_pagamento", kwargs={"pk": comanda.pk}),
                         {"forma": Pagamento.Forma.PIX, "valor": "12.50", "referencia": ""})
        cr = ContaReceber.objects.get(comanda=comanda)
        self.assertEqual(cr.status, ContaReceber.Status.QUITADA)
        self.assertEqual(cr.total_recebido, Decimal("12.50"))

    def test_conta_a_pagar_e_baixa_entram_no_total_do_caixa(self):
        caixa = Caixa.objects.create(valor_inicial=Decimal("100.00"), criado_por=self.user, atualizado_por=self.user)
        conta_saida = ContaFinanceira.objects.create(nome="Banco de teste", tipo=ContaFinanceira.Tipo.BANCO, saldo_inicial=Decimal("100.00"), ativa=True, criado_por=self.user, atualizado_por=self.user)
        cp = ContaPagar.objects.create(descricao="Compra de insumos", valor_total=Decimal("30.00"), vencimento="2026-11-10", criado_por=self.user, atualizado_por=self.user)

        resposta = self.client.post(reverse("atendimento:baixar_conta_pagar", kwargs={"pk": cp.pk}),
            {
                "forma": "PIX",
                "valor": "10.00",
                "referencia": "",
                "conta_saida": conta_saida.pk,
            },
            follow=True,
        )

        cp.refresh_from_db()
        self.assertEqual(cp.status, ContaPagar.Status.PARCIAL)
        self.assertEqual(cp.saldo, Decimal("20.00"))

        from .views import _total_caixa
        self.assertEqual(_total_caixa(caixa)["esperado"], Decimal("100.00"), [str(mensagem) for mensagem in resposta.context["messages"]])

    def test_telas_da_cozinha_e_caixa_carregam(self):
        self.assertEqual(self.client.get(reverse("atendimento:cozinha")).status_code, 200)
        self.assertEqual(self.client.get(reverse("atendimento:caixa")).status_code, 200)


class LoginEPermissoesTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType
        from .models import Comanda, ComandaItem, MovimentacaoCaixa

        self.user = get_user_model().objects.create_user(username="atendente", password="senha-atendente-123")
        grupo = Group.objects.create(name="Atendente e cozinha")
        permissoes = Permission.objects.filter(
            content_type__in=ContentType.objects.get_for_models(Comanda, ComandaItem, MovimentacaoCaixa).values()
        ).filter(codename__in=["view_comanda", "add_comanda", "view_comandaitem", "change_comandaitem", "add_movimentacaocaixa"])
        grupo.permissions.set(permissoes)
        self.user.groups.add(grupo)

    def test_login_proprio_autentica_usuario_do_django(self):
        resposta = self.client.get(reverse("atendimento:login"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Entrar no sistema")
        resposta = self.client.post(reverse("atendimento:login"), {"username": "atendente", "password": "senha-atendente-123"})
        self.assertRedirects(resposta, reverse("atendimento:inicio"))
        self.assertEqual(self.client.get(reverse("atendimento:inicio")).status_code, 200)

    def test_menu_e_rotas_respeitam_permissoes_do_grupo(self):
        self.client.login(username="atendente", password="senha-atendente-123")
        resposta = self.client.get(reverse("atendimento:inicio"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Atendimento")
        self.assertContains(resposta, "Cozinha")
        self.assertNotContains(resposta, "Caixa")
        self.assertNotContains(resposta, "Cadastros")
        self.assertEqual(self.client.get(reverse("atendimento:comandas")).status_code, 200)
        self.assertEqual(self.client.get(reverse("atendimento:cozinha")).status_code, 200)
        self.assertEqual(self.client.get(reverse("atendimento:caixa")).status_code, 403)
        resposta = self.client.post(reverse("atendimento:abrir_caixa"), {"valor_inicial": "50.00"})
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(Caixa.objects.count(), 0)


    def test_atendente_lanca_movimentacao_na_tela_inicial_sem_acesso_ao_caixa(self):
        self.client.login(username="atendente", password="senha-atendente-123")
        caixa = Caixa.objects.create(valor_inicial=Decimal("20.00"), status=Caixa.Status.ABERTO, criado_por=self.user, atualizado_por=self.user)
        ContaFinanceira.objects.create(nome="Gaveta de teste", tipo=ContaFinanceira.Tipo.GAVETA, saldo_inicial=Decimal("20.00"), ativa=True, criado_por=self.user, atualizado_por=self.user)
        resposta_inicio = self.client.get(reverse("atendimento:inicio"))
        self.assertContains(resposta_inicio, "Movimentação avulsa")
        self.assertContains(resposta_inicio, "Lance uma entrada")
        resposta = self.client.post(
            reverse("atendimento:registrar_movimentacao"),
            { "origem": "inicio", "tipo": "SAIDA", "descricao": "Conta de água", "valor": "8.50" },
            follow=True,
        )
        mensagens = (
            [str(mensagem) for mensagem in resposta.context["messages"]]
            if resposta.context
            else []
        )
        self.assertEqual(MovimentacaoCaixa.objects.count(), 1, f"A movimentação não foi criada. Mensagens da tela: {mensagens}")
        movimentacao = MovimentacaoCaixa.objects.get()
        self.assertEqual(movimentacao.caixa, caixa)
        self.assertEqual(movimentacao.tipo, MovimentacaoCaixa.Tipo.SAIDA)
        self.assertEqual(movimentacao.valor, Decimal("8.50"))
        resposta_caixa = self.client.get(reverse("atendimento:caixa"))
        self.assertEqual(resposta_caixa.status_code, 403)

    def test_logout_somente_post_e_encaminha_para_login(self):
        self.client.login(username="atendente", password="senha-atendente-123")
        resposta = self.client.post(reverse("atendimento:logout"))
        self.assertRedirects(resposta, reverse("atendimento:login"))
        resposta = self.client.get(reverse("atendimento:inicio"))
        self.assertRedirects(resposta, f"{reverse('atendimento:login')}?next={reverse('atendimento:inicio')}")
