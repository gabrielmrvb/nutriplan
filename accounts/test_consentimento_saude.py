# -*- coding: utf-8 -*-
"""A caixa de saúde diz para quê o dado serve e como revogar — LGPD art. 11,
I ("finalidades específicas") e art. 9º, § 3º (consequência de recusar).

Rascunho do dono, §3.3 (28/09/2026): o texto entra como está, marcado
`[REVISAR]` em `accounts/consentimento.py`. Este teste cobre só as duas
garantias que a Missão M7 exige — finalidade e caminho de revogação —, não
o texto inteiro palavra por palavra."""
from django.test import TestCase

from accounts import consentimento
from accounts.models import Consentimento


class ACaixaDeSaudeTests(TestCase):
    def test_o_texto_diz_finalidade_e_revogacao(self):
        texto = consentimento.ROTULOS[Consentimento.Tipo.SAUDE]
        self.assertIn("para calcular e ajustar", texto)
        self.assertIn("excluindo a conta", texto)

    def test_a_versao_subiu_com_o_texto(self):
        self.assertEqual(consentimento.VERSAO_DOS_LEGAIS, "2026-09-28")
