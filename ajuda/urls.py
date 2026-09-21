from django.urls import path

from . import views

app_name = "ajuda"

urlpatterns = [
    path("", views.AjudaView.as_view(), name="index"),
    path("reportar/", views.ReportarView.as_view(), name="reportar"),
    path("reportar/enviado/", views.ReportadoView.as_view(), name="reportado"),
    path("o-que-mudou/", views.MudancasView.as_view(), name="mudancas"),
]
