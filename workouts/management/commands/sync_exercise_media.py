"""Preenche a demonstração dos exercícios a partir da free-exercise-db.

    python manage.py sync_exercise_media
    python manage.py sync_exercise_media --check

O que esta base entrega, para não haver mal-entendido: DUAS FOTOS por
exercício, o começo e o fim do movimento. Não são GIFs animados nem
renderizações 3D — isso não existe em base aberta e sem chave de API. A tela
alterna as duas em loop, que é o que demonstra o movimento; chamar isso de
animação 3D seria vender o que não está sendo entregue.

Em troca do que se perde em suavidade, se ganha o que o vídeo de terceiro
nunca deu: a imagem é de domínio público, não some quando o dono resolve
apagar, não abre com introdução falada, e pesa uns 30 kB em vez de um player
inteiro.

O comando recusa o trabalho se qualquer imagem não responder. Cadastro
apontando para imagem quebrada é pior que cadastro vazio: a tela mostra um
espaço em branco e ninguém descobre por quê.
"""
import json
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from workouts.models import Exercise

#: O CDN do jsDelivr serve o mesmo repositório do GitHub com cache de borda e
#: sem limite de tráfego — raw.githubusercontent responde, mas não é feito para
#: ser origem de imagem de aplicação.
CDN = "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/exercises"

MAPA = Path(settings.BASE_DIR) / "workouts" / "data" / "media_map.json"


def urls_de(identificador: str) -> list:
    """As duas fotos do exercício: início e fim do movimento."""
    return [f"{CDN}/{identificador}/{quadro}.jpg" for quadro in (0, 1)]


def responde(url: str, timeout: int = 20) -> bool:
    pedido = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            return resposta.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


class Command(BaseCommand):
    help = "Aponta cada exercício para as fotos da free-exercise-db."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Só confere as imagens; não grava nada.",
        )

    def handle(self, *args, **options):
        mapa = {
            nome: ident
            for nome, ident in json.loads(MAPA.read_text(encoding="utf-8")).items()
            if not nome.startswith("_")
        }

        exercicios = list(Exercise.objects.filter(is_active=True).order_by("name"))
        sem_mapa = [e.name for e in exercicios if e.name not in mapa]
        quebradas = []
        atualizados = 0

        for exercicio in exercicios:
            identificador = mapa.get(exercicio.name)
            if not identificador:
                continue

            urls = urls_de(identificador)
            ruins = [u for u in urls if not responde(u)]
            if ruins:
                quebradas.append((exercicio.name, ruins))
                continue

            if options["check"]:
                continue

            if exercicio.frames != urls:
                exercicio.frames = urls
                exercicio.save(update_fields=["frames"])
                atualizados += 1

        for nome, urls in quebradas:
            self.stderr.write(self.style.ERROR(f"{nome}: imagem fora do ar"))
            for u in urls:
                self.stderr.write(f"    {u}")

        if sem_mapa:
            self.stderr.write(
                self.style.WARNING(f"{len(sem_mapa)} exercício(s) sem mapa:")
            )
            for nome in sem_mapa:
                self.stderr.write(f"    {nome}")

        if quebradas or sem_mapa:
            self.stderr.write(
                self.style.ERROR(
                    "Nada foi gravado além do que já estava certo — corrija o mapa."
                )
            )
            raise SystemExit(1)

        if options["check"]:
            self.stdout.write(
                self.style.SUCCESS(f"{len(exercicios)} exercícios, todas as fotos no ar.")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"{atualizados} atualizado(s); {len(exercicios)} exercícios com demonstração."
            )
        )
