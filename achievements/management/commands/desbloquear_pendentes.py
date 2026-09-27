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

Roda no build, e o filtro o torna barato para sempre. Entra quem está num
destes dois estados, e cada um SAI dele depois da primeira avaliação:

- tem registro de TREINO e zero conquistas — sai com "Primeiro treino";
- tem CORRIDA e não tem "Primeira corrida" — sai com ela. Este segundo ramo
  entrou com as quatro regras de corrida (revisão do PR #162, 27/09/2026):
  o filtro só por treino deixava de fora justamente quem o item 4 veio
  atender — quem só corre não tem `ExerciseLog` — e também quem já tinha
  uma medalha de treino. Nos dois casos "Primeira corrida 1/1" ficava
  trancada com a barra cheia, que é o defeito B35 de 16/09/2026, palavra por
  palavra, até a pessoa registrar outra corrida.

Numa base sem ninguém nesses estados, custa UMA consulta.

UMA CONTA NÃO DERRUBA O BUILD. Este comando itera dado de USUÁRIO dentro de
um `build.sh` com `errexit`; uma pessoa num estado que `reunir` não digere
derrubaria todo deploy seguinte. O erro é registrado com o id e o laço segue.
"""
import logging

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q

from accounts.models import User
from achievements import services
from achievements.models import UserAchievement
from workouts.models import Corrida, ExerciseLog

logger = logging.getLogger(__name__)


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
                tem_corrida=Exists(Corrida.objects.filter(user=OuterRef("pk"))),
                tem_primeira_corrida=Exists(
                    UserAchievement.objects.filter(
                        user=OuterRef("pk"), slug="primeira-corrida"
                    )
                ),
            )
            .filter(
                Q(tem_treino=True, tem_conquista=False)
                | Q(tem_corrida=True, tem_primeira_corrida=False)
            )
            .order_by("pk")
        )
        total, nascidas, falhas = 0, 0, 0
        for user in pendentes:
            total += 1
            if opcoes["dry_run"]:
                continue
            try:
                nascidas += len(services.avaliar(user))
            except Exception:  # noqa: BLE001 — ver "UMA CONTA NÃO DERRUBA O BUILD"
                falhas += 1
                logger.exception("desbloquear_pendentes: falhou para a conta %s", user.pk)
        if opcoes["dry_run"]:
            self.stdout.write("%d pessoa(s) seriam avaliadas" % total)
            return
        self.stdout.write(
            "%d pessoa(s) avaliadas, %d conquista(s) desbloqueada(s), %d falha(s)"
            % (total, nascidas, falhas)
        )
