"""Cria (ou refaz) o Carlos Silva, o usuário fictício do modo demo.

Idempotente: pode rodar quantas vezes quiser. Roda no build do Render, junto
dos outros seeds, então o demo sobe pronto a cada deploy.

Por que um usuário DE VERDADE no banco, e não um objeto de mentira em memória:
as telas do app leem `request.user.profile`, `user.plans`, `user.training_days`
e uma dúzia de relações. Fingir tudo isso exigiria um dublê para cada modelo, e
o dublê é o que diverge do app real na primeira mudança de schema. Um usuário
comum, montado pelo MESMO motor que monta o seu, é o que garante que o demo
mostra o app que existe.

O que protege os dados reais não é este comando — é o middleware, que recusa
qualquer método que escreva antes de chegar na view.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import (
    ONBOARDING_DONE,
    ActivityLevel,
    Goal,
    MealStyle,
    Profile,
    Sex,
    SplitPreference,
    TrainingDay,
    WeightEntry,
)
from demo.middleware import DEMO_EMAIL
from plans import services as plan_services
from plans.models import HydrationLog, MealLog, MealStatus
from workouts import services as workout_services
from workouts.models import ExerciseLog

IDADE = 28
PESO_KG = Decimal("78.0")
ALTURA_CM = 178

DIAS_DE_TREINO = ((0, time(19, 0)), (2, time(19, 0)), (4, time(19, 0)))
DURACAO_MIN = 60

SEMANAS_DE_PESO = 12
GANHO_POR_SEMANA = Decimal("0.25")


class Command(BaseCommand):
    help = "Cria o usuario ficticio do modo demo (Carlos Silva)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refazer",
            action="store_true",
            help="Apaga o usuario de demonstracao e o cria de novo.",
        )

    def _log(self, mensagem):
        if self.verbosity:
            self.stdout.write(mensagem)

    @transaction.atomic
    def handle(self, *args, **options):
        self.verbosity = options.get("verbosity", 1)
        User = get_user_model()

        if options["refazer"]:
            apagados, _ = User.objects.filter(email=DEMO_EMAIL).delete()
            if apagados:
                self._log("Usuario de demonstracao removido.")

        user, criado = User.objects.get_or_create(
            email=DEMO_EMAIL, defaults={"first_name": "Carlos"}
        )
        if criado:
            # Senha inutilizavel: a conta existe para ser LIDA pelo middleware,
            # e nao para alguem entrar nela pela tela de login.
            user.set_unusable_password()
            user.first_name = "Carlos"
            user.save()

        hoje = timezone.localdate()
        # A data de nascimento acompanha o ano corrente: fixa, o demo
        # envelheceria sozinho e a capa passaria a dizer 29, 30, 31 anos.
        nascimento = date(hoje.year - IDADE, 5, 14)

        Profile.objects.update_or_create(
            user=user,
            defaults={
                "sex": Sex.MALE,
                "birth_date": nascimento,
                "height_cm": ALTURA_CM,
                "activity_level": ActivityLevel.LIGHT,
                "goal": Goal.BULK,
                "split_preference": SplitPreference.DOIS,
                "meal_style": MealStyle.QUICK,
                "wake_time": time(6, 30),
                "sleep_time": time(23, 0),
                "onboarding_step": ONBOARDING_DONE,
                "onboarding_completed_at": timezone.now(),
            },
        )

        # Doze semanas subindo devagar, que e o que hipertrofia parece de
        # verdade. Sem isso o historico abre vazio e a tela mais visual do app
        # nao mostra nada.
        WeightEntry.objects.filter(user=user).delete()
        for semana in range(SEMANAS_DE_PESO, -1, -1):
            WeightEntry.objects.create(
                user=user,
                date=hoje - timedelta(weeks=semana),
                weight_kg=(PESO_KG - GANHO_POR_SEMANA * semana).quantize(
                    Decimal("0.01")
                ),
            )

        TrainingDay.objects.filter(user=user).delete()
        for dia, hora in DIAS_DE_TREINO:
            TrainingDay.objects.create(
                user=user, weekday=dia, start_time=hora, duration_min=DURACAO_MIN
            )

        # Daqui para baixo e o motor de verdade: as mesmas funcoes que montam
        # o plano de qualquer pessoa. E isso que faz o demo mostrar o app.
        plano, _ = plan_services.sync_active_plan(user)
        ficha = workout_services.create_routine(user)

        self._preencher_o_dia(user, plano)
        self._preencher_cargas(user, ficha)

        self._log(
            self.style.SUCCESS(
                "Demo pronto: Carlos Silva, "
                + str(ALTURA_CM)
                + " cm, "
                + str(plano.target_kcal)
                + " kcal, divisao "
                + ficha.get_split_display()
                + "."
            )
        )

    def _preencher_o_dia(self, user, plano):
        """Meia manha ja vivida: as primeiras refeicoes marcadas e agua bebida.

        Um demo com o dia inteiro em branco esconde metade da interface — a
        barra de progresso, o cartao de refeicao concluida, a ofensiva. Um demo
        com o dia inteiro preenchido esconde a outra metade, que e o botao de
        marcar. Metade e metade mostra as duas.
        """
        hoje = timezone.localdate()
        MealLog.objects.filter(user=user, date=hoje).delete()

        horarios = list(plano.slots.order_by("time"))
        for slot in horarios[: max(len(horarios) // 2, 1)]:
            opcao = slot.options.order_by("label").first()
            if opcao is None:
                continue
            MealLog.objects.create(
                user=user,
                slot=slot,
                chosen_option=opcao,
                date=hoje,
                status=MealStatus.DONE,
                marked_at=timezone.now(),
                slot_name=slot.name,
                scheduled_time=slot.time,
                kcal=opcao.kcal,
                protein_g=opcao.protein_g,
                carb_g=opcao.carb_g,
                fat_g=opcao.fat_g,
            )

        HydrationLog.objects.update_or_create(
            user=user, date=hoje, defaults={"ml": 1600}
        )

    def _preencher_cargas(self, user, ficha):
        """Cargas plausiveis na sessao de hoje, e no treino anterior.

        Sem o treino anterior, a linha "ultima carga" fica vazia e a seta de
        progressao — que e o que a tela de treino tem de mais proprio — nao
        aparece em lugar nenhum.
        """
        hoje = timezone.localdate()
        ExerciseLog.objects.filter(user=user).delete()

        sessao = ficha.sessions.order_by("weekday").first()
        if sessao is None:
            return

        for item in sessao.exercises.select_related("exercise").all():
            base = Decimal("60") if item.rep_max <= 10 else Decimal("30")
            if not item.exercise.is_compound:
                base = base / 2
            for atraso, ajuste in ((7, Decimal("-2.5")), (0, Decimal("0"))):
                for serie in range(1, item.sets + 1):
                    ExerciseLog.objects.create(
                        user=user,
                        exercise=item.exercise,
                        date=hoje - timedelta(days=atraso),
                        set_number=serie,
                        weight_kg=(base + ajuste).quantize(Decimal("0.01")),
                        reps=item.rep_min,
                    )
