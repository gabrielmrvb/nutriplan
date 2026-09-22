"""O erro de um formulário nasce JUNTO do campo — e a tela vai até ele.

Item 3 da missão de UX (22/09/2026): "Este campo é obrigatório." aparecia
ISOLADO, numa faixa no topo da tela, sem dizer qual campo nem rolar até
ele. Medido no navegador: só as ações POST → redirect → flash faziam isso —
o peso, na Home e no Progresso. Os formulários renderizados na mesma
resposta (etapa 2, corrida, reportar) já erravam no próprio campo.

Duas metades, e as duas têm teste:

- o SERVIDOR marca o campo (`aria-invalid`, `aria-describedby`) e escreve a
  mensagem embaixo dele, mesmo quando a resposta é um redirect: a recusa
  viaja pela sessão com a mensagem, não só com o valor;
- o JAVASCRIPT (`pwa.js`, "FOCO NO ERRO") leva a tela até o primeiro campo
  inválido e o foca, em TODA página — o `autofocus` das caixas de
  consentimento era a versão de um formulário só.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from plans.tests import create_complete_user


class PesoRecusadoJuntoDoCampoTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="peso-erro@exemplo.com")
        self.client.force_login(self.user)

    def _formulario(self, html):
        return html.split('<form class="pesagem"', 1)[1].split("</form>", 1)[0]

    def test_na_home_o_campo_fica_marcado_e_a_mensagem_mora_embaixo_dele(self):
        resposta = self.client.post(reverse("accounts:log_weight"), {"weight_kg": "", "origem": "hoje"}, follow=True)
        html = resposta.content.decode()
        form = self._formulario(html)
        self.assertIn('aria-invalid="true"', form)
        self.assertRegex(form, r'aria-describedby="[^"]*peso_error')
        self.assertRegex(form, r'<ul class="field__errors[^"]*" id="peso_error"')
        self.assertIn("Digite o peso", form)
        # e a faixa do topo, quando existe, diz DE QUE campo é o erro
        for m in re.findall(r'class="flash__item[^"]*">(.*?)</p>', html, flags=re.S):
            if "peso" in m.lower() or "obrigat" in m.lower():
                self.assertIn("Peso", m)

    def test_no_progresso_tambem(self):
        resposta = self.client.post(reverse("accounts:log_weight"), {"weight_kg": "8o", "origem": "metricas"}, follow=True)
        form = self._formulario(resposta.content.decode())
        self.assertIn('aria-invalid="true"', form)
        self.assertIn('value="8o"', form)
        self.assertIn("use números, como 82,5", form)

    def test_sem_recusa_o_campo_nao_esta_marcado(self):
        form = self._formulario(self.client.get(reverse("plans:history")).content.decode())
        self.assertNotIn("aria-invalid", form)
        self.assertNotIn("field__errors", form)


class FocoNoErroTests(TestCase):
    def test_o_pwa_leva_a_tela_ate_o_primeiro_campo_invalido(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        bloco = js.split("FOCO NO ERRO", 1)
        self.assertEqual(len(bloco), 2, "pwa.js sem o bloco FOCO NO ERRO")
        corpo = bloco[1][:3000]
        self.assertIn('[aria-invalid="true"]', corpo)
        self.assertIn("scrollIntoView", corpo)
        self.assertIn(".focus(", corpo)
        # quem já tem `autofocus` na página manda; o script não briga com ele
        self.assertIn("autofocus", corpo)
