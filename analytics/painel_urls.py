"""As rotas do painel de analytics, montadas sob /gestao/analytics/ pela
gestao/urls.py — separadas de `analytics/urls.py` (a ingestão) porque são outra
coisa: aquela é máquina, esta é gerência."""
from django.urls import path

from . import painel

app_name = "analytics_painel"

urlpatterns = [
    path("", painel.VisaoGeralView.as_view(), name="geral"),
    path("explorar/", painel.ExplorarView.as_view(), name="explorar"),
    path("funil/", painel.FunilView.as_view(), name="funil"),
    path("retencao/", painel.RetencaoView.as_view(), name="retencao"),
    path("usuario/", painel.UsuarioView.as_view(), name="usuario"),
]
