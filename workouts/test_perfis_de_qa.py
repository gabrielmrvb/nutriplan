# -*- coding: utf-8 -*-
"""Cinco perfis bem diferentes, e o que a prescrição tem de garantir a todos.

A regra da missão (§17): não validar treino com uma conta só. Os perfis
nascem e morrem dentro da suíte — nenhum vira fixture, nenhum toca em conta
real. O que cada um prova é o CONTRATO, e não um número mágico:

  - a divisão é a que `split_for` promete para a frequência e a preferência;
  - toda sessão tem pelo menos dois exercícios (a régua de
    `test_reparticao_semanal`, aplicada a perfis que ela não cobria);
  - no tempo padrão, nenhum composto principal desce de três séries — foi a
    queixa que abriu §16 ("supino com duas séries") e é a camada 2 do corte;
  - o teto da faixa é obedecido quando existe, e `livre` não corta nada;
  - nenhum exercício aparece duas vezes na mesma sessão;
  - de três dias para cima, no tempo padrão ou maior, o contrato de variedade
    4 peitos / 4 costas / 3 tríceps / 3 bíceps se cumpre;
  - de 45 minutos para cima, nenhum grupo do catálogo fica sem sessão na
    semana (a promessa de `realocar_complementares_orfaos`).

Onde um perfil reprovar, o achado é de §16/§18 e vira correção no MOTOR só
com medição escrita — nunca ajuste da expectativa.
"""
from collections import Counter
from datetime import date, time
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from accounts.forms import MINUTOS_POR_DURACAO
from accounts.models import (
    ONBOARDING_DONE,
    ActivityLevel,
    DuracaoTreino,
    Experiencia,
    Goal,
    Profile,
    Sex,
    SplitPreference,
    TrainingDay,
    User,
    WeightEntry,
)
from workouts import services
from workouts.models import MuscleGroup

# (rótulo, sexo, nascimento, peso, objetivo, atividade, dias, experiência, duração, preferência)
PERFIS = [
    ("a-iniciante-3d-rapido", Sex.FEMALE, date(2002, 3, 9), "58.0", Goal.CUT,
     ActivityLevel.SEDENTARY, (1, 3, 5), Experiencia.INICIANTE,
     DuracaoTreino.RAPIDO, SplitPreference.DOIS),
    ("b-referencia-5d-padrao", Sex.MALE, date(1999, 7, 8), "102.0", Goal.CUT,
     ActivityLevel.LIGHT, (0, 1, 2, 3, 4), Experiencia.INTERMEDIARIO,
     DuracaoTreino.PADRAO, SplitPreference.DOIS),
    ("c-avancado-4d-completo", Sex.MALE, date(1981, 11, 2), "88.0", Goal.MAINTAIN,
     ActivityLevel.ACTIVE, (0, 1, 3, 4), Experiencia.AVANCADO,
     DuracaoTreino.COMPLETO, SplitPreference.UM),
    ("d-ganho-6d-padrao", Sex.FEMALE, date(1991, 5, 20), "70.0", Goal.BULK,
     ActivityLevel.LIGHT, (0, 1, 2, 3, 4, 5), Experiencia.INTERMEDIARIO,
     DuracaoTreino.PADRAO, SplitPreference.TRES),
    ("e-jovem-2d-livre", Sex.MALE, date(2007, 1, 15), "65.0", Goal.BULK,
     ActivityLevel.LIGHT, (2, 5), Experiencia.INICIANTE,
     DuracaoTreino.LIVRE, SplitPreference.DOIS),
]

GRUPOS_DO_CONTRATO = {  # 4/4/3/3, de três dias para cima
    MuscleGroup.CHEST: 4, MuscleGroup.BACK: 4,
    MuscleGroup.TRICEPS: 3, MuscleGroup.BICEPS: 3,
}


def nascer(rotulo, sexo, nascimento, peso, objetivo, atividade, dias, exp, dur, pref):
    user = User.objects.create_user(
        email="qa-%s@exemplo.com" % rotulo, password="senha-bem-forte-123"
    )
    Profile.objects.create(
        user=user, sex=sexo, birth_date=nascimento, height_cm=170,
        activity_level=atividade, goal=objetivo, wake_time=time(7, 0),
        sleep_time=time(23, 0), onboarding_step=ONBOARDING_DONE,
        split_preference=pref, split_preference_confirmada=True,
        experiencia=exp, duracao_treino=dur,
    )
    WeightEntry.objects.create(user=user, weight_kg=Decimal(peso))
    for d in dias:
        # SEM HORÁRIO, de propósito: é o estado de quem se cadastra hoje.
        TrainingDay.objects.create(
            user=user, weekday=d, start_time=None,
            duration_min=MINUTOS_POR_DURACAO[dur],
        )
    return user


class CincoPerfisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _sessoes(self, user):
        plano = services.create_routine(user)
        return list(plano.sessions.order_by("weekday").prefetch_related(
            "exercises__exercise"
        ))

    def test_cada_perfil_recebe_uma_semana_coerente(self):
        for perfil in PERFIS:
            rotulo, dias, exp, dur, pref = perfil[0], perfil[6], perfil[7], perfil[8], perfil[9]
            with self.subTest(perfil=rotulo):
                user = nascer(*perfil)
                sessoes = self._sessoes(user)

                # a divisão prometida
                self.assertEqual(
                    user.training_plans.get(is_active=True).split,
                    services.split_for(len(dias), pref),
                )
                self.assertEqual(len(sessoes), len(dias))

                teto = services.teto_de_minutos(user)
                por_grupo_na_semana = {}
                for s in sessoes:
                  # POR OPÇÃO (15/09/2026): a sessão guarda até duas versões
                  # da letra, e cada uma é um treino — tamanho, repetição e
                  # tempo são medidos nela. A variedade da semana é a UNIÃO.
                  for opcao in s.opcoes:
                    itens = s.da_opcao(opcao)
                    nomes = [i.exercise.name for i in itens]
                    onde = "%s opção %d" % (s.label, opcao)

                    self.assertGreaterEqual(
                        len(itens), 2, "%s: sessão %s com %d exercício" % (rotulo, onde, len(itens))
                    )
                    self.assertEqual(len(nomes), len(set(nomes)),
                                     "%s: exercício repetido em %s" % (rotulo, onde))

                    if teto is not None:
                        self.assertLessEqual(
                            s.minutos_da_opcao(opcao), teto,
                            "%s: %s estima %d min com teto de %d" % (
                                rotulo, onde, s.minutos_da_opcao(opcao), teto),
                        )

                    if dur != DuracaoTreino.RAPIDO:
                        # No padrão ou acima, o composto principal não desce de
                        # três séries — camada 2 do corte, e a queixa de §16.
                        for i in itens:
                            if i.exercise.is_compound and i.exercise.muscle_group in (
                                s.main_groups or ()
                            ):
                                self.assertGreaterEqual(
                                    i.sets, 3,
                                    "%s: %s com %d série(s) em %s" % (
                                        rotulo, i.exercise.name, i.sets, onde),
                                )

                    for i in itens:
                        por_grupo_na_semana.setdefault(
                            i.exercise.muscle_group, set()
                        ).add(i.exercise.name)

                # o contrato de variedade, de três dias para cima e do padrão para cima
                if len(dias) >= 3 and dur != DuracaoTreino.RAPIDO:
                    for grupo, minimo in GRUPOS_DO_CONTRATO.items():
                        self.assertGreaterEqual(
                            len(por_grupo_na_semana.get(grupo, ())), minimo,
                            "%s: %s tem %d distintos, contrato pede %d" % (
                                rotulo, grupo, len(por_grupo_na_semana.get(grupo, ())), minimo),
                        )

                # zero grupo órfão de 45 minutos para cima
                if teto is None or teto >= 45:
                    faltando = [g for g, _ in MuscleGroup.choices if g not in por_grupo_na_semana]
                    self.assertEqual(
                        faltando, [], "%s: grupos sem sessão na semana: %s" % (rotulo, faltando)
                    )

    def test_o_horario_nao_e_exigido_para_montar_a_ficha(self):
        """`start_time=None` em todos os dias, e a ficha nasce mesmo assim (§13)."""
        user = nascer(*PERFIS[1])
        self.assertEqual(
            set(TrainingDay.objects.filter(user=user).values_list("start_time", flat=True)),
            {None},
        )
        self.assertTrue(self._sessoes(user))

    def test_a_faixa_move_o_tamanho_da_semana_na_direcao_certa(self):
        """Rápido cabe em menos minutos que padrão, que cabe em menos que
        completo — para a MESMA pessoa. É a coerência das faixas (§14)."""
        base = list(PERFIS[1])
        minutos = {}
        for dur in (DuracaoTreino.RAPIDO, DuracaoTreino.PADRAO, DuracaoTreino.COMPLETO):
            p = list(base)
            p[0] = "faixa-%s" % dur
            p[8] = dur
            user = nascer(*p)
            # A soma da opção de referência (a 1) de cada sessão: as opções
            # são equivalentes por construção, e somar as duas contaria dois
            # treinos por dia.
            minutos[dur] = sum(s.estimated_minutes for s in self._sessoes(user))
        self.assertLessEqual(minutos[DuracaoTreino.RAPIDO], minutos[DuracaoTreino.PADRAO])
        self.assertLessEqual(minutos[DuracaoTreino.PADRAO], minutos[DuracaoTreino.COMPLETO])
