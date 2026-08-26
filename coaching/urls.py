from django.urls import path

from . import views

app_name = "coaching"

urlpatterns = [
    path("", views.PanelView.as_view(), name="panel"),
    path("cadastro/", views.ProfessionalSignupView.as_view(), name="signup"),
    path("convite/", views.InviteCreateView.as_view(), name="invite_create"),
    path(
        "convite/<int:link_id>/cancelar/",
        views.InviteCancelView.as_view(),
        name="invite_cancel",
    ),
    # ------------------------------------------------- o lado do aluno
    path("vinculo/<int:link_id>/revogar/", views.RevokeView.as_view(), name="revoke"),
    path("avisos/vistos/", views.DismissUpdateView.as_view(), name="dismiss_updates"),
    # --------------------------------------------------------- a central
    path(
        "aluno/<int:student_id>/",
        views.StudentMonitorView.as_view(),
        name="student_monitor",
    ),
    path(
        "aluno/<int:student_id>/treino/",
        views.StudentWorkoutView.as_view(),
        name="student_workout",
    ),
    path(
        "aluno/<int:student_id>/dieta/",
        views.StudentNutritionView.as_view(),
        name="student_nutrition",
    ),
    # ------------------------------------------------------- prescrição
    path(
        "aluno/<int:student_id>/exercicio/<int:item_id>/ajustar/",
        views.AjustarExercicioView.as_view(),
        name="adjust_exercise",
    ),
    path(
        "aluno/<int:student_id>/exercicio/<int:item_id>/trocar/",
        views.TrocarExercicioView.as_view(),
        name="swap_exercise",
    ),
    path(
        "aluno/<int:student_id>/exercicio/<int:item_id>/remover/",
        views.RemoverExercicioView.as_view(),
        name="remove_exercise",
    ),
    path(
        "aluno/<int:student_id>/sessao/<int:session_id>/incluir/",
        views.AdicionarExercicioView.as_view(),
        name="add_exercise",
    ),
    path(
        "aluno/<int:student_id>/sessao/<int:session_id>/clonar/",
        views.ClonarModeloView.as_view(),
        name="clone_template",
    ),
    path(
        "aluno/<int:student_id>/metas/",
        views.AjustarMetasView.as_view(),
        name="adjust_targets",
    ),
    path(
        "aluno/<int:student_id>/opcao/<int:option_id>/trocar/",
        views.TrocarOpcaoView.as_view(),
        name="swap_option",
    ),
]
