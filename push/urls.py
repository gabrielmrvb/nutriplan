from django.urls import path

from . import views

app_name = "push"

urlpatterns = [
    path("inscrever/", views.SubscribeView.as_view(), name="subscribe"),
    path("cancelar/", views.UnsubscribeView.as_view(), name="unsubscribe"),
]
