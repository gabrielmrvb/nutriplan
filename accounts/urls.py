from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("cadastro/", views.SignupView.as_view(), name="signup"),
    path("entrar/", views.AppLoginView.as_view(), name="login"),
    path("sair/", LogoutView.as_view(), name="logout"),
    path("onboarding/", views.OnboardingEntryView.as_view(), name="onboarding"),
    path("onboarding/<int:step>/", views.onboarding_step, name="onboarding_step"),
    path("perfil/", views.ProfileSummaryView.as_view(), name="profile"),
    # O peso mora em accounts e continua com um escritor só. Uma rota em
    # `plans` deixaria WeightEntry sendo gravado de dois apps, com duas
    # validações para manter em sincronia.
    path("peso/", views.WeightLogView.as_view(), name="log_weight"),
]
