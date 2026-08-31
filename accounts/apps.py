from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Contas"

    def ready(self):
        # Importar registra as verificações de configuração. `manage.py check`
        # roda no build, então a produção falha ANTES de subir quando o e-mail
        # não está configurado — em vez de subir e escrever link de senha no log.
        from . import checks  # noqa: F401
