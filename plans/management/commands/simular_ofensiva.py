# -*- coding: utf-8 -*-
"""PROTÓTIPO (auditoria 20/09/2026, Fase 3): a MESMA semana, quatro regras.

Reproduz a semana simulada da parte A da auditoria (seg 21/09 → dom 27/09):
dia 1 treino completo + 2 refeições de 5 + 1 L; dia 2: 3/5 + 0,5 L + treino
parcial; dias 3–7: 4/5 + 1,5 L + treino nos dias previstos (seg/qua/sex).
Meta de água de quem pesa ~86 kg: 3 000 ml. E imprime a ofensiva que a Home
mostraria no dia 7 sob cada regra do dia. Cria uma pessoa descartável e a
apaga no fim. Só para o banco local.

    manage.py simular_ofensiva
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from plans import streaks
from plans.models import HydrationLog, MealLog, MealStatus, NutritionPlan
from workouts import services as treino
from workouts.models import Exercise, ExerciseLog
from workouts.tests import create_user

SEMANA = [
    # (refeições feitas de 5, ml de água, treinou?)
    (2, 1000, True),
    (3, 500, True),
    (4, 1500, True),
    (4, 1500, False),
    (4, 1500, True),
    (4, 1500, False),
    (4, 1500, False),
]
META_AGUA = 3000


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args, **opts):
        from django.core.management import call_command
        if not Exercise.objects.filter(is_active=True).exists():
            call_command("seed_workouts", verbosity=0)
        segunda = date(2026, 9, 21)
        with transaction.atomic():
            user = create_user(email="simulacao-ofensiva@exemplo.invalid", weekdays=(0, 2, 4))
            plano = NutritionPlan.objects.filter(user=user, is_active=True).first() or NutritionPlan.objects.filter(user=user).first()
            if plano is None:
                from plans import services
                plano = services.create_plan(user)
            treino.create_routine(user)
            slots = list(plano.slots.order_by("time")[:5])
            exercicio = Exercise.objects.filter(is_active=True).first()
            for i, (feitas, ml, treinou) in enumerate(SEMANA):
                dia = segunda + timedelta(days=i)
                for j, slot in enumerate(slots):
                    MealLog.objects.create(user=user, slot=slot, date=dia, status=MealStatus.DONE if j < feitas else MealStatus.SKIPPED)
                HydrationLog.objects.create(user=user, date=dia, ml=ml)
                if treinou:
                    ExerciseLog.objects.create(user=user, exercise=exercicio, date=dia, set_number=1, weight_kg=Decimal("40"), reps=10)
            hoje = segunda + timedelta(days=6)
            self.stdout.write("semana: " + ", ".join("%s %d/5 %dml %s" % ((segunda + timedelta(days=i)).strftime("%a"), f, ml, "treino" if t else "-") for i, (f, ml, t) in enumerate(SEMANA)))
            self.stdout.write("dias de treino previstos: seg/qua/sex · meta de água %d ml (90 %% = %d; 60 %% = %d)" % (META_AGUA, META_AGUA * 0.9, META_AGUA * 0.6))
            for regra in ("tres", "agua-60", "dois-de-tres", "agua-nao-quebra"):
                streaks.REGRA_DO_DIA = regra
                o = streaks.calcular(user, hoje=hoje, meta_agua_ml=META_AGUA)
                dias = []
                for i in range(7):
                    d = segunda + timedelta(days=i)
                    dia = streaks.calcular(user, hoje=d, meta_agua_ml=META_AGUA)
                    dias.append("%d" % dia.dias)
                self.stdout.write("%-16s ofensiva no dia 7: %2d dias · por dia: %s · falta hoje: %s" % (regra, o.dias, " ".join(dias), ", ".join(o.falta_hoje) or "nada"))
            transaction.set_rollback(True)
        self.stdout.write("(pessoa da simulação descartada: transação revertida)")
