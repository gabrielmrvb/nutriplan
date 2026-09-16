"""DESIGN.md: "Foco é `--brand` em todo controle." Havia dois idiomas — anel
azul `--agua` em cinco controles e um brilho difuso (`--glow`) nos campos — e
a água é cor de PILAR, não de estado. O `--glow` fica como nome (um teste de
`workouts/` lê a string) e muda de receita: anel de 1 px na cor da ação.

Os testes leem o CSS SEM comentários: a prosa do `app.css` fala de foco e de
água o tempo todo, e um regex que lesse os comentários acharia foco azul em
frase que explica por que ele saiu."""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

#: Controle positivo do regex de foco. Em 16/09/2026 o CSS tinha 17 regras
#: `:focus`/`:focus-visible`/`:focus-within`; um regex que não casasse nada
#: faria `test_nenhum_foco_e_azul` passar por acidente, e é isso que o piso
#: impede.
MINIMO_DE_REGRAS_DE_FOCO = 5


def _sem_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


class FocoUnicoTests(TestCase):
    def setUp(self):
        self.css = _sem_comentarios(CSS.read_text(encoding="utf-8"))

    def _regras_de_foco(self):
        return re.findall(r"([^{}]*:focus(?:-visible|-within)?[^{]*)\{([^}]*)\}", self.css)

    def test_nenhum_foco_e_azul(self):
        """Cinco controles — chips de dia, cartão de escolha, segmented, olho da
        senha e campo livre de água — pintavam o foco com `--agua`. A água é a
        cor do pilar Hidratação; o foco é a cor da AÇÃO, e a pessoa via os dois
        idiomas no mesmo formulário."""
        regras = self._regras_de_foco()
        self.assertGreaterEqual(
            len(regras), MINIMO_DE_REGRAS_DE_FOCO, "o regex de foco não achou o CSS"
        )
        azuis = [sel.strip() for sel, corpo in regras if "--agua" in corpo]
        self.assertEqual(azuis, [], f"foco com cor de pilar: {azuis}")

    def test_o_leitor_enxerga_um_foco_azul(self):
        """Controle positivo da DETECÇÃO, não só do regex: um CSS sintético com
        foco em `--agua` tem de ser flagrado. Sem isto, só a sabotagem manual
        provava que o teste de cima morde."""
        self.css = ".x:focus-visible { outline: 2px solid var(--agua) } .y:focus { color: var(--text) }"
        regras = self._regras_de_foco()
        azuis = [sel.strip() for sel, corpo in regras if "--agua" in corpo]
        self.assertEqual(azuis, [".x:focus-visible"])

    def test_o_glow_e_um_anel_sem_difusao(self):
        """O `--glow` era duas sombras: um anel de 18% mais uma difusão de 26 px.
        Somado à borda que já vira `--brand` no `:focus`, o anel de 1 px cheio
        dá os 2 px do DESIGN.md — e nada se espalha para fora do campo. Os dois
        gatilhos do Ferro continuam apontando para `--ferro-glow`."""
        declaracoes = [v.strip() for v in re.findall(r"^\s*--glow:\s*([^;]+);", self.css, re.M)]
        gatilhos = [v for v in declaracoes if v == "var(--ferro-glow)"]
        raizes = [v for v in declaracoes if v != "var(--ferro-glow)"]
        self.assertEqual(len(gatilhos), 2, f"os dois gatilhos do Ferro: {declaracoes}")
        self.assertEqual(len(raizes), 1, f"um `--glow` de Mesa no :root: {declaracoes}")
        ferro = re.search(r"^\s*--ferro-glow:\s*([^;]+);", self.css, re.M).group(1).strip()
        for valor in (raizes[0], ferro):
            with self.subTest(valor=valor):
                self.assertNotIn(",", valor, "duas sombras = difusão")
                self.assertRegex(valor, r"^0 0 0 1px var\(--(ferro-)?brand\)$")

    def test_o_campo_em_foco_continua_com_o_glow(self):
        """Anchor de `workouts/tests.py`: a string tem de continuar lá."""
        corpo = re.search(r"\.field-input:focus\s*\{([^}]*)\}", self.css).group(1)
        self.assertIn("var(--glow)", corpo)
        self.assertIn("border-color: var(--brand)", corpo)

    def test_o_campo_invalido_tem_regra(self):
        """O Django 5.2 escreve `aria-invalid="true"` no widget com erro, e até
        16/09/2026 nenhuma regra lia isso: a borda do campo errado era igual à
        do campo certo, e a pessoa achava o erro pela lista embaixo."""
        self.assertIn('.field-input[aria-invalid="true"]', self.css)
        corpo = re.search(r'\.field-input\[aria-invalid="true"\]\s*\{([^}]*)\}', self.css).group(1)
        self.assertIn("var(--danger)", corpo)

    def test_o_html_de_erro_escreve_aria_invalid(self):
        """Django 5.2 já escreve `aria-invalid="true"` no widget com erro; o teste
        prova que o parcial `field.html` não o perde no caminho. Os nomes são os
        do `AuthenticationForm` (`username`/`password`), não os do allauth."""
        resposta = self.client.post("/conta/entrar/", {"username": "nao-e-email", "password": ""})
        self.assertEqual(resposta.status_code, 200)
        # Na MESMA tag, classe e atributo: a regra CSS precisa da coincidência,
        # e `assertIn` solto passaria com a string dentro de um <script>.
        tags = re.findall(r"<input [^>]*>", resposta.content.decode())
        com_os_dois = [t for t in tags if 'class="field-input"' in t and 'aria-invalid="true"' in t]
        self.assertTrue(com_os_dois, "nenhum <input class=\"field-input\"> com aria-invalid na mesma tag")

    def test_o_que_o_campo_aponta_existe(self):
        """O Django escreve `aria-describedby="id_x_helptext id_x_error"` no
        widget; `partials/field.html` renderiza ajuda e erros por conta própria
        e, até 16/09/2026, sem os ids — o leitor de tela recebia a referência e
        não achava o alvo. Toda referência tem de ter alvo na página."""
        resposta = self.client.post("/conta/entrar/", {"username": "nao-e-email", "password": ""})
        html = resposta.content.decode()
        referencias = [i for grupo in re.findall(r'aria-describedby="([^"]+)"', html) for i in grupo.split()]
        self.assertTrue(referencias, "a página de erro não tem aria-describedby: o controle positivo sumiu")
        ids = set(re.findall(r'\sid="([^"]+)"', html))
        orfas = [r for r in referencias if r not in ids]
        self.assertEqual(orfas, [], f"aria-describedby sem alvo: {orfas}")
