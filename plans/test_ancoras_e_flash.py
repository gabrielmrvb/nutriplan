""""Entrou na lista" tem flash e âncora no item; toda âncora respeita a app-bar.

UX P1-10 / E03 (14/09/2026): acrescentar um item à lista devolvia para
`#seus-itens` — o topo do cartão —, e o item novo, no fim da lista, ficava
fora da tela a 320; nenhuma mensagem dizia que algo aconteceu. Agora o
redirect pousa no PRÓPRIO item (`#item-<id>`) e a tela diz "X entrou na
lista".

NOVO-02: a barra de cima é `sticky` (desde T1.4 ela gruda de verdade), e
toda âncora pousava com o alvo debaixo dela — `#slot-N` ("Ver refeição"
do cartão AGORA), `#seus-itens`, `#hidratacao`, `#pesar`. `scroll-margin-top`
com a altura da barra, num token, resolve para todas de uma vez.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import ItemAvulsoDaLista
from .tests import create_complete_user

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"


class ItemNovoTemFlashEAncoraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        services.create_plan(self.user)
        self.client.force_login(self.user)

    def test_o_redirect_pousa_no_item_e_a_tela_diz_que_ele_entrou(self):
        resposta = self.client.post(
            reverse("plans:adicionar_item"), {"nome": "Café", "opcao": "A"}
        )
        item = ItemAvulsoDaLista.objects.get(user=self.user, nome="Café")
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(resposta["Location"].endswith("#item-%d" % item.pk), resposta["Location"])

        pagina = self.client.get(resposta["Location"].split("#")[0])
        self.assertContains(pagina, 'id="item-%d"' % item.pk)
        self.assertContains(pagina, "Café entrou na lista")

    def test_remover_continua_pousando_na_secao(self):
        item = ItemAvulsoDaLista.objects.create(
            user=self.user, nome="Café", semana=timezone.localdate()
        )
        resposta = self.client.post(
            reverse("plans:remover_item"), {"item_id": item.pk, "opcao": "A"}
        )
        self.assertTrue(resposta["Location"].endswith("#seus-itens"))


class TodaAncoraRespeitaAAppBarTests(SimpleTestCase):
    def test_o_token_existe_e_as_ancoras_o_usam(self):
        css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
        self.assertRegex(css, r"--appbar-h:\s*[\d.]+rem;")
        m = re.search(r"\[id\]\s*\{([^}]*)\}", css)
        self.assertIsNotNone(m, "a regra geral de âncora ([id]) não existe")
        self.assertIn("scroll-margin-top: var(--appbar-h)", m.group(1))
