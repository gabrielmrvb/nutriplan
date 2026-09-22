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

        # A data de vencimento entra na sessão no login (config/sessao.py):
        # é o que deixa `RenovarSessaoMiddleware` renovar sem consulta.
        from django.contrib.auth.signals import user_logged_in

        from config.sessao import marcar_vencimento_no_login

        user_logged_in.connect(marcar_vencimento_no_login, dispatch_uid="nutriplan.sessao.vencimento")
