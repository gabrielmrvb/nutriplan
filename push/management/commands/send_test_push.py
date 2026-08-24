r"""Manda uma notificação de teste para os dispositivos de uma pessoa.

Serve para conferir a ponta a ponta depois de clicar em "Ativar lembretes":

    .venv\Scripts\python.exe manage.py send_test_push voce@email.com

Diferente do send_meal_reminders, este comando ignora horário e não grava
NotificationLog — é ferramenta de diagnóstico, não parte do fluxo.
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from push.models import PushSubscription
from push.services import notify_user, push_is_configured


class Command(BaseCommand):
    help = "Envia uma notificação de teste para os dispositivos de um usuário."

    def add_arguments(self, parser):
        parser.add_argument("email", help="E-mail da pessoa que vai receber.")

    def handle(self, *args, **options):
        if not push_is_configured():
            raise CommandError("VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY não configuradas.")

        try:
            user = User.objects.get(email__iexact=options["email"])
        except User.DoesNotExist:
            raise CommandError(f"Nenhum usuário com o e-mail {options['email']}.")

        devices = PushSubscription.objects.filter(user=user, is_active=True).count()
        if not devices:
            raise CommandError(
                f"{user.email} não tem dispositivo inscrito. Abra o app, clique em "
                '"Ativar lembretes das refeições" e permita a notificação.'
            )

        delivered = notify_user(
            user,
            {
                "title": "NutriPlan funcionando",
                "body": "Se você está lendo isso, os lembretes estão no ar.",
                "url": "/",
                "tag": "teste",
            },
        )
        if delivered:
            self.stdout.write(
                self.style.SUCCESS(f"Enviada para {delivered} de {devices} dispositivo(s).")
            )
        else:
            self.stderr.write(
                f"Nenhum dos {devices} dispositivo(s) aceitou. Veja o log para o motivo."
            )
