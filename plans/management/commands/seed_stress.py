"""Um ano de histórico fictício, para descobrir o que trava com volume.

O que ele existe para achar não é lentidão de banco — é consulta dentro de
laço e cálculo em Python sobre a série inteira. Com duas semanas de dados
qualquer desenho parece rápido; a diferença aparece no dia trezentos.

Gera para UMA pessoa, e isso basta: as telas são todas do escopo de um usuário.
Popular cem contas mediria o banco, não a tela.

Idempotente: rodar de novo repõe o mesmo período em vez de duplicar.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User, WeightEntry
from plans import services
from plans.models import HydrationLog, MealLog, MealStatus
from supplements.models import Supplement, SupplementLog
from workouts.models import Exercise, ExerciseLog
from workouts.services import create_routine, get_active_routine

DIAS = 365


class Command(BaseCommand):
    help = "Popula um ano de histórico para medir a interface sob volume."

    def add_arguments(self, parser):
        parser.add_argument("email", help="A conta que recebe o histórico.")
        parser.add_argument("--dias", type=int, default=DIAS)
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Apaga o histórico gerado antes de gerar de novo.",
        )

    def handle(self, *args, **options):
        user = User.objects.filter(email=options["email"]).first()
        if user is None:
            raise CommandError(f"Conta não encontrada: {options['email']}")

        dias = options["dias"]
        hoje = timezone.localdate()
        inicio = hoje - timedelta(days=dias)

        # O plano e a rotina são resolvidos ANTES da limpeza, e a ordem é o
        # conserto de um defeito real: `--limpar` apaga as pesagens do período,
        # e criar o plano depois disso falhava com "nenhum registro de peso" —
        # o cálculo precisa de um peso atual e a limpeza tinha levado o único
        # que existia. O plano é um retrato, então sobrevive à limpeza.
        plano = services.get_active_plan(user) or services.create_plan(user)
        rotina = get_active_routine(user) or create_routine(user)

        if options["limpar"]:
            self._limpar(user, inicio)

        slots = list(plano.slots.order_by("order"))
        exercicios = list(
            Exercise.objects.filter(
                pk__in=rotina.sessions.values_list("exercises__exercise", flat=True)
            )
        )
        suplementos = list(Supplement.objects.filter(is_active=True))
        dias_de_treino = set(rotina.sessions.values_list("weekday", flat=True))

        # Semente fixa: rodar duas vezes produz o mesmo histórico, e comparar
        # medições entre execuções passa a fazer sentido.
        sorteio = random.Random(42)

        with transaction.atomic():
            self._peso(user, inicio, dias, sorteio)
            self._refeicoes(user, slots, inicio, dias, sorteio)
            self._agua(user, inicio, dias, sorteio)
            self._treinos(user, exercicios, dias_de_treino, inicio, dias, sorteio)
            self._suplementos(user, suplementos, inicio, dias, sorteio)

        self.stdout.write(
            self.style.SUCCESS(
                f"{dias} dias gerados para {user.email}:\n"
                f"  {WeightEntry.objects.filter(user=user).count()} pesagens\n"
                f"  {MealLog.objects.filter(user=user).count()} refeições\n"
                f"  {HydrationLog.objects.filter(user=user).count()} dias de água\n"
                f"  {ExerciseLog.objects.filter(user=user).count()} séries\n"
                f"  {SupplementLog.objects.filter(user=user).count()} suplementos"
            )
        )

    # ------------------------------------------------------------ limpeza
    def _limpar(self, user, inicio):
        WeightEntry.objects.filter(user=user, date__gte=inicio).delete()
        MealLog.objects.filter(user=user, date__gte=inicio).delete()
        HydrationLog.objects.filter(user=user, date__gte=inicio).delete()
        ExerciseLog.objects.filter(user=user, date__gte=inicio).delete()
        SupplementLog.objects.filter(user=user, date__gte=inicio).delete()

    # -------------------------------------------------------------- peso
    def _peso(self, user, inicio, dias, sorteio):
        """Uma curva com platôs, e não uma reta.

        Reta descendente esconderia justamente o que a tela precisa mostrar: a
        semana em que a média não se mexe. O histórico gerado tem três platôs
        de propósito.
        """
        peso = Decimal("92.0")
        linhas = []
        for i in range(dias):
            dia = inicio + timedelta(days=i)
            # Pesa quatro vezes por semana, como gente pesa.
            if dia.weekday() in (0, 2, 4, 6):
                platô = 120 <= i <= 150 or 220 <= i <= 245
                deriva = Decimal("0") if platô else Decimal("-0.035")
                ruido = Decimal(str(sorteio.uniform(-0.5, 0.5))).quantize(Decimal("0.01"))
                peso = (peso + deriva).quantize(Decimal("0.01"))
                linhas.append(
                    WeightEntry(user=user, date=dia, weight_kg=max(peso + ruido, Decimal("60")))
                )
        WeightEntry.objects.bulk_create(linhas, ignore_conflicts=True)

    # --------------------------------------------------------- refeições
    def _refeicoes(self, user, slots, inicio, dias, sorteio):
        linhas = []
        for i in range(dias):
            dia = inicio + timedelta(days=i)
            for slot in slots:
                sorte = sorteio.random()
                if sorte < 0.08:
                    continue  # nem abriu o app
                if sorte < 0.16:
                    status, opcao = MealStatus.SKIPPED, None
                elif sorte < 0.28:
                    status, opcao = MealStatus.OFF_PLAN, None
                else:
                    status = MealStatus.DONE
                    opcao = sorteio.choice(list(slot.options.all()) or [None])
                linhas.append(
                    MealLog(
                        user=user,
                        slot=slot,
                        date=dia,
                        status=status,
                        chosen_option=opcao if status == MealStatus.DONE else None,
                        slot_name=slot.name,
                        scheduled_time=slot.time,
                        kcal=opcao.kcal if (opcao and status == MealStatus.DONE) else 0,
                        protein_g=opcao.protein_g if (opcao and status == MealStatus.DONE) else 0,
                        carb_g=opcao.carb_g if (opcao and status == MealStatus.DONE) else 0,
                        fat_g=opcao.fat_g if (opcao and status == MealStatus.DONE) else 0,
                    )
                )
        MealLog.objects.bulk_create(linhas, ignore_conflicts=True, batch_size=500)

    # -------------------------------------------------------------- água
    def _agua(self, user, inicio, dias, sorteio):
        linhas = [
            HydrationLog(
                user=user,
                date=inicio + timedelta(days=i),
                ml=sorteio.choice([1500, 2000, 2500, 2800, 3000, 3200, 3500]),
            )
            for i in range(dias)
            if sorteio.random() > 0.12
        ]
        HydrationLog.objects.bulk_create(linhas, ignore_conflicts=True, batch_size=500)

    # ------------------------------------------------------------ treino
    def _treinos(self, user, exercicios, dias_de_treino, inicio, dias, sorteio):
        """Carga subindo devagar, com semanas ruins.

        Progressão linear perfeita não existe e esconderia o caso interessante:
        a sessão em que o volume cai. O gerador tem semanas de deload.
        """
        if not exercicios:
            return
        base = {e.pk: Decimal(str(sorteio.choice([20, 30, 40, 50, 60, 80]))) for e in exercicios}
        linhas = []
        for i in range(dias):
            dia = inicio + timedelta(days=i)
            if dia.weekday() not in dias_de_treino or sorteio.random() < 0.15:
                continue  # dia sem treino previsto, ou faltou
            semana = i // 7
            deload = semana % 8 == 7
            for exercicio in sorteio.sample(exercicios, min(6, len(exercicios))):
                carga = base[exercicio.pk] + Decimal(semana) * Decimal("0.4")
                if deload:
                    carga = (carga * Decimal("0.85")).quantize(Decimal("0.5"))
                for serie in range(1, 4):
                    linhas.append(
                        ExerciseLog(
                            user=user,
                            exercise=exercicio,
                            date=dia,
                            set_number=serie,
                            weight_kg=carga.quantize(Decimal("0.01")),
                            reps=sorteio.choice([8, 10, 12]),
                        )
                    )
        ExerciseLog.objects.bulk_create(linhas, ignore_conflicts=True, batch_size=500)

    # -------------------------------------------------------- suplementos
    def _suplementos(self, user, suplementos, inicio, dias, sorteio):
        linhas = [
            SupplementLog(user=user, supplement=s, date=inicio + timedelta(days=i))
            for i in range(dias)
            for s in suplementos
            if sorteio.random() > 0.35
        ]
        SupplementLog.objects.bulk_create(linhas, ignore_conflicts=True, batch_size=500)
