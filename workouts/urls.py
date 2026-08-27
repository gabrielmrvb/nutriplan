from django.urls import path

from . import views

app_name = "workouts"

urlpatterns = [
    path("", views.WorkoutView.as_view(), name="routine"),
    path(
        "exercicio/<int:exercise_id>/carga/",
        views.RecordLoadView.as_view(),
        name="record_load",
    ),
    path("exportar/saude.tcx", views.HealthExportView.as_view(), name="health_export"),
]
