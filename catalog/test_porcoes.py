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

    def test_meia_porcao_sai_como_glifo_e_no_singular(self):
        """QA local da Fase 3 (17/09/2026) viu "0,5 xícaras", "0,5 unidades
        médias", "0,5 colheres de sopa" na Home. Meia porção é "½" + rótulo
        SINGULAR: "½ xícara (100 ml)". O glifo evita a concordância de gênero
        de "meio/meia" — que o catálogo não sabe — e o singular é o que se
        diz em português para uma fração de UMA unidade."""
        self.assertEqual(medida_caseira(Decimal("8"), self._porcao(15)), ("½", "colher de sopa"))
        xicara = FoodPortion(grams=Decimal("200"), singular="xícara", plural="xícaras")
        self.assertEqual(medida_caseira(Decimal("100"), xicara), ("½", "xícara"))
        unidade = FoodPortion(grams=Decimal("120"), singular="unidade média", plural="unidades médias")
        self.assertEqual(medida_caseira(Decimal("60"), unidade), ("½", "unidade média"))

    def test_um_e_meio_continua_com_virgula_e_no_plural(self):
        """CONTROLE: só o meio exato vira glifo. 1,5 e acima seguem "1,5
        xícaras" — número com vírgula e rótulo no plural."""
        xicara = FoodPortion(grams=Decimal("200"), singular="xícara", plural="xícaras")
        self.assertEqual(medida_caseira(Decimal("300"), xicara), ("1,5", "xícaras"))
        self.assertEqual(medida_caseira(Decimal("500"), xicara), ("2,5", "xícaras"))

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
