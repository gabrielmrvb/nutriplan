# -*- coding: utf-8 -*-
"""O número que decide o plano Starter (21/09/2026): quantas SESSÕES distintas
o app viu na mesma janela de 5 minutos, no pior momento de cada dia.

    manage.py pico_de_sessoes [--dias 7] [--janela 5]

O k6 mediu o teto do free em 5 usuários simultâneos (p95 < 2 s, zero erro) e
o degrau seguinte em 10 (p95 até 6 s, ainda sem erro). Este comando lê os
eventos do analytics (`session_id`, `ts`) e agrupa em janelas fixas de
`--janela` minutos: o pico do dia é a janela com mais sessões distintas.
Quando o pico passa do teto em dois dias da mesma semana, é hora do Starter
— a régua está no CLAUDE.md, "Deploy". Só leitura: UMA consulta (sessão +
minuto, sem repetição) e o resto em memória, sem ler conteúdo de evento.
"""
from django.core.management.base import BaseCommand
from django.db.models.functions import TruncMinute
from django.utils import timezone

from analytics.models import Event


def picos(dias, janela, agora=None):
    """[(dia, pico, janela_inicio)] — sessões DISTINTAS por janela fixa de
    `janela` minutos; o pico do dia é a janela mais cheia. UMA consulta
    (`session_id` + minuto, sem repetição), o resto em memória — o app é
    pequeno, e a conta certa (conjuntos por janela) não cabe num GROUP BY."""
    agora = agora or timezone.now()
    inicio = agora - timezone.timedelta(days=dias)
    pares = (
        Event.objects.filter(ts__gte=inicio).exclude(session_id="")
        .annotate(minuto=TruncMinute("ts"))
        .values_list("session_id", "minuto").distinct()
    )
    sessoes_por_janela = {}
    for sessao, minuto in pares:
        m = timezone.localtime(minuto)
        balde = m.replace(minute=m.minute - (m.minute % janela), second=0, microsecond=0)
        sessoes_por_janela.setdefault(balde, set()).add(sessao)
    por_dia = {}
    for balde, sessoes in sessoes_por_janela.items():
        dia = balde.date()
        if dia not in por_dia or len(sessoes) > por_dia[dia][0]:
            por_dia[dia] = (len(sessoes), balde)
    return [(dia, pico, balde) for dia, (pico, balde) in sorted(por_dia.items())]


class Command(BaseCommand):
    help = "Pico de sessões distintas por janela de minutos, por dia — o número que decide o plano Starter."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=7)
        parser.add_argument("--janela", type=int, default=5)
        parser.add_argument("--teto", type=int, default=5, help="o teto medido pelo k6 (usuários simultâneos)")

    def handle(self, *args, **opts):
        lista = picos(opts["dias"], opts["janela"])
        if not lista:
            self.stdout.write("sem eventos nos últimos %d dias" % opts["dias"])
            return
        acima = 0
        for dia, pico, balde in lista:
            marca = "  ← acima do teto (%d)" % opts["teto"] if pico >= opts["teto"] else ""
            acima += 1 if pico >= opts["teto"] else 0
            self.stdout.write("%s  pico %2d sessões  (janela das %s)%s" % (dia.isoformat(), pico, balde.strftime("%H:%M"), marca))
        self.stdout.write("dias no teto ou acima: %d de %d — Starter quando forem 2 na mesma semana" % (acima, len(lista)))
