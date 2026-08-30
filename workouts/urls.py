from django.urls import path

from . import views

app_name = "workouts"

urlpatterns = [
    path("", views.WorkoutView.as_view(), name="routine"),
    # O modo treino é uma tela própria, e não uma âncora dentro da lista: a
    # pessoa precisa poder voltar para ele, recarregar e compartilhar o
    # endereço sem cair no meio de uma página de cinco mil pixels.
    path("agora/", views.ModoTreinoView.as_view(), name="now"),
    path("agora/serie/", views.ConcluirSerieView.as_view(), name="record_set"),
    path(
        "exercicio/<int:exercise_id>/carga/",
        views.RecordLoadView.as_view(),
        name="record_load",
    ),
    path("exportar/saude.tcx", views.HealthExportView.as_view(), name="health_export"),
]
