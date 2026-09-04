# -*- coding: utf-8 -*-
"""As telas novas do B7 não têm rede contra alvo pequeno.

`TouchTargetTests` trava as REGRAS de CSS: `.btn` tem `min-height: 2.95rem`,
`.btn-link` tem 2.75rem, e assim por diante. O que ele não sabe é se uma tela
usa essas classes — CSS certo não ajuda um `<button>` que não tem classe
nenhuma.

O buraco foi medido antes de este arquivo existir, sabotando primeiro: trocando
`class="btn btn--perigo btn--block"` por `class="link-desvincular"` no botão de
desvincular, os 13 testes das telas novas continuaram **verdes**. O alvo cairia
de 47px para a altura do texto e ninguém saberia.

No navegador, a 375px, os controles dessas duas telas medem hoje:

  "Tentar de novo"                297x47
  "Desvincular a conta escolhida" 294x47
  "Conectar uma conta Google"     294x47
  "Voltar ao perfil"              294x47
  o rótulo de cada conta          294x50

A medida de verdade continua sendo o navegador — como diz o próprio
`TouchTargetTests`. Isto aqui é a rede para quando ninguém estiver medindo.
"""
import re

from django.test import SimpleTestCase

from config.settings import BASE_DIR

TELAS = {
    "socialaccount/authentication_error.html": "quem falha no handshake do Google",
    "socialaccount/connections.html": "quem vê e desvincula as contas conectadas",
}

#: Classes que carregam altura própria, com a regra que as sustenta. Cada uma
#: está travada em `TouchTargetTests`, e é de lá que vem o número.
CLASSES_COM_ALTURA = ("btn", "btn-link", "choice-list")


def sem_comentarios(texto):
    """O template sem `{% comment %}` e sem `<!-- -->`.

    Este projeto comenta muito, e os dois templates em questão explicam por que
    existem — citando `btn--perigo` e `choice-list` na prosa. Uma asserção que
    procurasse essas palavras no arquivo inteiro passaria verde com o botão
    apagado. É a armadilha que o `CLAUDE.md` descreve, e ela já custou caro
    três vezes nesta base.
    """
    sem_django = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", texto, flags=re.S)
    return re.sub(r"<!--.*?-->", "", sem_django, flags=re.S)


def controles(corpo):
    """Cada `<button>` e cada `<a href>` do template, com as classes dele."""
    for tag in re.finditer(r"<(button|a)\b([^>]*)>", corpo, re.S):
        atributos = tag.group(2)
        if tag.group(1) == "a" and "href" not in atributos:
            continue
        classe = re.search(r'class="([^"]*)"', atributos)
        yield tag.group(0)[:70], (classe.group(1).split() if classe else [])


class TodoControleDasTelasNovasTemAlturaTests(SimpleTestCase):
    """Cada controle carrega uma classe que garante os 44px."""

    def test_nenhum_controle_fica_sem_classe_de_altura(self):
        nus = []
        for caminho in TELAS:
            corpo = sem_comentarios(
                (BASE_DIR / "templates" / caminho).read_text(encoding="utf-8")
            )
            for tag, classes in controles(corpo):
                if not any(c.split("--")[0] in CLASSES_COM_ALTURA for c in classes):
                    nus.append("%s: %s" % (caminho, tag))

        self.assertEqual(nus, [])

    def test_a_lista_de_contas_usa_o_componente_que_tem_altura(self):
        """O rádio tem 19x19. Quem recebe o dedo é o RÓTULO, que o
        `.choice-list` faz medir 294x50 — provado no navegador clicando a 8px
        da borda direita, longe do rádio.

        Sem `.choice-list`, o rótulo encolhe para a altura do texto e o alvo
        real vira o rádio de 19px."""
        corpo = sem_comentarios(
            (BASE_DIR / "templates" / "socialaccount" / "connections.html").read_text(
                encoding="utf-8"
            )
        )

        # A `<ul>` que CONTÉM o rádio, e não a primeira da página: a de erros
        # vem antes, e casar com ela fazia o teste falhar por motivo errado.
        listas = [
            achado.group(1)
            for achado in re.finditer(r'<ul class="([^"]*)">(.*?)</ul>', corpo, re.S)
            if 'type="radio"' in achado.group(2)
        ]

        self.assertEqual(len(listas), 1, "sumiu a lista de contas conectadas")
        self.assertIn("choice-list", listas[0])

    def test_a_varredura_olha_para_alguma_coisa(self):
        """Controle positivo. Um regex que não casasse com nada passaria verde
        para sempre, e é o jeito mais fácil de este arquivo virar decoração."""
        total = 0
        for caminho in TELAS:
            corpo = sem_comentarios(
                (BASE_DIR / "templates" / caminho).read_text(encoding="utf-8")
            )
            total += len(list(controles(corpo)))

        self.assertGreaterEqual(total, 4)

    def test_as_telas_da_lista_existem(self):
        """Um caminho que não existe mais faria a varredura acima passar sem
        cobrir nada."""
        for caminho in TELAS:
            with self.subTest(tela=caminho):
                self.assertTrue((BASE_DIR / "templates" / caminho).exists())
