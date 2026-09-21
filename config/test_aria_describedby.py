# -*- coding: utf-8 -*-
"""Todo `aria-describedby` da página aponta para um `id` que existe nela.

O Django 5.2 escreve `aria-describedby="id_x_helptext id_x_error"` no
`<input>` (e `aria-invalid="true"` quando há erro). O parcial
`partials/field.html` renderizava a ajuda como `<div class="field__help">` e
os erros como `<ul class="field__errors">` — SEM esses ids. Medido em produção
em 16/09/2026 (avaliação, B10): no cadastro com e-mail inválido,
`document.getElementById("id_email_error")` devolvia `null`. O leitor de tela
anunciava "inválido" e não lia qual era o erro nem a ajuda — em todo
formulário do app.

Rádios e caixas em grupo não recebem o atributo no `<input>` (o Django o põe
no `<fieldset>` do próprio template dele); aqui o grupo é um `<div
role="group">` que envolve a `<ul>`, e é ele que carrega o rótulo e a
descrição (a `<ul>` fica lista: `config/test_axe_serio.py`).
"""
import re

from django.test import TestCase
from django.urls import reverse

from plans.tests import create_complete_user

DESCRITO_POR = re.compile(r'aria-describedby="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')


def _ids_orfaos(html):
    ids = set(IDS.findall(html))
    orfaos = []
    for lista in DESCRITO_POR.findall(html):
        for alvo in lista.split():
            if alvo not in ids:
                orfaos.append(alvo)
    return orfaos


class ErroEAjudaFicamLigadosAoCampoTests(TestCase):
    def test_cadastro_com_erro_liga_o_erro_ao_campo(self):
        html = self.client.post(
            reverse("accounts:signup"),
            {"first_name": "Ana", "email": "nao-e-email", "password1": "12345678", "password2": "87654321"},
        ).content.decode()
        self.assertIn('aria-invalid="true"', html)
        self.assertIn("aria-describedby=", html)
        # Controle positivo: há erro de e-mail e ele é referenciado.
        self.assertIn("id_email_error", DESCRITO_POR.search(html).group(1) if "id_email_error" in html else "")
        self.assertEqual(_ids_orfaos(html), [])

    def test_cadastro_sem_erro_liga_a_ajuda_ao_campo(self):
        html = self.client.get(reverse("accounts:signup")).content.decode()
        self.assertIn("_helptext", html)
        self.assertEqual(_ids_orfaos(html), [])

    def test_etapa_1_com_altura_absurda_liga_o_erro(self):
        user = create_complete_user()
        self.client.force_login(user)
        html = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 1}),
            {"sex": "M", "birth_date": "1996-03-10", "height_cm": "300", "weight_kg": "82,5"},
        ).content.decode()
        self.assertIn("id_height_cm_error", html)
        self.assertEqual(_ids_orfaos(html), [])

    def test_etapa_2_vazia_descreve_o_grupo_de_radios(self):
        """Grupo de rádio não leva `aria-describedby` no `<input>`; o grupo
        (a `<ul>`) é quem carrega rótulo e erro."""
        user = create_complete_user()
        self.client.force_login(user)
        html = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 2}), {}
        ).content.decode()
        self.assertIn("Este campo é obrigatório", html)
        # Os dois parciais de grupo: `field.html` (choice-list) e
        # `choice_cards.html` (choice-cards).
        # Desde 20/09/2026 o grupo ENVOLVE a lista (`config/test_axe_serio.py`):
        # a `<ul>` fica sem `role`, e o `<div role="group">` logo antes dela
        # carrega rótulo e descrição.
        grupos = re.findall(r'<div role="group"[^>]*>\s*<ul class="choice-(?:list|cards)[^"]*">', html)
        self.assertGreaterEqual(len(grupos), 4)
        for grupo in grupos:
            self.assertIn('role="group"', grupo)
            self.assertIn("aria-labelledby=", grupo)
        # O grupo do objetivo, que falhou, aponta para o erro dele; o dos dias,
        # que tem ajuda e não falhou, aponta só para a ajuda.
        objetivo = next(g for g in grupos if "goal_label" in g)
        self.assertRegex(objetivo, r'aria-describedby="[^"]*goal_error"')
        dias = next(g for g in grupos if "weekdays_label" in g)
        self.assertRegex(dias, r'aria-describedby="[^"]*weekdays_helptext"')
        self.assertNotIn("weekdays_error", dias)
        self.assertEqual(_ids_orfaos(html), [])
