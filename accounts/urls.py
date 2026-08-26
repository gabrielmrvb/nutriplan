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
    path(
        "profissionais/",
        views.ProfessionalsView.as_view(),
        name="professionals",
    ),
]
