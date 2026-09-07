# -*- coding: utf-8 -*-
"""Confere, contra o YouTube, se cada exercício ainda aponta para o vídeo certo.

    python manage.py conferir_videos
    python manage.py conferir_videos --json

FORA DO BUILD, e isso é decisão. `scripts/build.sh` roda com `errexit`: um
soluço do YouTube durante o deploy derrubaria a publicação por um motivo que
não tem nada a ver com o que subiu. É o mesmo raciocínio já escrito em
`seed_workouts` sobre a checagem de vídeo. Este comando é para rodar à mão —
depois de mexer na curadoria, e de tempos em tempos para pegar vídeo que saiu
do ar.

O QUE ELE PEGA:
  * vídeo removido, privado ou com embed bloqueado (o link morre em silêncio);
  * título que deixou de mencionar o movimento — o sintoma de par trocado;
  * título que mudou desde a curadoria (o dono pode ter trocado o vídeo, ou o
    canal renomeou; nos dois casos alguém precisa olhar).
"""
import json

from django.core.management.base import BaseCommand

from workouts.models import Exercise
from workouts.videos import oembed, titulo_confere


class Command(BaseCommand):
    help = "Confere exercício -> vídeo contra o título real no YouTube."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true",
                            help="Saída em JSON, para outro programa ler.")

    def handle(self, *args, **options):
        linhas = []
        for exercicio in Exercise.objects.filter(is_active=True).order_by("name"):
            if not exercicio.video_id:
                linhas.append({"exercicio": exercicio.name, "id": "",
                               "estado": "SEM VIDEO", "titulo": ""})
                continue
            info = oembed(exercicio.video_id)
            if not info["vivo"]:
                linhas.append({"exercicio": exercicio.name,
                               "id": exercicio.video_id, "estado": "MORTO",
                               "titulo": info["motivo"]})
                continue
            estado = "OK" if titulo_confere(exercicio.name, info["titulo"]) \
                else "TITULO NAO BATE"
            linhas.append({"exercicio": exercicio.name, "id": exercicio.video_id,
                           "estado": estado, "titulo": info["titulo"],
                           "canal": info["canal"]})

        if options["json"]:
            self.stdout.write(json.dumps(linhas, ensure_ascii=False, indent=1))
            return

        for l in linhas:
            self.stdout.write("%-32s %-12s %-16s %s"
                              % (l["exercicio"][:32], l["id"], l["estado"],
                                 l["titulo"][:60]))
        ruins = [l for l in linhas if l["estado"] not in ("OK",)]
        self.stdout.write("")
        self.stdout.write("%d exercícios conferidos, %d precisam de olhada"
                          % (len(linhas), len(ruins)))
        for l in ruins:
            self.stdout.write("  %s: %s" % (l["exercicio"], l["estado"]))
