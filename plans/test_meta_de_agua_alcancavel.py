# -*- coding: utf-8 -*-
"""A meta de água tem de caber no que o servidor deixa registrar.

Eram dois números que não se conheciam: `hidratacao_ml` é linear em 35 ml/kg e
não tinha limite, e a view que grava recusava passar de 10.000 ml no dia. Quem
pesasse 293 kg ou mais recebia uma meta que o próprio app impedia de alcançar.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from plans.weight_trend import TETO_DIARIO_ML, hidratacao_ml


class NenhumPesoPedeMaisDoQueOAppAceitaTests(SimpleTestCase):
    def test_o_peso_maximo_do_cadastro_ainda_tem_meta_alcancavel(self):
        """400 kg é o teto de `PesoField`. A meta ali era 14.000 ml contra um
        teto de 10.000 — impossível por construção."""
        self.assertLessEqual(hidratacao_ml(Decimal("400")), TETO_DIARIO_ML)

    def test_varredura_da_faixa_inteira_que_o_cadastro_aceita(self):
        """De 20 a 400 kg, de quilo em quilo: nenhuma meta pode passar do teto.

        Varredura e não três casos escolhidos a dedo — o defeito original
        aparecia só a partir de 293 kg, e nenhum caso redondo o alcançava.
        """
        for kg in range(20, 401):
            self.assertLessEqual(
                hidratacao_ml(Decimal(kg)), TETO_DIARIO_ML,
                "%d kg pede mais do que o app deixa registrar" % kg,
            )

    def test_o_peso_comum_nao_foi_afetado_pelo_teto(self):
        """CONTROLE POSITIVO: o teto não pode ter achatado a meta de ninguém
        que já usava o app. 82,5 kg continua em 2.900 ml arredondados."""
        self.assertEqual(hidratacao_ml(Decimal("82.5")), 3000)
        self.assertEqual(hidratacao_ml(Decimal("102")), 3500)
        self.assertEqual(hidratacao_ml(Decimal("60")), 2000)

    def test_a_view_e_a_meta_usam_a_MESMA_constante(self):
        """A incoerência nasceu de o teto ser um literal solto dentro de um
        `update()`. Se alguém reintroduzir o número cru, isto fica vermelho."""
        import inspect

        from plans import views

        fonte = inspect.getsource(views.LogHydrationView)
        self.assertIn("TETO_DIARIO_ML", fonte)
        self.assertNotIn("Value(10000)", fonte)
