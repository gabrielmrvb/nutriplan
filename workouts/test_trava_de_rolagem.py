"""TREINO — a rolagem volta no MESMO instante em que a gaveta fecha.

O DEFEITO, medido em PRODUÇÃO em 09/09/2026, na ficha do demo. Depois do toque
no ✕, o evento `close` do `<dialog>` levou **2.100 ms** para disparar. Nesses
dois segundos o vídeo já tinha sumido — `limparMidia` é chamada direto por
`fecharDrawer`, síncrona —, mas `html.drawer-aberto` continuava lá, e essa
classe é `overflow: hidden`. A pessoa fecha o vídeo e a página não rola.

O atraso não é do nosso código: tirar o `<iframe>` do YouTube do documento
derruba o player, e esse trabalho segura a thread principal; a tarefa do
`close`, que é enfileirada, espera atrás dele. Localmente, com o clipe em
cache, o intervalo é curto o bastante para ninguém ver — foi preciso medir com
a rede de verdade.

É a MESMA lição que a limpeza da mídia já tinha aprendido, e está escrita no
`_drawer.html`: depender de um evento só é o que produziu o defeito. Agora o
destravamento acontece nos dois lugares — na hora, dentro de `fecharDrawer`, e
no `cancel`/`close`, que continuam sendo a rede para quem sai pelo Esc ou fecha
o diálogo de fora.

POR QUE ESTE TESTE LÊ O ARQUIVO. O comportamento é do navegador, e teste de
servidor não tem `<dialog>` nem thread bloqueada. O que dá para prender aqui é
a ESTRUTURA que o comportamento exige: que o caminho síncrono destrave, e que o
evento continue destravando. A prova de que funciona é a medição em produção,
repetida depois da correção e escrita no relatório da campanha.
"""
from django.test import TestCase

from push.test_cache_privado import sem_comentarios


def _fonte():
    from pathlib import Path

    caminho = (
        Path(__file__).resolve().parent.parent
        / "templates" / "workouts" / "_drawer.html"
    )
    return caminho.read_text(encoding="utf-8")


def corpo_da_funcao(fonte, nome):
    """O corpo de uma função, do `{` até a chave que o fecha.

    Contar chaves e não usar regex: o corpo tem `if` e objeto literal dentro, e
    um `.*?}` casaria a primeira chave interna — devolvendo um pedaço, e um
    teste sobre um pedaço não prova nada sobre o resto. É o mesmo ajudante de
    `workouts/test_corrida_v1.py`.
    """
    inicio = fonte.index("function %s(" % nome)
    abre = fonte.index("{", inicio)
    nivel = 0
    for i in range(abre, len(fonte)):
        if fonte[i] == "{":
            nivel += 1
        elif fonte[i] == "}":
            nivel -= 1
            if nivel == 0:
                return fonte[abre : i + 1]
    raise AssertionError("função %s não fecha" % nome)


class ATravaDeRolagemCaiNoCaminhoSincronoTests(TestCase):
    """SEM COMENTÁRIO NA LEITURA, e isto não é zelo: o comentário que explica
    esta correção cita `destravarRolagem` e `drawer-aberto` por extenso, três
    vezes. Uma asserção ingênua passaria lendo a prosa que descreve o conserto
    mesmo com o conserto apagado — a armadilha que o `CLAUDE.md` nomeia."""

    @classmethod
    def setUpTestData(cls):
        cls.js = sem_comentarios(_fonte())

    def test_fechar_o_drawer_destrava_a_rolagem_na_hora(self):
        corpo = corpo_da_funcao(self.js, "fecharDrawer")

        self.assertIn("destravarRolagem()", corpo)
        self.assertIn("limparMidia()", corpo)

    def test_o_extrator_pega_o_corpo_inteiro(self):
        """Controle positivo: um extrator que devolvesse `{}` faria o teste
        acima falhar, mas um que devolvesse o arquivo TODO o faria passar por
        acidente — inclusive com `fecharDrawer` vazia."""
        corpo = corpo_da_funcao(self.js, "fecharDrawer")

        self.assertLess(len(corpo), 400, corpo)
        self.assertNotIn("function preencher", corpo)

    def test_o_evento_continua_sendo_a_rede(self):
        """O Esc não passa por `fecharDrawer`: o navegador fecha sozinho.

        Sem estas duas linhas, sair pelo teclado deixaria a página travada
        para sempre — que é o defeito que o `close` foi posto para cobrir.
        """
        self.assertIn('addEventListener("cancel", destravarRolagem)', self.js)
        self.assertIn('addEventListener("close", destravarRolagem)', self.js)

    def test_quem_destrava_e_quem_trava_falam_da_mesma_classe(self):
        """`drawer-aberto` escrito à mão nos dois lados é o defeito clássico:
        travar com um nome e destravar com outro passa em qualquer teste que
        olhe só um lado."""
        self.assertIn('classList.add("drawer-aberto")', self.js)

        corpo = corpo_da_funcao(self.js, "destravarRolagem")
        self.assertIn('classList.remove("drawer-aberto")', corpo)

    def test_a_classe_existe_no_css_e_e_ela_que_segura_a_pagina(self):
        """Sem a regra, todo o resto é cerimônia sobre uma classe inerte."""
        from pathlib import Path

        css = (
            Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
        ).read_text(encoding="utf-8")

        self.assertIn("html.drawer-aberto { overflow: hidden; }", css)
