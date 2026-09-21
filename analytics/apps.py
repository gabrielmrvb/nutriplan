from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
    verbose_name = "analytics de produto"

    def ready(self):
        # Registra o "alias": ao entrar, o histórico anônimo daquele
        # aparelho passa a apontar para a pessoa. Ver analytics/identidade.py.
        from . import identidade  # noqa: F401
