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
    path(
        "ficha/<int:session_id>/ajustar/",
        views.AssistantView.as_view(),
        name="assistant",
    ),
    path(
        "ficha/<int:session_id>/ajustar/aplicar/",
        views.AssistantApplyView.as_view(),
        name="assistant_apply",
    ),
]
