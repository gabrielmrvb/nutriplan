from django.contrib import admin
from django.urls import include, path

from push import views as push_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # O service worker precisa vir da raiz: um arquivo servido de /static/ só
    # teria escopo sobre /static/ e não controlaria as páginas do app.
    path("sw.js", push_views.ServiceWorkerView.as_view(), name="service_worker"),
    path("manifest.webmanifest", push_views.ManifestView.as_view(), name="manifest"),
    path("offline/", push_views.OfflineView.as_view(), name="offline"),
    path("conta/", include("accounts.urls")),
    path("push/", include("push.urls")),
    path("treino/", include("workouts.urls")),
    path("", include("plans.urls")),
]
