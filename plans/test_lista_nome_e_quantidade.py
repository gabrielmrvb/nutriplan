"""A lista de compras não repete o nome do alimento na quantidade.

UX P1-03 (14/09/2026), medido a 320 e 390: "Arroz branco cozido" na coluna do
nome e "~1,4 kg de arroz branco (cru)" na da quantidade — a quantidade era
`nowrap` e ficava FORA do rótulo, então o nome, que é o que encolhe,
quebrava letra por letra ("A r r o z…"). O nome só existe uma vez, no
rótulo; a quantidade diz o número e o estado ("(cru)"), mora DENTRO do
rótulo e empilha abaixo do nome quando não cabe ao lado.

Regra: para todo item, o texto da quantidade não contém `Food.name`; o
`<label class="shopping__check">` contém `.shopping__qty`. Sabotagem que
precisa ficar vermelha: voltar o nome à quantidade (`converter`), ou tirar
a quantidade de dentro do rótulo.
"""

import re
from decimal import Decimal

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import compra, services
from .tests import create_complete_user


class AQuantidadeNaoRepeteONomeTests(SimpleTestCase):
    def test_cozido_para_cru_diz_o_estado_e_nao_o_nome(self):
        for nome in compra.FATOR_CRU:
            with self.subTest(nome=nome):
                texto, aproximado = compra.converter(nome, Decimal("1400"), "g")
                self.assertTrue(aproximado)
                raiz = re.sub(r"\s+cozid[oa]$", "", nome).lower()
                self.assertNotIn(raiz, texto.lower(), texto)

    def test_o_estado_e_o_genero_do_alimento(self):
        self.assertEqual(compra.converter("Arroz branco cozido", Decimal("1400"), "g")[0], "600 g (cru)")
        self.assertEqual(compra.converter("Lentilha cozida", Decimal("1400"), "g")[0], "600 g (crua)")

    def test_quando_se_compra_outro_produto_o_rotulo_inteiro_fica(self):
        """Cuscuz se compra como flocão de milho: aí o rótulo é informação."""
        texto, _ = compra.converter("Cuscuz de milho cozido", Decimal("1400"), "g")
        self.assertEqual(texto, "600 g de flocão de milho")

    def test_quem_se_compra_por_peso_continua_so_com_o_numero(self):
        texto, aproximado = compra.converter("Batata-doce", Decimal("2100"), "g")
        self.assertFalse(aproximado)
        self.assertEqual(texto, "2,1 kg")


class AQuantidadeMoraDentroDoRotuloTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        services.create_plan(self.user)
        self.client.force_login(self.user)

    def test_cada_rotulo_traz_nome_e_quantidade_e_a_quantidade_nao_repete_o_nome(self):
        html = self.client.get(reverse("plans:shopping")).content.decode()
        rotulos = re.findall(r'<label class="shopping__check">(.*?)</label>', html, re.S)
        com_nome = [r for r in rotulos if 'class="shopping__name"' in r]
        self.assertTrue(com_nome, "a lista precisa ter itens do cardápio")
        for rotulo in com_nome:
            nome = re.search(r'class="shopping__name">([^<]*)<', rotulo).group(1).strip()
            qtd = re.search(r'class="shopping__qty[^"]*"[^>]*>([^<]*)<', rotulo)
            with self.subTest(nome=nome):
                self.assertIsNotNone(qtd, "a quantidade tem de estar DENTRO do rótulo")
                self.assertNotIn(nome.lower(), qtd.group(1).lower())
        # Fora do rótulo não sobra quantidade nenhuma.
        fora = re.sub(r'<label class="shopping__check">.*?</label>', "", html, flags=re.S)
        self.assertEqual(fora.count('class="shopping__qty'), 0, "quantidade fora do rótulo")
