"""A superfície de foco existe, é usada, e é UMA por tela.

A ideia central do REDESIGN V1 cabe numa frase: em cada tela há um bloco que
responde "o que eu faço agora?", e ele não deve apenas vir primeiro — deve
PARECER diferente. Numa coluna de cartões com o mesmo fundo, "primeiro" é uma
informação que some no instante em que a pessoa rola.

Por que este arquivo existe, e não bastava a régua de token órfão: aquela
prova que `--surface-focus` está declarado e usado em ALGUM lugar. Como dois
blocos o usam — o cartão AGORA e o hero de treino —, apagar o fundo de um dos
dois deixaria o token vivo por causa do outro, e a regressão passaria em
verde. Aqui a asserção é sobre CADA dono.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css" / "app.css"

#: Os donos da superfície de foco, e o que cada um responde na sua tela.
DONOS = {
    ".agora-card": "a próxima ação em /hoje/",
    ".hoje": "o treino de hoje em /treino/",
}


def sem_comentarios(texto):
    """O CSS sem comentários.

    Os comentários que explicam a superfície de foco CITAM
    `background: var(--surface-focus)` e os nomes das duas classes. Sem
    removê-los, toda asserção abaixo casaria com a prosa que descreve a
    regra em vez de com a regra.
    """
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def bloco(css, seletor):
    achado = re.search(re.escape("\n" + seletor) + r"\s*\{([^}]*)\}", css)
    return achado.group(1) if achado else None


class ASuperficieDeFocoTemDonoTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_o_token_existe_nos_dois_temas(self):
        """Escuro e claro, e o claro não é o escuro invertido.

        No tema claro escurecer um bloco lê como desabilitado; a superfície de
        foco de lá é um lavado claro de verde. Se um dos dois sumir, a tela
        perde o destaque num tema e ninguém percebe no outro.
        """
        valores = re.findall(r"--surface-focus:\s*([^;]+);", self.css)

        self.assertEqual(
            len(valores), 2,
            f"esperava um valor por tema, achei {valores}",
        )
        self.assertNotEqual(
            valores[0].strip(), valores[1].strip(),
            "os dois temas receberam a MESMA cor de foco — um dos dois está "
            "com o valor do outro",
        )

    def test_cada_dono_pinta_o_proprio_fundo_com_ela(self):
        """A regressão que a régua de token órfão não pega."""
        for seletor, papel in DONOS.items():
            with self.subTest(seletor=seletor):
                corpo = bloco(self.css, seletor)
                self.assertIsNotNone(corpo, f"sumiu a regra {seletor}")
                self.assertIn(
                    "var(--surface-focus)", corpo,
                    f"{seletor} ({papel}) deixou de usar a superfície de foco: "
                    "volta a parecer um cartão como qualquer outro",
                )

    def test_o_destaque_nao_depende_so_da_cor_de_fundo(self):
        """Fundo tingido some em tela ruim, no sol e em `prefers-contrast`.

        A borda de marca é a segunda camada, e é ela que sustenta o destaque
        quando a primeira não aparece. Um destaque com uma camada só é um
        destaque que funciona no monitor de quem o desenhou.
        """
        for seletor in DONOS:
            with self.subTest(seletor=seletor):
                corpo = bloco(self.css, seletor)
                self.assertIn("border-color", corpo)
                self.assertIn("var(--brand)", corpo)

    def test_os_ramos_sem_hora_marcada_abrem_mao_do_foco(self):
        """Água, pesagem e "nada pendente" não são ação com hora que passa.

        Se os três também ficassem no verde, a tela diria "urgente" todo dia
        — e uma tela que grita sempre não grita nunca. Este teste guarda a
        regra de PRODUTO, não a cor: o foco é para o que a hora atrasa.
        """
        for ramo in (".agora-card--agua", ".agora-card--pesagem",
                     ".agora-card--vazio"):
            with self.subTest(ramo=ramo):
                self.assertIn(ramo, self.css)

        recuo = re.search(
            r"\.agora-card--agua,\s*\.agora-card--pesagem,\s*"
            r"\.agora-card--vazio\s*\{([^}]*)\}",
            self.css,
        )
        self.assertIsNotNone(
            recuo, "os três ramos deixaram de recuar o fundo de foco juntos"
        )
        self.assertIn("var(--surface)", recuo.group(1))
