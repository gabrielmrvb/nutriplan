"""O toque dado enquanto a tela ainda está entrando não se perde.

Item 7 da missão de UX (22/09/2026): "botões às vezes não respondem ao
primeiro toque". MEDIDO no Chrome 153 (`scratchpad/ux/r7_medir_vt.py`):
durante a view transition entre páginas (`@view-transition { navigation:
auto }`, `--mov-tela` .2s) o `elementFromPoint` devolve `<html>` por
280–320 ms depois de o documento novo começar — o clique é despachado no
`<html>` e a página não faz nada. `pointer-events: none` na árvore de
pseudo-elementos NÃO muda isso (medido). Num celular lento a janela é
maior, e é exatamente quando a pessoa já sabe onde vai tocar.

A resposta é REPETIR o toque quando a transição termina: `pwa.js` ("TOQUE
DURANTE A TRANSIÇÃO") escuta `pagereveal`, guarda o clique que caiu no
`<html>` enquanto `viewTransition.finished` não resolveu, e o entrega ao
elemento que está naquele ponto depois. Sem transição (movimento
reduzido, navegador sem suporte) não há `viewTransition` e nada acontece.
"""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ToqueDuranteATransicaoTests(SimpleTestCase):
    def setUp(self):
        self.js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(encoding="utf-8")

    def test_o_pwa_repete_o_toque_que_caiu_na_transicao(self):
        partes = self.js.split("TOQUE DURANTE A TRANSIÇÃO", 1)
        self.assertEqual(len(partes), 2, "pwa.js sem o bloco")
        bloco = partes[1][:3500]
        self.assertIn('"pagereveal"', bloco)
        self.assertIn("viewTransition", bloco)
        self.assertIn(".finished", bloco)
        self.assertIn("elementFromPoint", bloco)
        self.assertIn(".click()", bloco)
        # só o clique que caiu no documento — um clique que chegou a um botão
        # de verdade já fez o que tinha de fazer
        self.assertIn("documentElement", bloco)

    def test_a_transicao_continua_curta(self):
        """A janela morta é a duração da transição; ela não pode crescer sem
        alguém ler isto. `.2s` é o token, e a régua de `config/test_movimento`
        proíbe duração fora dele."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("--mov-tela: .2s", css)
