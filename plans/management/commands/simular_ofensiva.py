# -*- coding: utf-8 -*-
"""A semana da auditoria de 20/09/2026 sob a regra ANTIGA e a de HOJE.

Reproduz, numa pessoa descartável e dentro de uma transação revertida, a
semana simulada da parte A da auditoria (seg 21/09 → dom 27/09): dia 1
treino completo + 2 refeições de 5 + 1 L; dia 2: 3/5 + 0,5 L + treino
parcial; dias 3–7: 4/5 + 1,5 L + treino nos dias previstos (seg/qua/sex).
Meta de água de quem pesa ~86 kg: 3 000 ml. E imprime, dia a dia, a ofensiva
que a Home mostraria sob a regra antiga (treino E dieta E água) e sob a
regra de hoje (`Dia.completo`: treino no dia previsto, mais dieta ou água).

É a prova pedida na decisão de 20/09 ("com o simular_ofensiva provando a
semana auditada antes/depois"), e continua servindo para qualquer mudança
futura na régua: rode antes e depois.

    manage.py simular_ofensiva
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import ActivityLevel, Goal, ONBOARDING_DONE, Profile, Sex, TrainingDay, WeightEntry
from plans import services, streaks
from plans.models import HydrationLog, MealLog, MealStatus
from workouts import services as treino
from workouts.models import Exercise, ExerciseLog

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
DIAS_DE_TREINO = (0, 2, 4)
DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def regra_antiga(dia):
    """A régua até 20/09/2026: os três pilares no mesmo dia."""
    return dia.treino and dia.dieta and dia.agua


def _pessoa():
    user = get_user_model().objects.create_user(email="simulacao-ofensiva@exemplo.invalid", password=None)
    Profile.objects.create(
        user=user, sex=Sex.MALE, birth_date=date(1995, 4, 12), height_cm=178,
        activity_level=ActivityLevel.LIGHT, goal=Goal.BULK, wake_time=time(7, 0),
        sleep_time=time(23, 0), onboarding_step=ONBOARDING_DONE,
    )
    WeightEntry.objects.create(user=user, weight_kg=Decimal("86.0"))
    for weekday in DIAS_DE_TREINO:
        TrainingDay.objects.create(user=user, weekday=weekday, start_time=time(19, 0), duration_min=60)
    return user


class Command(BaseCommand):
    help = "A semana auditada em 20/09/2026 sob a regra antiga e a de hoje."

    def handle(self, *args, **opts):
        if not Exercise.objects.filter(is_active=True).exists():
            call_command("seed_workouts", verbosity=0)
        segunda = date(2026, 9, 21)
        with transaction.atomic():
            user = _pessoa()
            plano = services.create_plan(user)
            treino.create_routine(user)
            slots = list(plano.slots.order_by("time")[:5])
            exercicio = Exercise.objects.filter(is_active=True).first()
            for i, (feitas, ml, treinou) in enumerate(SEMANA):
                dia = segunda + timedelta(days=i)
                for j, slot in enumerate(slots):
                    MealLog.objects.create(user=user, slot=slot, date=dia,
                                           status=MealStatus.DONE if j < feitas else MealStatus.SKIPPED)
                HydrationLog.objects.create(user=user, date=dia, ml=ml)
                if treinou:
                    ExerciseLog.objects.create(user=user, exercise=exercicio, date=dia,
                                               set_number=1, weight_kg=Decimal("40"), reps=10)
            self.stdout.write("semana: " + " · ".join(
                "%s %d/5 %s ml%s" % (DIAS[i], f, ml, " treino" if t else "")
                for i, (f, ml, t) in enumerate(SEMANA)))
            self.stdout.write("treino previsto seg/qua/sex · meta de água %d ml (90 %% = %d ml)" % (META_AGUA, META_AGUA * 0.9))
            antiga, nova = [], []
            seq_antiga = 0
            for i in range(7):
                hoje = segunda + timedelta(days=i)
                ofensiva = streaks.calcular(user, hoje=hoje, meta_agua_ml=META_AGUA)
                nova.append(ofensiva.dias)
                # A regra antiga, dia a dia, sobre os mesmos `Dia`s que a nova lê.
                dia = streaks.avaliar_dia(user, hoje, META_AGUA)
                seq_antiga = seq_antiga + 1 if regra_antiga(dia) else 0
                antiga.append(seq_antiga)
            self.stdout.write("regra antiga (treino E dieta E água):   %s  → dia 7: %d dias" % (" ".join(str(n) for n in antiga), antiga[-1]))
            self.stdout.write("regra de hoje (treino previsto + dieta ou água): %s  → dia 7: %d dias" % (" ".join(str(n) for n in nova), nova[-1]))
            transaction.set_rollback(True)
        self.stdout.write("(pessoa da simulação descartada: transação revertida)")
