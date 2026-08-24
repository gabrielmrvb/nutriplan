r"""Dispara os lembretes das refeições que estão chegando.

Feito para rodar de poucos em poucos minutos no agendador do sistema
(Agendador de Tarefas no Windows, cron no Linux):

    .venv\Scripts\python.exe manage.py send_meal_reminders

Rodar duas vezes no mesmo minuto é seguro: a unicidade
(usuário, refeição, dia) no banco é que decide quem já foi avisado.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from push.services import due_slots, push_is_configured, send_meal_reminders


class Command(BaseCommand):
    help = "Envia as notificações das refeições próximas do horário."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Só lista o que seria enviado, sem enviar nem registrar.",
        )

    def handle(self, *args, **options):
        now = timezone.localtime()

        if not push_is_configured():
            self.stderr.write(
                "VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY não configuradas — nada a enviar."
            )
            return

        if options["dry_run"]:
            slots = list(due_slots(now))
            self.stdout.write(f"{now:%d/%m %H:%M} — {len(slots)} refeição(ões) na janela:")
            for slot in slots:
                self.stdout.write(f"  {slot.time:%H:%M} {slot.name} → {slot.plan.user}")
            return

        result = send_meal_reminders(now)
        self.stdout.write(
            self.style.SUCCESS(
                f"{now:%d/%m %H:%M} — enviadas: {result['sent']}, "
                f"puladas: {result['skipped']}, falhas: {result['failed']}"
            )
        )
