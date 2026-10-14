from django.urls import path

from . import views

app_name = "atendimento"

urlpatterns = [
    path("login/", views.LoginSistemaView.as_view(), name="login"),
    path("logout/", views.logout_sistema, name="logout"),
    path("", views.inicio, name="inicio"),
    path("comandas/", views.comandas, name="comandas"),
    path("comandas/nova/", views.nova_comanda, name="nova_comanda"),
    path("comandas/<int:pk>/", views.detalhe_comanda, name="comanda"),
    path("comandas/<int:pk>/imprimir/cozinha/", views.imprimir_comanda_cozinha, name="imprimir_comanda_cozinha"),
    path("comandas/<int:pk>/imprimir/consumo/", views.imprimir_comanda_consumo, name="imprimir_comanda_consumo"),
    path("comandas/<int:pk>/itens/adicionar/", views.adicionar_item, name="adicionar_item"),
    path("comandas/<int:pk>/itens/<int:item_id>/cancelar/", views.cancelar_item, name="cancelar_item"),
    path("comandas/<int:pk>/pagamentos/", views.registrar_pagamento, name="registrar_pagamento"),
    path("comandas/<int:pk>/fechar/", views.fechar_comanda, name="fechar_comanda"),
    path("cozinha/", views.cozinha, name="cozinha"),
    path("cozinha/itens/<int:item_id>/<str:status>/", views.atualizar_cozinha, name="atualizar_cozinha"),
    path("contas-a-receber/", views.contas_receber, name="contas_receber"),
    path("contas-a-receber/<int:pk>/receber/", views.receber_conta, name="receber_conta"),
    path("contas-a-pagar/", views.contas_pagar, name="contas_pagar"),
    path("contas-a-pagar/<int:pk>/baixar/", views.baixar_conta_pagar, name="baixar_conta_pagar"),
    path("caixa/", views.caixa, name="caixa"),
    path("caixa/abrir/", views.abrir_caixa, name="abrir_caixa"),
    path("caixa/movimentacoes/", views.registrar_movimentacao, name="registrar_movimentacao"),
    path("caixa/fechar/", views.fechar_caixa, name="fechar_caixa"),
]
