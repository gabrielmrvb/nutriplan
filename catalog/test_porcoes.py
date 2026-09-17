# -*- coding: utf-8 -*-
"""Toda porção tem nome no singular e no plural — escritos, não derivados.

"Aveia 116 g" (avaliação de 16/09, B15) não é o que uma pessoa mede na cozinha;
"7,5 colheres de sopa" é. A porção já estava no banco e nunca era lida. O plural
é escrito no catálogo porque pt-BR não deriva "colher → colheres" por regra.
"""
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from catalog.models import FoodPortion
from plans.porcoes import _formatar, medida_caseira


class OCatalogoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def test_toda_porcao_tem_singular_e_plural(self):
        vazias = [str(p) for p in FoodPortion.objects.all() if not p.singular or not p.plural]
        self.assertEqual(vazias, [])

    def test_o_rotulo_nao_carrega_numero(self):
        com_numero = [p.singular for p in FoodPortion.objects.all() if p.singular[0].isdigit() or p.singular.startswith("1/")]
        self.assertEqual(com_numero, [])


class AMedidaCaseiraTests(TestCase):
    def _porcao(self, gramas):
        return FoodPortion(grams=Decimal(gramas), singular="colher de sopa", plural="colheres de sopa")

    def test_arredonda_a_meio_com_virgula(self):
        self.assertEqual(medida_caseira(Decimal("116"), self._porcao(15)), ("7,5", "colheres de sopa"))
        self.assertEqual(medida_caseira(Decimal("30"), self._porcao(15)), ("2", "colheres de sopa"))

    def test_singular_quando_e_um(self):
        self.assertEqual(medida_caseira(Decimal("16"), self._porcao(15)), ("1", "colher de sopa"))

    def test_menos_de_meia_porcao_nao_vira_medida(self):
        self.assertIsNone(medida_caseira(Decimal("5"), self._porcao(15)))

    def test_meio_sobe(self):
        # 3,25 porções → 3,5 (ROUND_HALF_UP no meio-degrau), não 3
        self.assertEqual(medida_caseira(Decimal("48.75"), self._porcao(15))[0], "3,5")

    def test_multiplo_de_dez_nao_vira_notacao_cientifica(self):
        # Decimal.normalize() derruba zero à direita trocando para notação
        # científica quando isso encurta a representação: Decimal("10.0")
        # normaliza para Decimal("1E+1"). 150 g numa colher de 15 g dá
        # n = 10 porções, e a Home mostrava "1E+1 colheres de sopa (150 g)"
        # em vez de "10 colheres de sopa (150 g)".
        self.assertEqual(medida_caseira(Decimal("150"), self._porcao(15)), ("10", "colheres de sopa"))


class AFormatarTests(TestCase):
    def test_formata_cada_degrau_sem_notacao_cientifica(self):
        casos = {
            "10": "10",
            "20": "20",
            "100": "100",
            "12.5": "12,5",
            "0.5": "0,5",
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                texto = _formatar(Decimal(valor))
                self.assertEqual(texto, esperado)
                self.assertNotIn("E", texto)
