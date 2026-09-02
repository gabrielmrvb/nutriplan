from django.urls import path

from . import views

app_name = "gestao"

urlpatterns = [
    path("", views.PainelView.as_view(), name="painel"),
    path("pessoas/", views.PessoasView.as_view(), name="pessoas"),
    path("atividade/", views.AtividadeView.as_view(), name="atividade"),
]
