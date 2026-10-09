from django.urls import path

from . import views

app_name = "atendimento"

urlpatterns = [
    path("", views.atendimento, name="lista"),
    path("comanda/<int:pk>/", views.comanda_detalhe, name="comanda"),
    path("comanda/<int:pk>/item/<int:item_id>/remover/", views.remover_item, name="remover_item"),
    path("cozinha/", views.cozinha, name="cozinha"),
    path("cozinha/item/<int:item_id>/", views.atualizar_producao, name="atualizar_producao"),
    path("caixa/", views.caixa, name="caixa"),
]
