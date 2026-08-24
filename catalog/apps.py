from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "Catálogo de alimentos e refeições"

    def ready(self):
        from . import signals  # noqa: F401
