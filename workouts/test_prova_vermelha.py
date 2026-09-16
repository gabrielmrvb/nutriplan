# -*- coding: utf-8 -*-
"""PROVA DO GATE — este arquivo NUNCA entra em `main`.

Um teste que falha de propósito, fora do subconjunto do pre-push (que
roda `config`, o dourado, a doutrina, o gate por letra e os orçamentos):
o atalho local deixa passar, o CI reprova, e a proteção de `main` recusa
o merge. É a prova de que o julgamento é o CI — e o PR é fechado sem
merge assim que a recusa está registrada.
"""
from django.test import SimpleTestCase


class AProvaDoGateTests(SimpleTestCase):
    def test_o_ci_reprova_o_que_o_atalho_deixa_passar(self):
        self.fail("prova do gate: este teste existe para ficar vermelho no CI")
