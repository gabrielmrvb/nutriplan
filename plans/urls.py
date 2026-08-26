from django.urls import path

from . import views

app_name = "plans"

urlpatterns = [
    path("", views.TodayView.as_view(), name="today"),
    path("historico/", views.HistoryView.as_view(), name="history"),
    path("refeicao/<int:slot_id>/marcar/", views.MarkMealView.as_view(), name="mark_meal"),
    path("refeicao/<int:slot_id>/desfazer/", views.ClearMealView.as_view(), name="clear_meal"),
    path("recalcular/", views.RecalculatePlanView.as_view(), name="recalculate"),
    path("recalibrar/", views.RecalibrateView.as_view(), name="recalibrate"),
    path("agua/", views.LogHydrationView.as_view(), name="log_hydration"),
    path("lista-de-compras/", views.ShoppingListView.as_view(), name="shopping"),
    path(
        "opcao/<int:option_id>/substituir/",
        views.SubstituteOptionView.as_view(),
        name="substitute_option",
    ),
    path(
        "alimento/<int:food_id>/substituir/",
        views.SubstituteFoodView.as_view(),
        name="substitute_food",
    ),
]
