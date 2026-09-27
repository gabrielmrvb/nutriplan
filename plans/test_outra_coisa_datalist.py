"""A sugestão do "Comi outra coisa" tem nomes, não 62 valores vazios.

Regressão do PR #102 (21/09/2026), achada pelas três personas (achado #2):
`alimentos_do_catalogo()` passou a devolver STRINGS (a lista em cache de 15
min), e o template continuou lendo `{{ food.name }}` — o `<datalist>` saía
com 62 `<option value="">`. Sem sugestão, "pão de queijo 80 g" entrava
como registro sem calorias e sem aviso; só o nome EXATO do catálogo contava.

O `<datalist>` SAIU em 26/09/2026 (item 3 da missão "quem entra não
desiste"): com os 583 alimentos da TACO ele seriam ~20 kB de `<option>` nesta
tela em toda visita, e ele casava por prefixo do nome INTEIRO, então
"requeijao" não achava "Queijo, requeijão, cremoso". A sugestão virou
`plans:buscar_alimento`.

ESTE ARQUIVO FICA porque o defeito que ele descreve não é o `<datalist>`: é a
tela sugerir NOME VAZIO. A asserção mudou de lugar junto com o mecanismo — e o
resto do item 3 mora em `plans/test_comi_outra_coisa.py`.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from plans.tests import create_complete_user


class SugestaoDoCatalogoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="datalist@exemplo.com")
        self.client.force_login(self.user)

    def test_a_sugestao_traz_o_nome_do_alimento_e_nunca_vazio(self):
        resposta = self.client.get(reverse("plans:buscar_alimento"), {"q": "arroz"})
        itens = resposta.json()["itens"]
        self.assertTrue(itens)
        nomes = [i["nome"] for i in itens]
        self.assertNotIn("", nomes)
        self.assertIn("Arroz branco cozido", nomes)

    def test_a_tela_do_cardapio_aponta_para_a_busca(self):
        """O campo existe e é o da busca — sem isto, o teste acima passaria
        sobre um endpoint que nenhuma tela usa."""
        html = self.client.get(reverse("plans:alimentacao")).content.decode()
        self.assertIn("data-busca-campo", html)
