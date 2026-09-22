"""A lista de sugestões do "Comi outra coisa" tem nomes, não 62 valores vazios.

Regressão do PR #102 (21/09/2026), achada pelas três personas (achado #2):
`alimentos_do_catalogo()` passou a devolver STRINGS (a lista em cache de 15
min), e o template continuou lendo `{{ food.name }}` — o `<datalist>` saía
com 62 `<option value="">`. Sem sugestão, "pão de queijo 80 g" entrava
como registro sem calorias e sem aviso; só o nome EXATO do catálogo conta.
"""
import re

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from plans.tests import create_complete_user


class DatalistDoCatalogoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        # A lista fica 15 min em cache POR PROCESSO: outro teste pode ter
        # guardado uma lista vazia antes de o catálogo existir.
        cache.delete("plans.alimentos_do_catalogo")

    def test_a_home_lista_os_alimentos_do_catalogo_por_nome(self):
        user = create_complete_user(email="datalist@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("plans:today")).content.decode()
        lista = html.split('<datalist id="alimentos-do-catalogo">', 1)[1].split("</datalist>", 1)[0]
        valores = re.findall(r'<option value="([^"]*)"', lista)
        self.assertGreater(len(valores), 30)
        self.assertNotIn("", valores)
        self.assertIn("Arroz branco cozido", valores)
