from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    # Curto de propósito: é chamado por sendBeacon em toda tela; cada byte da
    # URL viaja junto.
    path("e/", views.IngestView.as_view(), name="ingest"),
]
