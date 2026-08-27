from django.urls import path

from . import views

app_name = "demo"

urlpatterns = [
    path("", views.DemoHomeView.as_view(), name="home"),
    path("sobre/", views.DemoSobreView.as_view(), name="sobre"),
]
