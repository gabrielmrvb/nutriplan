# -*- coding: utf-8 -*-
"""Contas sintéticas para PROVAR a tela de Progresso nos dois extremos.

A tela de Progresso tem dois estados que importam e que nenhum fixture da
suíte reproduz junto: a conta de TRÊS DIAS — que é o que todo mundo vê na
primeira semana — e a conta de SEIS SEMANAS, que é onde os gráficos têm o
que desenhar. Provar só um dos dois é provar metade: com três dias não dá
para ver se a linha de peso tem forma, e com seis semanas não dá para ver
se o estado vazio mente.

Este comando escreve os dois, de forma DETERMINÍSTICA (`random.Random` com
semente fixa): rodar duas vezes produz a mesma tela, e uma captura de ontem
continua comparável com a de hoje.

    manage.py semear_progresso                 # as duas contas
    manage.py semear_progresso --semanas 6     # só a cheia
    manage.py semear_progresso --dias 3        # só a nova
    manage.py semear_progresso --apagar        # tira as duas do banco

**Não roda em produção**, e a recusa é por AMBIENTE e não por convenção de
nome: `DEBUG` ligado (máquina de quem desenvolve) ou
`NUTRIPLAN_AMBIENTE=staging`. Em produção ele sai com erro sem tocar no
banco — escrever seis semanas de treino falso na conta de alguém é o tipo
de coisa que não tem desfazer.

Os e-mails terminam em `@nutriplan.invalid` de propósito: é a convenção que
`avisos.enviar` usa para NUNCA mandar e-mail (`TLD_QUE_NAO_ENTREGA`), então
uma conta de seed não pode virar mensagem na caixa de ninguém.
"""
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import (
    ActivityLevel,
    DuracaoTreino,
    Equipamento,
    Experiencia,
    Goal,
    MealStyle,
    Musculacao,
    Pilar,
    Profile,
    Sex,
    SplitPreference,
    TrainingDay,
    WeightEntry,
)
from accounts.models import ONBOARDING_DONE
from plans import services
from plans.models import HydrationLog, MealLog, MealStatus
from workouts.models import Corrida, Exercise, ExerciseLog

#: As duas contas. O sufixo diz o que cada uma prova.
EMAIL_CHEIO = "qa-progresso-6semanas@nutriplan.invalid"
EMAIL_NOVO = "qa-progresso-3dias@nutriplan.invalid"

#: Semente fixa: a mesma tela em toda execução (ver o docstring).
SEMENTE = 20260923

#: Dias de treino combinados (segunda, quarta, sexta).
DIAS_DE_TREINO = (0, 2, 4)


