from django.urls import path

from . import views

app_name = "achievements"

urlpatterns = [
    path("", views.ConquistasView.as_view(), name="list"),
    path("vistas/", views.MarcarVistasView.as_view(), name="marcar_vistas"),
]
