# -*- coding: utf-8 -*-
"""A lista de compras não pode escrever quantidade em notação científica."""
from decimal import Decimal

from django.test import SimpleTestCase

from plans.shopping import humanize


class AQuantidadeSeLeNoCorredorTests(SimpleTestCase):
    def test_multiplo_exato_de_dez_quilos_nao_vira_expoente(self):
        """`Decimal("10").normalize()` é `Decimal("1E+1")`, e a lista imprimia
        "1E+1 kg" para dez quilos de arroz. Acima de um quilo os degraus de
        compra são de 100 g, então o múltiplo exato de 10.000 é alcançável."""
        self.assertEqual(humanize(Decimal("10000"), "g"), "10 kg")
        self.assertEqual(humanize(Decimal("20000"), "g"), "20 kg")
        self.assertEqual(humanize(Decimal("100000"), "g"), "100 kg")
        self.assertEqual(humanize(Decimal("10000"), "ml"), "10 L")

    def test_a_fracao_continua_com_virgula_e_sem_zero_a_toa(self):
        """CONTROLE POSITIVO: era isto que `normalize()` acertava, e a correção
        não pode ter trocado um defeito por outro."""
        self.assertEqual(humanize(Decimal("1500"), "g"), "1,5 kg")
        self.assertEqual(humanize(Decimal("10500"), "g"), "10,5 kg")
        self.assertEqual(humanize(Decimal("1200"), "g"), "1,2 kg")
        self.assertEqual(humanize(Decimal("2500"), "ml"), "2,5 L")

    def test_abaixo_de_um_quilo_continua_em_gramas(self):
        self.assertEqual(humanize(Decimal("999"), "g"), "999 g")
        self.assertEqual(humanize(Decimal("1000"), "g"), "1 kg")

    def test_nenhum_degrau_alcancavel_produz_a_letra_E(self):
        """VARREDURA, e é ela que impede a correção de valer só para os casos
        que eu lembrei de escrever: todo múltiplo de 100 g de 1 kg a 100 kg."""
        for gramas in range(1000, 100_001, 100):
            texto = humanize(Decimal(gramas), "g")
            self.assertNotIn("E", texto, "%d g virou %r" % (gramas, texto))
            self.assertNotIn(".", texto, "%d g veio com ponto: %r" % (gramas, texto))
