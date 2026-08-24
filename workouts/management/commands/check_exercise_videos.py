"""Confere se os vídeos de execução ainda estão no ar e permitem embed.

    python manage.py check_exercise_videos

Vídeo de terceiro apodrece: o dono apaga, torna privado ou desliga a permissão
de embutir — e a ficha passa a abrir uma tela preta no meio da série de alguém.
Este comando é a forma de descobrir isso antes do usuário, e é o que torna
honesto ter URL fixa no seed.

Usa o oEmbed do próprio YouTube, que não precisa de chave de API: 200 significa
"existe e pode ser embutido", 401 é embed bloqueado pelo dono, 404 é vídeo fora
do ar. Devolve status 1 quando algo está errado, então dá para pendurar num
agendador e ser avisado.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand

from workouts.models import Exercise

OEMBED = "https://www.youtube.com/oembed?format=json&url="

MOTIVO = {
    401: "o dono bloqueou a exibição fora do YouTube",
    403: "acesso restrito",
    404: "vídeo fora do ar",
}


class Command(BaseCommand):
    help = "Verifica os vídeos de execução dos exercícios ativos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout", type=int, default=20, help="Segundos por requisição."
        )

    def handle(self, *args, **options):
        exercises = Exercise.objects.filter(is_active=True).order_by("name")
        sem_video = [e.name for e in exercises if not e.video_url]
        problemas = []

        for exercise in exercises.exclude(video_url=""):
            erro = self._check(exercise, options["timeout"])
            if erro:
                problemas.append((exercise.name, erro))
                self.stdout.write(self.style.ERROR(f"  {exercise.name}: {erro}"))

        if sem_video:
            self.stdout.write(
                self.style.WARNING(f"  sem vídeo cadastrado: {', '.join(sem_video)}")
            )

        total = exercises.count()
        if problemas:
            self.stdout.write(
                self.style.ERROR(
                    f"{len(problemas)} de {total} vídeos com problema. "
                    f"Troque a URL em workouts/data/exercises.json e rode o seed."
                )
            )
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(f"{total} vídeos no ar e embutíveis."))

    def _check(self, exercise, timeout):
        """Devolve o motivo do problema, ou "" quando está tudo certo."""
        if not exercise.video_embed_url:
            return "a URL cadastrada não vira um embed do YouTube"
        alvo = OEMBED + urllib.parse.quote(exercise.video_url, safe="")
        try:
            with urllib.request.urlopen(alvo, timeout=timeout) as response:
                json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return MOTIVO.get(exc.code, f"HTTP {exc.code}")
        except Exception as exc:  # rede fora, DNS, timeout
            return f"não deu para verificar ({exc})"
        return ""
