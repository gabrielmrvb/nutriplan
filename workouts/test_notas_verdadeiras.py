# -*- coding: utf-8 -*-
"""As notas da ficha só afirmam o que é verdade — inclusive sobre fisiologia.

Três frases foram apanhadas pela pesquisa de 13/09/2026:

- a nota do ABC dizia que peito e costas "são antagonistas, e treinar um
  cansa o outro pela metade" — a meta-análise de supersets
  agonista-antagonista (Zhang 2025) mede o OPOSTO: a alternância mantém ou
  aumenta as repetições. E o próprio `ab A` treina supino e remada juntos;
- a nota do ABCDE descrevia "o ciclo de quatro mais um dia para o que sobra",
  que é o modelo ABCD+1 que o catálogo não tem mais — o ABCDE de hoje é
  peito, costas, pernas, ombros e braços, um por dia — e o rótulo do `Split`
  chamava o quinto dia de "pontos fracos";
- o iniciante (teto 12) com quatro dias ou mais recebe a segunda passagem da
  letra com um exercício só, e nenhuma frase dizia que a EXPERIÊNCIA é a
  causa. "Corte de volume continua sem frase" vale para o aparo comum; aqui
  a pessoa vê uma sessão de treze minutos e precisa saber por quê.
"""
from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from accounts.models import ActivityLevel, Experiencia, Goal, Sex, SplitPreference, DuracaoTreino
from workouts import services
from workouts.models import Split
from workouts.test_perfis_de_qa import nascer


class AsNotasDeDivisaoTests(TestCase):
    def test_o_abc_nao_afirma_que_antagonista_cansa_o_outro(self):
        nota = services.SPLIT_NOTE[Split.ABC]
        self.assertNotIn("metade", nota)
        self.assertNotIn("cansa", nota)
        self.assertIn("empurrar", nota)

    def test_o_abcde_descreve_o_modelo_que_existe(self):
        nota = services.SPLIT_NOTE[Split.ABCDE]
        self.assertNotIn("quatro", nota)
        self.assertNotIn("sobra", nota)
        for grupo in ("peito", "costas", "pernas", "ombros", "braços"):
            self.assertIn(grupo, nota)

    def test_o_rotulo_do_abcde_nao_chama_o_quinto_dia_de_pontos_fracos(self):
        self.assertNotIn("pontos fracos", Split.ABCDE.label)


class ANotaDoInicianteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _plano(self, exp, dias):
        user = nascer(
            "nota-%s-%d" % (exp, len(dias)), Sex.MALE, date(1999, 7, 8), "80",
            Goal.BULK, ActivityLevel.LIGHT, dias, exp, DuracaoTreino.PADRAO,
            SplitPreference.DOIS,
        )
        return services.create_routine(user)

    def test_iniciante_com_cinco_dias_le_a_causa_na_nota(self):
        plano = self._plano(Experiencia.INICIANTE, (0, 1, 2, 3, 4))
        self.assertIn("quem está começando", plano.notes)
        self.assertIn("três dias", plano.notes)

    def test_iniciante_com_tres_dias_nao_le_a_frase(self):
        """Com três dias não há passagem esvaziada: a frase seria ruído."""
        plano = self._plano(Experiencia.INICIANTE, (0, 2, 4))
        self.assertNotIn("quem está começando", plano.notes)

    def test_intermediario_com_cinco_dias_nao_le_a_frase(self):
        plano = self._plano(Experiencia.INTERMEDIARIO, (0, 1, 2, 3, 4))
        self.assertNotIn("quem está começando", plano.notes)
