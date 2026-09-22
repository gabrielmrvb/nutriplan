from django.urls import path

from . import views

app_name = "push"

urlpatterns = [
    path("inscrever/", views.SubscribeView.as_view(), name="subscribe"),
    path("cancelar/", views.UnsubscribeView.as_view(), name="unsubscribe"),
    # O app instalado (casca nativa): token do FCM em vez de assinatura Web Push.
    path("nativo/registrar/", views.RegistrarDispositivoNativoView.as_view(), name="dispositivo_registrar"),
    path("nativo/remover/", views.RemoverDispositivoNativoView.as_view(), name="dispositivo_remover"),
]
