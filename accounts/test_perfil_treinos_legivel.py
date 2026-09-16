# -*- coding: utf-8 -*-
"""O cartão "Treinos" do Perfil a 390 px: uma lista, dias curtos, nada partido.

Revisão visual da avaliação de 16/09/2026 (B33): o cartão tinha DUAS `<dl
class="data-list">` coladas — "Acorda" grudado em "Dias" sem divisor, porque a
regra `:last-child { border-bottom: 0 }` da primeira encostava na
`:first-child { padding-top: 0 }` da segunda — e o valor dos dias era
"Segunda-feira · Terça-feira · Quarta-feira · Quinta-feira · Sexta-feira",
que numa coluna de 390 px partia em "Quinta-/feira". O resumo da etapa 3 já
escreve "Seg, Ter, Qua"; o Perfil escreve os mesmos dias com o mesmo
vocabulário, lendo `DIA_CURTO` em vez de uma terceira lista de nomes.
"""
import re

from django.test import TestCase
from django.urls import reverse

from plans.tests import create_complete_user


class OCartaoDeTreinosDoPerfilTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)
        html = self.client.get(reverse("accounts:profile")).content.decode()
        inicio = html.index("<h2>Treinos</h2>")
        fim = html.index("</section>", inicio)
        self.cartao = html[inicio:fim]

    def test_os_dias_saem_curtos_como_no_resumo_da_etapa_3(self):
        # O fixture treina segunda, quarta e sexta.
        self.assertIn("Seg · Qua · Sex", self.cartao)
        self.assertNotIn("Segunda-feira", self.cartao)

    def test_o_cartao_tem_uma_lista_so(self):
        """Experiência, Dias, Acorda e Dorme são fatos do mesmo assunto; duas
        listas coladas desenham uma linha sem divisor e sem respiro."""
        self.assertEqual(len(re.findall(r'<dl class="data-list"', self.cartao)), 1)
        for rotulo in ("Experiência", "Dias", "Acorda", "Dorme"):
            self.assertIn("<dt>%s</dt>" % rotulo, self.cartao)

    def test_sem_dias_o_convite_continua_e_a_janela_do_dia_tambem(self):
        self.user.training_days.all().delete()
        html = self.client.get(reverse("accounts:profile")).content.decode()
        inicio = html.index("<h2>Treinos</h2>")
        cartao = html[inicio:html.index("</section>", inicio)]
        self.assertIn("Cadastrar dias de treino", cartao)
        self.assertIn("<dt>Acorda</dt>", cartao)
