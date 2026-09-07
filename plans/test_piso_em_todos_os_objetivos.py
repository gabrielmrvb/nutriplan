# -*- coding: utf-8 -*-
"""O rótulo do piso vale para TODOS os objetivos, não só para Emagrecer.

A primeira correção deste defeito consertava só `Goal.CUT`, com o objetivo
escrito à mão na condição. Recomposição e Manutenção continuavam recebendo
"Superávit diário recomendado" na mesma situação — dois de três ainda com o
defeito que a correção existia para fechar. Achado em revisão adversarial.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from accounts.models import Goal, Sex
from plans import calculations as c


class OPisoEReconhecidoEmQualquerObjetivoTests(SimpleTestCase):
    """A mulher de 45 kg, 150 cm e 60 anos, sedentária: gasto 1.158."""

    def setUp(self):
        self.bmr = c.bmr_mifflin_st_jeor(
            sex=Sex.FEMALE, weight_kg=Decimal("45"), height_cm=150, age_years=60
        )
        self.gasto = c.tdee(self.bmr, "sedentary", 0)

    def _meta(self, objetivo):
        alvo, _ = c.target_kcal(self.gasto, objetivo, self.bmr, Sex.FEMALE, Decimal("45"))
        return alvo

    def test_o_piso_e_reconhecido_no_corte(self):
        alvo = self._meta(Goal.CUT)
        self.assertTrue(c.piso_elevou(int(self.gasto), Goal.CUT, alvo))

    def test_o_piso_e_reconhecido_na_recomposicao(self):
        """Era aqui que a versão anterior falhava: meta 1.200 contra gasto
        1.158, delta +42, e a tela dizia "Superávit diário recomendado" para
        quem escolheu perder gordura."""
        alvo = self._meta(Goal.RECOMP)
        self.assertTrue(c.piso_elevou(int(self.gasto), Goal.RECOMP, alvo))

    def test_o_piso_e_reconhecido_na_manutencao(self):
        alvo = self._meta(Goal.MAINTAIN)
        self.assertTrue(c.piso_elevou(int(self.gasto), Goal.MAINTAIN, alvo))

    def test_ganhar_massa_com_delta_positivo_NAO_e_piso(self):
        """CONTROLE NEGATIVO: em BULK o superávit é o pedido, não uma trava.
        Sem este teste, um `piso_elevou` que devolvesse sempre True passaria
        nos três acima."""
        alvo = self._meta(Goal.BULK)
        self.assertFalse(c.piso_elevou(int(self.gasto), Goal.BULK, alvo))

    def test_nenhum_objetivo_de_pessoa_grande_dispara_o_piso(self):
        """CONTROLE POSITIVO: homem de 90 kg, gasto 2.970. Nenhuma meta é
        elevada, e rotular qualquer uma como piso seria o defeito inverso."""
        bmr = c.bmr_mifflin_st_jeor(
            sex=Sex.MALE, weight_kg=Decimal("90"), height_cm=180, age_years=30
        )
        gasto = c.tdee(bmr, "active", 4)
        for objetivo in Goal.values:
            alvo, _ = c.target_kcal(gasto, objetivo, bmr, Sex.MALE, Decimal("90"))
            self.assertFalse(
                c.piso_elevou(int(gasto), objetivo, alvo),
                "%s virou piso sem que nada elevasse a meta" % objetivo,
            )

    def test_a_condicao_da_tela_nao_nomeia_objetivo(self):
        """Enumerar objetivo na view é o que fez o defeito nascer. Se alguém
        reintroduzir `plan.goal == Goal.CUT` ali, isto fica vermelho.

        OS COMENTÁRIOS SAEM ANTES DA ASSERÇÃO, e não é firula: a primeira
        versão deste teste falhou porque o comentário da própria correção CITA
        `plan.goal == Goal.CUT` para explicar o que saiu. A asserção casava com
        a explicação, não com o código — a armadilha que o `CLAUDE.md` descreve
        e que `push/test_cache_privado.py` resolve com o mesmo helper.
        """
        import inspect
        import re

        from plans import views

        fonte = inspect.getsource(views.energy_balance)
        sem_comentario = re.sub(r"#.*", "", fonte)

        self.assertIn("piso_elevou", sem_comentario)
        self.assertNotIn("plan.goal == Goal.CUT", sem_comentario)


class ObjetivoDesconhecidoNaoDerrubaATelaTests(SimpleTestCase):
    """`NutritionPlan.goal` é `CharField` com `choices` e SEM default.

    Todo plano criado sem informar o objetivo fica com `""`, e a primeira
    versão de `piso_elevou` levantava `KeyError` ao consultar a tabela de
    ajustes — derrubando a tela Hoje inteira. A condição antiga só comparava
    strings e devolvia False; a nova precisa devolver o mesmo.
    """

    def test_objetivo_vazio_devolve_False_em_vez_de_estourar(self):
        self.assertFalse(c.piso_elevou(2000, "", 2200))

    def test_objetivo_inventado_devolve_False_em_vez_de_estourar(self):
        self.assertFalse(c.piso_elevou(2000, "virar_ciclista", 2200))
