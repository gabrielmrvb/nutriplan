"""A etapa 3 do cadastro: o resumo respira, e cartão sem ícone não desenha caixa.

QA exploratório de 27/09/2026 (`achados/qa-exploratorio-20260927.md`, M7).
Na captura da etapa 3, "Divisão · 2 grupos por dia" (a última linha do
resumo) encostava em "Que tipo de cardápio você quer?", sem respiro. A causa:
`.resumo-etapas` não tinha regra nenhuma no CSS, então o `<dl>` terminava
sem margem.

No mesmo passo, o cartão "Não quero priorizar agora" desenhava a caixa do
ícone vazia. `detalhe()` devolve `None` para a opção sem desenho, e o
docstring dele já prometia "a escolha aparece sem ícone"; o que faltava era
o template não emitir a caixa nesse caso.
"""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Profile

User = get_user_model()


class OCartaoSemDesenhoNaoTemCaixaTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(email="etapa3@exemplo.com")
        Profile.objects.create(user=user, sex="M", birth_date="1995-04-12",
                               height_cm=178, onboarding_step=3)
        self.client.force_login(user)

    def _cartao(self, valor):
        html = self.client.get(reverse("accounts:onboarding_step", args=[3])).content.decode()
        casou = re.search(
            # O cartão da PRIORIDADE: desde 28/09/2026 os interesses, que vêm
            # antes na mesma etapa, também são `choice-card` e têm "treino".
            r'<label class="choice-card">\s*<input[^>]*name="prioridade"[^>]*value="%s".*?</label>' % re.escape(valor),
            html, re.S)
        self.assertIsNotNone(casou, "cartão %r não achado" % valor)
        return casou.group(0)

    def test_nao_priorizar_nao_tem_caixa_de_icone(self):
        self.assertNotIn("choice-card__icon", self._cartao("nenhuma"))

    def test_o_cartao_com_desenho_continua_com_icone(self):
        """Controle positivo: a mesma leitura acha o ícone onde ele existe."""
        self.assertIn('<use href="#icone-', self._cartao("treino"))


class OResumoTemMargemTests(TestCase):
    def test_o_css_da_margem_ao_resumo(self):
        css = (Path(settings.BASE_DIR) / "static/css/app.css").read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        regra = re.search(r"\.resumo-etapas\s*\{([^}]*)\}", css)
        self.assertIsNotNone(regra, "falta a regra de .resumo-etapas")
        self.assertIn("margin-bottom", regra.group(1))
