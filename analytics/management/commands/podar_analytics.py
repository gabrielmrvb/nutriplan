"""Apaga o evento bruto com mais de 90 dias.

O bruto é uma linha por toque e é o que mais cresce; 90 dias é o que o painel
precisa ver com todas as propriedades. Passado isso, o AGREGADO (sem prazo, sem
PII) guarda a série. Roda no build, por último, depois de agregar — assim o dia
que vai ser podado já virou agregado.

Idempotente: rodar duas vezes apaga na primeira e não acha nada na segunda.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import Event


class Command(BaseCommand):
    help = "Apaga eventos brutos anteriores ao prazo de retenção (padrão 90 dias)."

    def handle(self, *args, **opts):
        dias = getattr(settings, "ANALYTICS_RETENCAO_DIAS", 90)
        corte = timezone.now() - timezone.timedelta(days=dias)
        apagados, _ = Event.objects.filter(ts__lt=corte).delete()
        self.stdout.write(f"podados {apagados} eventos anteriores a {corte:%Y-%m-%d}")
