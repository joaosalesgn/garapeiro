from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .impressao import ErroImpressao, montar_comanda_cozinha, montar_comprovante_consumo
from .models import Adicional, Categoria, Comanda, ComandaItem, ItemAdicional, Mesa, Produto

data_impressao = timezone.make_aware(
    datetime(2026, 10, 13, 14, 0),
    timezone.get_current_timezone(),
)

class ImpressaoComandaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="teste_impressao", password="senha-segura-123")
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label="atendimento", codename="view_comanda"))
        categoria = Categoria.objects.create(nome="Lanches", criado_por=self.user, atualizado_por=self.user)
        self.produto_cozinha = Produto.objects.create(nome="Pastel especial", categoria=categoria, preco=Decimal("15.00"), vai_para_cozinha=True, criado_por=self.user, atualizado_por=self.user)
        self.produto_bebida = Produto.objects.create(nome="Suco", categoria=categoria, preco=Decimal("7.00"), vai_para_cozinha=False, criado_por=self.user, atualizado_por=self.user)
        mesa = Mesa.objects.create(numero=2, criado_por=self.user, atualizado_por=self.user)
        self.comanda = Comanda.objects.create(mesa=mesa, criado_por=self.user, atualizado_por=self.user)
        self.item = ComandaItem.objects.create(comanda=self.comanda, produto=self.produto_cozinha, produto_nome=self.produto_cozinha.nome, quantidade=2, preco_unitario=Decimal("15.00"), criado_por=self.user, atualizado_por=self.user)
        self.client.force_login(self.user)


    @patch("atendimento.views.imprimir_itens_cozinha")
    def test_cozinha_imprime_apenas_itens_novos_e_registra_data(self, imprimir):
        url = reverse("atendimento:imprimir_comanda_cozinha", args=[self.comanda.pk])
        response = self.client.post(url, {"reimprimir_tudo": "0"})
        self.assertEqual(response.status_code, 302)
        imprimir.assert_called_once()
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.cozinha_impresso_em)

    @patch("atendimento.views.imprimir_itens_cozinha")
    def test_reimprimir_tudo_inclui_itens_ja_impressos(self, imprimir):
        self.item.cozinha_impresso_em = data_impressao
        self.item.save(update_fields=["cozinha_impresso_em"])
        url = reverse("atendimento:imprimir_comanda_cozinha", args=[self.comanda.pk])
        response = self.client.post(url, {"reimprimir_tudo": "1"})
        self.assertEqual(response.status_code, 302)
        imprimir.assert_called_once()

    @patch("atendimento.views.imprimir_itens_cozinha")
    def test_novo_item_e_impresso_sem_repetir_item_anterior(self, imprimir):
        self.item.cozinha_impresso_em = data_impressao
        self.item.save(update_fields=["cozinha_impresso_em"])
        segundo = ComandaItem.objects.create(comanda=self.comanda, produto=self.produto_cozinha, produto_nome=self.produto_cozinha.nome, quantidade=1, preco_unitario=Decimal("15.00"), criado_por=self.user, atualizado_por=self.user)
        url = reverse("atendimento:imprimir_comanda_cozinha", args=[self.comanda.pk])
        self.client.post(url, {"reimprimir_tudo": "0"})
        impressos = imprimir.call_args.args[1]
        self.assertEqual([obj.pk for obj in impressos], [segundo.pk])

    @patch("atendimento.views.imprimir_itens_cozinha", side_effect=ErroImpressao("impressora indisponível"))
    def test_falha_na_impressora_nao_marca_item_como_impresso(self, imprimir):
        url = reverse("atendimento:imprimir_comanda_cozinha", args=[self.comanda.pk])
        self.client.post(url, {"reimprimir_tudo": "0"})
        self.item.refresh_from_db()
        self.assertIsNone(self.item.cozinha_impresso_em)

    @patch("atendimento.views.imprimir_itens_consumo")
    def test_imprime_conferencia_com_todos_os_itens_validos(self, imprimir):
        url = reverse("atendimento:imprimir_comanda_consumo", args=[self.comanda.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        imprimir.assert_called_once()

    def test_comprovante_cozinha_sem_valores_com_identificacao_e_horario(self):
        texto = montar_comanda_cozinha(self.comanda, [self.item], datetime(2026, 10, 13, 14, 5))
        self.assertIn("COZINHA", texto)
        self.assertIn("Mesa 2", texto)
        self.assertIn("Pastel especial", texto)
        self.assertIn("13/10/2026 14:05:00", texto)
        self.assertNotIn("15,00", texto)

    def test_comprovante_consumo_inclui_adicionais_e_total(self):
        adicional = Adicional.objects.create(nome="Creme", preco=Decimal("2.00"), criado_por=self.user, atualizado_por=self.user)
        ItemAdicional.objects.create(item=self.item, adicional=adicional, adicional_nome="Creme", quantidade=1, preco_unitario=Decimal("2.00"), criado_por=self.user, atualizado_por=self.user)
        texto = montar_comprovante_consumo(self.comanda, [self.item], datetime(2026, 10, 13, 14, 5))
        self.assertIn("Pastel especial", texto)
        self.assertIn("Creme", texto)
        self.assertIn("TOTAL: R$ 32,00", texto)
