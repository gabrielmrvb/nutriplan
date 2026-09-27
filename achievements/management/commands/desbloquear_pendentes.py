# -*- coding: utf-8 -*-
"""Avalia quem TEM histórico e NENHUMA conquista — a retroatividade, sem GET.

Até 26/09/2026 esta conta era paga por `ConquistasView`: ela chamava
`avaliar` no GET, e a razão escrita era exatamente esta — "quem já tinha
histórico quando as conquistas nasceram nunca era avaliado". O preço era um
GET que grava, com duas leituras dos mesmos dados devolvendo números
diferentes (item 0 da missão "quem entra não desiste").

A retroatividade é um trabalho de UMA VEZ por pessoa, não de toda abertura
de tela. Daqui para frente toda conquista nasce no POST que cria o fato
(série, carga, refeição, água, corrida); este comando fecha a conta de quem
já tinha fato antes de a regra existir.

Roda no build, e o filtro o torna barato para sempre: só entra quem tem
registro de treino E zero conquistas gravadas — e, depois da primeira
avaliação, essa pessoa passa a ter pelo menos "Primeiro treino" e sai da
lista. Numa base sem ninguém nessas condições, custa UMA consulta.
"""
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from accounts.models import User
from achievements import services
from achievements.models import UserAchievement
from workouts.models import ExerciseLog


class Command(BaseCommand):
    help = "Desbloqueia conquistas de quem tem histórico e nenhuma gravada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="diz quem seria avaliado, sem gravar nada",
        )

    def handle(self, *args, **opcoes):
        pendentes = (
            User.objects.annotate(
                tem_treino=Exists(ExerciseLog.objects.filter(user=OuterRef("pk"))),
                tem_conquista=Exists(
                    UserAchievement.objects.filter(user=OuterRef("pk"))
                ),
            )
            .filter(tem_treino=True, tem_conquista=False)
            .order_by("pk")
        )
        total, nascidas = 0, 0
        for user in pendentes:
            total += 1
            if opcoes["dry_run"]:
                continue
            nascidas += len(services.avaliar(user))
        if opcoes["dry_run"]:
            self.stdout.write("%d pessoa(s) seriam avaliadas" % total)
            return
        self.stdout.write(
            "%d pessoa(s) avaliadas, %d conquista(s) desbloqueada(s)" % (total, nascidas)
        )
