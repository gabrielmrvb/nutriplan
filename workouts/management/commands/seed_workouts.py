"""Popula o catálogo de exercícios e as divisões de treino.

Idempotente: pode rodar quantas vezes quiser sem duplicar nada.

    python manage.py seed_workouts
    python manage.py seed_workouts --reset-templates
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from workouts.models import (
    Exercise,
    Measure,
    WorkoutTemplate,
    WorkoutTemplateItem,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load(filename):
    with open(DATA_DIR / filename, encoding="utf-8") as fp:
        return json.load(fp)


class Command(BaseCommand):
    help = "Carrega exercícios e as divisões de treino (full, AB, ABC, ABCD)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-templates",
            action="store_true",
            help="Recria os exercícios das divisões a partir do JSON.",
        )


    def _log(self, mensagem):
        """Só fala quando pedem. `verbosity=0` é o padrão dentro dos testes."""
        if self.verbosity:
            self.stdout.write(mensagem)

    @transaction.atomic
    def handle(self, *args, **options):
        self.verbosity = options.get("verbosity", 1)
        exercises = self._seed_exercises()
        self._seed_splits(exercises, reset=options["reset_templates"])
        self._log(self.style.SUCCESS("Treinos carregados."))

    def _seed_exercises(self):
        exercises = {}
        for row in _load("exercises.json"):
            exercise, _ = Exercise.objects.update_or_create(
                name=row["name"],
                defaults={
                    "muscle_group": row["muscle_group"],
                    "is_compound": row.get("compound", False),
                    "cue": row.get("cue", ""),
                    "video_url": row.get("video", ""),
                    "is_active": row.get("active", True),
                },
            )
            exercises[row["name"]] = exercise
        self._log(f"  {len(exercises)} exercícios")
        return exercises

    def _seed_splits(self, exercises, reset=False):
        count = 0
        no_json = set()
        for row in _load("splits.json"):
            key = (row["split"], row["label"])
            no_json.add(key)
            template, created = WorkoutTemplate.objects.update_or_create(
                split=row["split"],
                label=row["label"],
                defaults={
                    "name": row["name"],
                    "focus": row.get("focus", ""),
                    "order": row.get("order", 0),
                    "is_active": True,
                },
            )

            # A lista de exercícios é reconstruída quando difere do JSON, e
            # não só quando o treino é novo.
            #
            # A regra antiga era `created or reset`, e ela mentia em silêncio:
            # mudar o Treino C de "pernas" para "ombro e perna" atualizava o
            # NOME do dia e mantinha os exercícios antigos. A ficha passava a
            # prometer ombro e entregar perna, e nada no deploy acusava —
            # aconteceu aqui, e só apareceu porque fui conferir a tela.
            desejado = [
                (
                    item[0],
                    item[1],
                    item[2],
                    item[3],
                    item[4],
                    item[5] if len(item) > 5 else Measure.REPS,
                )
                for item in row["items"]
            ]
            atual = [
                (
                    it.exercise.name,
                    it.sets,
                    it.rep_min,
                    it.rep_max,
                    it.rest_seconds,
                    it.measure,
                )
                for it in template.items.select_related("exercise").order_by("order")
            ]

            if created or reset or atual != desejado:
                template.items.all().delete()
                for order, (name, sets, rep_min, rep_max, rest, measure) in enumerate(
                    desejado
                ):
                    WorkoutTemplateItem.objects.create(
                        template=template,
                        exercise=exercises[name],
                        sets=sets,
                        rep_min=rep_min,
                        rep_max=rep_max,
                        measure=measure,
                        rest_seconds=rest,
                        order=order,
                    )
            count += 1

        # Divisão que saiu do JSON é desativada, não apagada: fichas antigas
        # apontam para ela e o histórico de quem treinou precisa continuar de pé.
        aposentadas = 0
        for template in WorkoutTemplate.objects.filter(is_active=True):
            if (template.split, template.label) not in no_json:
                template.is_active = False
                template.save(update_fields=["is_active"])
                aposentadas += 1

        self._log(f"  {count} treinos ({aposentadas} aposentados)")
