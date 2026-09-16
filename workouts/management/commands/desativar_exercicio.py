"""Veta um exercício do catálogo — no banco E no `exercises.json`.

    python manage.py desativar_exercicio "Agachamento goblet"

Os dois lugares, porque o seed roda em todo deploy e RESSUSCITARIA o
exercício se só o banco mudasse (`CLAUDE.md`, "o seed também precisa
saber"). Aposentar nunca apaga: `ExerciseLog.exercise` é `CASCADE`, e a
linha fica para o histórico de quem já o treinou. Feito para o veto do
mosaico de ativação de 17/09/2026: uma linha, um exercício, reversível.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from workouts.models import Exercise

CATALOGO = Path(__file__).resolve().parents[2] / "data" / "exercises.json"


class Command(BaseCommand):
    help = "Desativa um exercício no banco e marca active: false no exercises.json."

    def add_arguments(self, parser):
        parser.add_argument("nome", help="O nome exato do exercício, como está no catálogo.")
        parser.add_argument(
            "--reativar", action="store_true",
            help="Desfaz o veto: active: true nos dois lugares.",
        )

    def handle(self, *args, **options):
        nome = options["nome"]
        ativo = bool(options["reativar"])
        catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
        linha = next((x for x in catalogo if x["name"] == nome), None)
        if linha is None:
            raise CommandError("'%s' não está no exercises.json — o nome é exato, com acentos." % nome)
        linha["active"] = ativo
        CATALOGO.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        alterados = Exercise.objects.filter(name=nome).update(is_active=ativo)
        if not alterados:
            self.stdout.write(self.style.WARNING("no banco: '%s' não existe ainda (o seed vai criá-lo %s)." % (
                nome, "ativo" if ativo else "inativo")))
        self.stdout.write(self.style.SUCCESS(
            "%s: %s (json + banco). Commit e deploy para valer em produção." % (
                "reativado" if ativo else "desativado", nome)
        ))
