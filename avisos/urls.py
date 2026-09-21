from django.urls import path

from . import views

app_name = "avisos"

urlpatterns = [
    path("", views.PreferenciasView.as_view(), name="preferencias"),
    path("sair/<str:chave>/", views.DescadastroView.as_view(), name="descadastro"),
]
