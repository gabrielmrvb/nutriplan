from django.urls import path

from . import views

app_name = "supplements"

urlpatterns = [
    path("", views.SupplementListView.as_view(), name="list"),
    path(
        "<int:supplement_id>/marcar/",
        views.ToggleSupplementView.as_view(),
        name="toggle",
    ),
]