class Command(BaseCommand):
    help = "Cria as contas sintéticas que provam a tela de Progresso cheia e vazia."

    def add_arguments(self, parser):
        parser.add_argument("--semanas", type=int, default=None,
                            help="Só a conta cheia, com este número de semanas (padrão 6).")
        parser.add_argument("--dias", type=int, default=None,
                            help="Só a conta nova, com este número de dias (padrão 3).")
        parser.add_argument("--apagar", action="store_true",
                            help="Remove as duas contas e sai.")

    # ------------------------------------------------------------------ guarda
    def _recusar_em_producao(self):
        from django.conf import settings

        from config import ambiente

        if settings.DEBUG or ambiente.e_staging():
            return
        raise CommandError(
            "semear_progresso não roda em produção: ligue DEBUG ou use o staging."
        )

    # ------------------------------------------------------------------ handle
    def handle(self, *args, **opcoes):
        self._recusar_em_producao()
        User = get_user_model()

        if opcoes["apagar"]:
            apagados, _ = User.objects.filter(
                email__in=(EMAIL_CHEIO, EMAIL_NOVO)
            ).delete()
            self.stdout.write("Contas de seed removidas (%d objetos)." % apagados)
            return

        só_cheia = opcoes["semanas"] is not None
        só_nova = opcoes["dias"] is not None
        faz_cheia = só_cheia or not só_nova
        faz_nova = só_nova or not só_cheia

        if faz_cheia:
            self._semear(EMAIL_CHEIO, dias=(opcoes["semanas"] or 6) * 7, nome="Joana")
        if faz_nova:
            self._semear(EMAIL_NOVO, dias=opcoes["dias"] or 3, nome="Rafa")

    # ------------------------------------------------------------------ conta
    @transaction.atomic
    def _semear(self, email, dias, nome):
        """Uma conta com `dias` de histórico, a partir de hoje para trás."""
        User = get_user_model()
        User.objects.filter(email=email).delete()

        hoje = timezone.localdate()
        # A DATA DE CADASTRO é o que a tela usa para nunca desenhar semana que
        # não existiu. Sem mexer nela, a conta nova de "3 dias" teria seis
        # semanas de calendário vazio para mostrar, que é exatamente o defeito
        # que esta missão veio corrigir.
        nascimento_da_conta = hoje - timedelta(days=dias - 1)

        user = User.objects.create_user(email=email, password=None, first_name=nome)
        user.set_unusable_password()
        user.date_joined = timezone.make_aware(
            timezone.datetime.combine(nascimento_da_conta, time(8, 0))
        )
        user.save()

        Profile.objects.update_or_create(
            user=user,
            defaults={
                "sex": Sex.FEMALE,
                "birth_date": date(hoje.year - 31, 3, 9),
                "height_cm": 168,
                "activity_level": ActivityLevel.LIGHT,
                "goal": Goal.CUT,
                "split_preference": SplitPreference.DOIS,
                "duracao_treino": DuracaoTreino.PADRAO,
                "equipamento": Equipamento.COMPLETA,
                "musculacao": Musculacao.SIM,
                "experiencia": Experiencia.INTERMEDIARIO,
                "meal_style": MealStyle.QUICK,
                "wake_time": time(6, 30),
                "sleep_time": time(23, 0),
                "onboarding_step": ONBOARDING_DONE,
                "onboarding_completed_at": user.date_joined,
                "interesse_dieta": True,
                "interesse_treino": True,
                "interesse_corrida": True,
                "interesse_hidratacao": True,
                "prioridade": Pilar.TREINO,
            },
        )
        for weekday in DIAS_DE_TREINO:
            TrainingDay.objects.update_or_create(
                user=user, weekday=weekday, defaults={"duration_min": 60}
            )

        # AS PESAGENS VÊM ANTES DO PLANO, e não é ordem estética: o motor
        # calcula a meta a partir do peso (`build_inputs` levanta
        # `IncompleteProfile` sem nenhuma pesagem), então um plano criado
        # antes delas simplesmente não nasce.
        sorte = random.Random(SEMENTE + dias)
        self._pesagens(user, nascimento_da_conta, hoje, sorte)

        services.sync_active_plan(user)
        plano = services.get_active_plan(user)
        ficha = self._ficha(user)

        self._treinos(user, ficha, nascimento_da_conta, hoje, sorte)
        self._refeicoes(user, plano, nascimento_da_conta, hoje, sorte)
        self._agua(user, nascimento_da_conta, hoje, sorte)
        self._corridas(user, nascimento_da_conta, hoje, sorte)

        self.stdout.write(self.style.SUCCESS(
            "%s: %d dia(s) de histórico, conta nascida em %s."
            % (email, dias, nascimento_da_conta.strftime("%d/%m"))
        ))

    # ------------------------------------------------------------------ partes
    @staticmethod
    def _ficha(user):
        from workouts import services as treino

        try:
            return treino.sync_active_routine(user)[0]
        except Exception:  # noqa: BLE001 — catálogo não semeado; o resto do seed vale
            return None

    def _pesagens(self, user, inicio, hoje, sorte):
        """Uma pesagem por semana, caindo devagar, com ruído de balança.

        Semanal e não diária porque é o que uma pessoa faz — e é o caso que
        a média móvel de 7 dias precisa saber tratar (poucos pontos, espaçados).
        """
        peso = Decimal("74.8")
        dia = inicio
        while dia <= hoje:
            if dia.weekday() == 0 or dia == inicio:
                ruido = Decimal(str(round(sorte.uniform(-0.35, 0.35), 2)))
                WeightEntry.objects.update_or_create(
                    user=user, date=dia,
                    defaults={"weight_kg": (peso + ruido).quantize(Decimal("0.01"))},
                )
                peso -= Decimal("0.4")
            dia += timedelta(days=1)

    def _treinos(self, user, ficha, inicio, hoje, sorte):
        """Séries nos dias combinados, com carga subindo ao longo das semanas.

        Nem todo dia combinado vira treino: 1 em cada 6 é falha, porque um
        heatmap em que todo dia previsto está aceso não prova o terceiro
        estado (dia faltado), que é justamente o que ele existe para mostrar.
        """
        if ficha is None:
            return
        exercicios = list(
            Exercise.objects.filter(is_active=True).order_by("pk")[:6]
        )
        if not exercicios:
            return
        dia = inicio
        semana = 0
        while dia <= hoje:
            if dia.weekday() == 0:
                semana += 1
            if dia.weekday() in DIAS_DE_TREINO and sorte.random() > 1 / 6:
                for n, exercicio in enumerate(exercicios[: 3 + (dia.weekday() % 2)]):
                    base = 20 + n * 7.5 + semana * 2.5
                    for serie in range(1, 4):
                        ExerciseLog.objects.update_or_create(
                            user=user, exercise=exercicio, date=dia, set_number=serie,
                            defaults={
                                "weight_kg": Decimal(str(round(base, 1))),
                                "reps": sorte.choice((8, 9, 10, 10, 12)),
                            },
                        )
            dia += timedelta(days=1)

    def _refeicoes(self, user, plano, inicio, hoje, sorte):
        """Refeições marcadas com aderência variável, do plano ativo.

        A aderência SOBE ao longo das semanas (0,55 → 0,95): uma série que
        não vai a lugar nenhum não prova que a tela consegue mostrar
        tendência, que é o ponto do redesenho.
        """
        if plano is None:
            return
        slots = list(plano.slots.all().order_by("order", "time"))
        if not slots:
            return
        total_dias = max((hoje - inicio).days, 1)
        dia = inicio
        while dia <= hoje:
            avanco = (dia - inicio).days / total_dias
            chance = 0.55 + 0.40 * avanco
            for slot in slots:
                if sorte.random() > chance:
                    continue
                opcao = slot.options.order_by("rank").first()
                receita = getattr(getattr(opcao, "template", None), "name", "") or slot.name
                MealLog.objects.update_or_create(
                    user=user, date=dia, slot=slot,
                    defaults={
                        "status": MealStatus.DONE,
                        "chosen_option": opcao,
                        "slot_name": slot.name,
                        "scheduled_time": slot.time,
                        "recipe_name": receita,
                        "kcal": int(getattr(opcao, "kcal", 0) or slot.target_kcal or 0),
                        "protein_g": int(getattr(opcao, "protein_g", 0) or 0),
                        "carb_g": int(getattr(opcao, "carb_g", 0) or 0),
                        "fat_g": int(getattr(opcao, "fat_g", 0) or 0),
                        "marked_at": timezone.now(),
                    },
                )
            dia += timedelta(days=1)

    def _agua(self, user, inicio, hoje, sorte):
        """Cinco dias em sete com água anotada, volume perto da meta."""
        dia = inicio
        while dia <= hoje:
            if sorte.random() < 5 / 7:
                HydrationLog.objects.update_or_create(
                    user=user, date=dia,
                    defaults={"ml": sorte.choice((1500, 1750, 2000, 2250, 2500, 2750))},
                )
            dia += timedelta(days=1)

    def _corridas(self, user, inicio, hoje, sorte):
        """Uma ou duas corridas por semana, distância subindo devagar."""
        dia = inicio
        semana = 0
        while dia <= hoje:
            if dia.weekday() == 0:
                semana += 1
            if dia.weekday() in (2, 6) and sorte.random() < 0.7:
                km = 3.0 + semana * 0.35 + sorte.uniform(-0.4, 0.4)
                metros = int(km * 1000)
                # Ritmo melhorando: 6'40"/km na primeira semana, ~6'05" na sexta.
                seg_por_km = 400 - semana * 7 + sorte.randint(-12, 12)
                comeco = timezone.make_aware(
                    timezone.datetime.combine(dia, time(7, 10))
                )
                duracao = int(km * seg_por_km)
                # `op_id` ENTRA: a constraint `uma_corrida_por_operacao` é
                # `(user, op_id)`, e duas corridas com o identificador em
                # branco colidem na segunda semana.
                Corrida.objects.update_or_create(
                    user=user, comecou_em=comeco,
                    defaults={
                        "op_id": "seed-%s" % dia.isoformat(),
                        "terminou_em": comeco + timedelta(seconds=duracao),
                        "distancia_m": metros,
                        "duracao_s": duracao,
                        "origem": Corrida.Origem.MANUAL,
                    },
                )
            dia += timedelta(days=1)
