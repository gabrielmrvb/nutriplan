"""Cartão dentro de cartão é moldura repetida — o defeito que a T3.3 do plano
mestre existe para impedir ("três caixas com borda dentro de uma caixa com
borda"). Antes de trocar a pele de 114 cartões, medir: hoje, quantos nascem
aninhados? A resposta vira catraca."""
from html.parser import HTMLParser

from django.core.management import call_command
from django.test import TestCase

from plans.tests import create_complete_user


class _Aninhamento(HTMLParser):
    VAZIOS = {"br", "img", "input", "meta", "link", "hr", "source", "use", "path", "circle", "rect", "line"}

    def __init__(self):
        super().__init__()
        self.pilha = []  # True quando o elemento aberto é um .card
        self.aninhados = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VAZIOS:
            return
        classes = dict(attrs).get("class", "").split()
        eh_card = "card" in classes
        if eh_card and any(self.pilha):
            self.aninhados.append(" ".join(classes))
        self.pilha.append(eh_card)

    def handle_endtag(self, tag):
        if tag in self.VAZIOS or not self.pilha:
            return
        self.pilha.pop()


def cartoes_aninhados(html):
    p = _Aninhamento()
    p.feed(html)
    return p.aninhados


class CartaoDentroDeCartaoTests(TestCase):
    ROTAS = ("/", "/treino/", "/historico/", "/hidratacao/", "/areas/", "/conquistas/", "/conta/perfil/")

    #: Catraca: o que se mede hoje. Só desce.
    TETO_ANINHADOS = 0

    @classmethod
    def setUpTestData(cls):
        # Os mesmos seeds do deploy: sem o catálogo de treino, `/treino/`
        # estoura em `create_routine` ("A divisão abc não está no catálogo");
        # sem alimentos, a Home nasce sem refeição e a medida sai menor do que
        # a tela que a pessoa vê.
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user("cartoes@exemplo.com")
        self.client.force_login(self.user)

    def test_o_leitor_enxerga_um_aninhamento(self):
        """Controle positivo do leitor: sem isto, um HTML sem `.card` deixaria o
        teste verde por não achar nada."""
        self.assertEqual(cartoes_aninhados('<div class="card a"><section class="card b"></section></div>'), ["card b"])
        self.assertEqual(cartoes_aninhados('<div class="card a"></div><div class="card b"></div>'), [])

    def test_nenhuma_rota_renderiza_cartao_dentro_de_cartao(self):
        achados = {}
        for rota in self.ROTAS:
            resposta = self.client.get(rota, follow=True)
            self.assertEqual(resposta.status_code, 200, rota)
            aninhados = cartoes_aninhados(resposta.content.decode())
            if aninhados:
                achados[rota] = aninhados
        total = sum(len(v) for v in achados.values())
        self.assertLessEqual(total, self.TETO_ANINHADOS, f"cartões aninhados: {achados}")
