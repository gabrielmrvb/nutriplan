"""O TREINO ENTRA NO CÂNONE DO SISTEMA VISUAL (pente-fino de qualidade, resíduo
da onda 2, 04/10/2026).

A dívida de sistema visual (28/09) parou na porta de `templates/workouts/`,
que a Parte 2 segurava. Medido na tela do Treino de hoje, a 390: 23 de 57
textos fora da escala `--texto-*` — quinze a 12,2 px (`.76rem`, a linha de
cada cartão de sessão e o resumo do programa), dois a 11,5 px (`.72rem`, as
etiquetas do bloco de hoje), dois `h2` a 20,8 px (o legado) e o nome da
sessão a 22,7 px (`1.42rem`) —, mais o "%" do anel em display a 14,4 px e o
"COMEÇAR TREINO" em display a 16 px (`btn--hoje` encolhia o primário). A
display nunca desce de 20 px (`DESIGN.md`).
"""
import re

from django.test import SimpleTestCase

from config.test_design_system import CSS, sem_comentarios
from config.test_nervura import _regra


class OTreinoNaEscalaTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_as_linhas_de_apoio_do_treino_usam_token(self):
        for seletor in (".session__meta", ".programa__resumo", ".hoje__etiqueta",
                        ".hoje__proximo-rotulo", ".hoje__nome"):
            with self.subTest(seletor=seletor):
                corpo = _regra(self.css, seletor, contendo="font-size")
                self.assertIsNotNone(corpo, seletor)
                self.assertRegex(corpo, r"font-size:\s*var\(--texto-")

    def test_o_primario_de_hoje_e_o_primario_de_sempre(self):
        corpo = _regra(self.css, ".btn--hoje") or ""
        self.assertNotIn("font-size", corpo)

    def test_o_sinal_de_porcento_do_anel_nao_e_display(self):
        self.assertRegex(_regra(self.css, ".ring__pc") or "", r"font-family:\s*var\(--font\)")

    def test_controle_a_regra_le_o_tamanho_cru(self):
        self.assertIsNone(re.search(r"font-size:\s*var\(--texto-", ".x { font-size: .76rem; }"))
