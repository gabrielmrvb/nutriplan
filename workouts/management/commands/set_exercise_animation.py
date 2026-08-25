"""Aponta os exercícios para animações de uma fonte externa.

    python manage.py set_exercise_animation animacoes.json
    python manage.py set_exercise_animation animacoes.json --check
    python manage.py set_exercise_animation --clear

O arquivo é um JSON simples, nome do exercício para endereço da mídia:

    {
      "Supino reto com barra": "https://cdn.exemplo.com/supino.mp4",
      "Agachamento livre": "https://cdn.exemplo.com/agachamento.gif"
    }

Por que um importador genérico em vez de um cliente da API do MuscleWiki: a
fonte da animação é uma decisão de produto que já mudou três vezes neste
projeto — YouTube, foto de domínio público, e agora animação premium. Escrever
um cliente HTTP para cada fonte significa reescrever código a cada mudança;
lendo um arquivo, trocar de fonte é trocar o arquivo.

Vale para qualquer origem: exportação da API do MuscleWiki, do ExerciseDB, um
pacote de animações licenciado, ou arquivos que você mesmo hospede.

ATENÇÃO ao termo de uso da fonte. O do MuscleWiki, por exemplo, proíbe baixar
e guardar os vídeos: lá o endereço tem que ser pedido à API na hora, não
gravado no banco. Guardar URL de CDN é legítimo quando a licença permite —
confira antes de importar.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from workouts.models import Exercise

#: O que a tela sabe tocar. Formato fora desta lista entra como imagem e
#: provavelmente aparece parado — melhor recusar do que exibir errado.
TIPOS = {
    ".mp4": "video",
    ".webm": "video",
    ".mov": "video",
    ".gif": "imagem",
    ".webp": "imagem",
    ".apng": "imagem",
}


def tipo_de(url: str) -> str:
    endereco = url.lower()
    # Short do YouTube é o formato em que as animações anatômicas existem
    # hoje. Não é arquivo de mídia, é player — a tela monta um `<iframe>`.
    if "youtube.com" in endereco or "youtu.be" in endereco:
        return "youtube"

    caminho = endereco.split("?")[0]
    for extensao, tipo in TIPOS.items():
        if caminho.endswith(extensao):
            return tipo
    return ""


OEMBED = "https://www.youtube.com/oembed?format=json&url="


def responde(url: str, timeout: int = 25) -> bool:
    """A URL está de pé e pode ser exibida?

    Para o YouTube a pergunta é outra e a resposta vem de outro lugar: um
    `HEAD` na página do vídeo devolve 200 mesmo quando o dono bloqueou a
    exibição fora do site. Quem sabe disso é o oEmbed — 200 significa "existe
    e pode ser embutido", 401 é embed bloqueado, 404 é vídeo fora do ar.
    """
    if tipo_de(url) == "youtube":
        consulta = OEMBED + urllib.parse.quote(url, safe="")
        try:
            with urllib.request.urlopen(consulta, timeout=timeout) as resposta:
                return resposta.status == 200
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            return False

    pedido = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            return resposta.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


class Command(BaseCommand):
    help = "Importa URLs de animação para o catálogo de exercícios."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", nargs="?", help="JSON com nome -> URL.")
        parser.add_argument(
            "--check",
            action="store_true",
            help="Confere as URLs sem gravar nada.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Apaga as animações e volta para a demonstração em fotos.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            quantos = Exercise.objects.exclude(animation_url="").update(animation_url="")
            self.stdout.write(
                self.style.SUCCESS(f"{quantos} animação(ões) removida(s).")
            )
            return

        if not options["arquivo"]:
            raise CommandError("Informe o arquivo JSON, ou use --clear.")

        caminho = Path(options["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Não encontrei {caminho}.")

        mapa = json.loads(caminho.read_text(encoding="utf-8"))
        mapa = {k: v for k, v in mapa.items() if not k.startswith("_")}

        do_catalogo = {e.name: e for e in Exercise.objects.filter(is_active=True)}

        desconhecidos = [nome for nome in mapa if nome not in do_catalogo]
        sem_animacao = [nome for nome in do_catalogo if nome not in mapa]
        formato_ruim = [
            (nome, url) for nome, url in mapa.items() if not tipo_de(url)
        ]

        # A conferência de rede é a parte lenta; só roda se o resto passou.
        fora_do_ar = []
        if not desconhecidos and not formato_ruim:
            for nome, url in mapa.items():
                if not responde(url):
                    fora_do_ar.append((nome, url))

        problemas = False

        for nome in desconhecidos:
            self.stderr.write(self.style.ERROR(f"não existe no catálogo: {nome}"))
            problemas = True

        for nome, url in formato_ruim:
            self.stderr.write(
                self.style.ERROR(f"formato que a tela não toca: {nome} -> {url}")
            )
            problemas = True

        for nome, url in fora_do_ar:
            self.stderr.write(self.style.ERROR(f"não respondeu: {nome} -> {url}"))
            problemas = True

        if sem_animacao:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(sem_animacao)} exercício(s) seguem com a demonstração em fotos:"
                )
            )
            for nome in sem_animacao:
                self.stdout.write(f"    {nome}")

        if problemas:
            # Nada é gravado: catálogo meio importado é pior que não importado,
            # porque metade da tela muda de aparência e ninguém sabe por quê.
            raise CommandError("Nada foi gravado. Corrija o arquivo e rode de novo.")

        if options["check"]:
            self.stdout.write(
                self.style.SUCCESS(f"{len(mapa)} animação(ões) conferida(s), todas no ar.")
            )
            return

        gravados = 0
        for nome, url in mapa.items():
            exercicio = do_catalogo[nome]
            if exercicio.animation_url != url:
                exercicio.animation_url = url
                exercicio.save(update_fields=["animation_url"])
                gravados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{gravados} atualizado(s); {len(mapa)} exercício(s) com animação."
            )
        )
