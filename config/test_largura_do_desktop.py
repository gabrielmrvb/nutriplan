# -*- coding: utf-8 -*-
"""A régua das DUAS pontas da largura do desktop.

Medido a 1280x900 em 24/09/2026, com o `<main>` de cada tela:

    Hoje, Alimentação, Progresso, Mais, Corridas ... 1024px (984 úteis)
    Treino, Hidratação, Conquistas, Lista de compras ... 480px (440 úteis)

Quatro telas — uma delas a aba Treino, uma das quatro da barra de baixo —
abriam como um celular no meio do monitor. A correção é a mesma linha que
`templates/workouts/corridas.html` ganhou no mesmo dia:
`{% block container_class %}largo{% endblock %}`.

E é por isso que este arquivo tem DUAS pontas. Uma régua que só cobrasse
"largo" nas quatro telas seria satisfeita pondo `largo` em toda página — e o
`CLAUDE.md` já escreveu por que isso é pior: "um formulário de 1.024px de
largura seria pior que a coluna estreita, e por isso entrar na lista é
decisão de cada tela". A segunda ponta é a lista FECHADA das telas que NÃO
são largas de propósito (entrada, cadastro, onboarding, consentimento, 403 e
404): se alguém alargar uma delas, esta régua fica vermelha.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from plans import services as plans_services
from plans.tests import create_complete_user

#: A raiz de `templates/`. Os testes de varredura deste projeto leem o disco
#: (é o que `config/test_csp.py` e `config/test_design_system.py` fazem):
#: o defeito que se quer impedir é alguém APAGAR a linha do template.
TEMPLATES = Path(settings.BASE_DIR) / "templates"

#: As quatro telas da correção de 24/09/2026, com a rota que as serve.
LARGAS = {
    "workouts/routine.html": "workouts:routine",
    "plans/hydration.html": "plans:hydration",
    "achievements/list.html": "achievements:list",
    "plans/shopping.html": "plans:shopping",
}

#: A LISTA FECHADA do que não é largo de propósito. Cada uma é um formulário
#: curto ou uma página de recado: esticá-la até 1.024px afasta o rótulo do
#: campo e faz a pessoa varrer a tela com os olhos para ler uma linha.
ESTREITAS = (
    "accounts/login.html",
    "accounts/signup.html",
    "accounts/onboarding/step.html",
    "accounts/consentimento.html",
    "accounts/conectar_google.html",
    "accounts/senha_pedir.html",
    "accounts/senha_enviado.html",
    "accounts/senha_nova.html",
    "accounts/senha_pronta.html",
    "socialaccount/authentication_error.html",
    "plans/landing.html",
    "pwa/offline.html",
    "403.html",
    "403_csrf.html",
    "404.html",
)

BLOCO = re.compile(
    r"{%\s*block\s+container_class\s*%}(.*?){%\s*endblock", re.DOTALL
)


def container_class_de(caminho):
    """O conteúdo do `{% block container_class %}` do template, ou None."""
    achado = BLOCO.search((TEMPLATES / caminho).read_text(encoding="utf-8"))
    return achado.group(1).strip() if achado else None


class AsQuatroTelasSaoLargasNoDesktopTests(TestCase):
    """As quatro telas presas em 480px declaram `largo`."""

    @classmethod
    def setUpTestData(cls):
        # As quatro telas só existem com catálogo: a de treino monta a ficha
        # na entrada (`sync_active_routine`) e a lista de compras sai do
        # cardápio. Sem os dois seeds a de treino responde 500, e um 500 não
        # mede largura nenhuma.
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def test_cada_uma_das_quatro_telas_declara_largo(self):
        for caminho in LARGAS:
            with self.subTest(template=caminho):
                declarado = container_class_de(caminho)
                self.assertIsNotNone(
                    declarado,
                    "%s não declara `{%% block container_class %%}`: no desktop "
                    "ela abre em 480px enquanto Hoje e Progresso usam 1024."
                    % caminho,
                )
                self.assertIn(
                    "largo",
                    declarado.split(),
                    "%s declara `%s`, sem `largo`." % (caminho, declarado),
                )

    def test_o_main_servido_carrega_a_classe(self):
        """A prova do lado do navegador: a classe chega ao `<main>`.

        Ler o template prova que a linha existe; só a resposta prova que a
        `base.html` ainda a usa. As duas pontas do mesmo defeito.
        """
        user = create_complete_user(email="larga@exemplo.com")
        plans_services.create_plan(user)
        self.client.force_login(user)
        for rota in LARGAS.values():
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(rota))
                self.assertEqual(resposta.status_code, 200, rota)
                self.assertRegex(
                    resposta.content.decode(),
                    r'<main class="container [^"]*\blargo\b',
                    "a resposta de %s não traz `largo` no `<main>`." % rota,
                )


class OQueNaoELargoContinuaEstreitoTests(TestCase):
    """A outra ponta: a régua não pode virar "todo mundo largo"."""

    def test_formulario_e_recado_nao_ganham_a_largura_do_desktop(self):
        for caminho in ESTREITAS:
            with self.subTest(template=caminho):
                declarado = container_class_de(caminho) or ""
                self.assertNotIn(
                    "largo",
                    declarado.split(),
                    "%s virou largo. Formulário curto e página de recado ficam "
                    "estreitos de propósito (CLAUDE.md, seção 28 do CSS): "
                    "1.024px de largura para um campo de e-mail é pior que a "
                    "coluna estreita." % caminho,
                )

    def test_a_lista_fechada_descreve_arquivos_que_existem(self):
        """Uma lista fechada que envelhece em silêncio não guarda nada.

        Template renomeado sem tocar aqui deixaria de ser vigiado, e o teste
        continuaria verde — foi assim que a régua de nomenclatura quase
        passou a medir uma tela que não existia mais.
        """
        for caminho in tuple(ESTREITAS) + tuple(LARGAS):
            with self.subTest(template=caminho):
                self.assertTrue(
                    (TEMPLATES / caminho).is_file(),
                    "%s não existe mais; atualize a lista." % caminho,
                )


#: `{% comment %}…{% endcomment %}` e `{# … #}` — este arquivo mede MARCAÇÃO,
#: e as duas telas desta correção EXPLICAM `split__main` em comentário para
#: dizer por que não o usam. Medir o comentário seria reprovar a explicação.
COMENTARIO = re.compile(
    r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}", re.DOTALL
)

#: `class="split__main …"` e `class="split__aside …"` de verdade — em
#: atributo, não em prosa. Serve para DECIDIR SE VALE ABRIR o arquivo; quem
#: julga parentesco é o parser abaixo.
FILHO_DO_SPLIT = re.compile(r"""class=["'][^"']*\bsplit__(main|aside)\b""")

#: Tag que não tem filho e por isso não empilha. Sem esta lista, um `<img>`
#: no meio do `.split` deixaria a pilha desalinhada para sempre.
VAZIAS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
          "meta", "param", "source", "track", "wbr", "use", "path", "circle",
          "rect", "line", "polyline", "polygon", "stop", "animate"}


class ProcuraSplitOrfao(HTMLParser):
    """Acha `split__main`/`split__aside` que não tem um `.split` ANCESTRAL.

    A primeira versão desta régua comparava por COOCORRÊNCIA — "tem
    `split__main` e tem `class="split"` no mesmo arquivo" —, e a revisão
    adversarial desta missão mostrou os dois furos: uma tela com dois blocos
    independentes (um `.split` de verdade e um `split__main` esquecido fora
    dele) passava verde, e um pai escrito `class="algo split"` reprovava,
    porque o regex exigia `split` como PRIMEIRO nome. Aqui a pergunta é a do
    DOM: existe um ancestral aberto com a classe `split`?
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha = []
        self.orfaos = []

    def _classes(self, attrs):
        return set((dict(attrs).get("class") or "").split())

    def handle_starttag(self, tag, attrs):
        classes = self._classes(attrs)
        filhas = classes & {"split__main", "split__aside"}
        if filhas and not any("split" in ancestral for ancestral in self.pilha):
            self.orfaos.append(sorted(filhas)[0])
        if tag not in VAZIAS:
            self.pilha.append(classes)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VAZIAS and self.pilha:
            self.pilha.pop()

    def handle_endtag(self, tag):
        if tag not in VAZIAS and self.pilha:
            self.pilha.pop()


def orfaos_de(marcacao):
    """As classes de `.split` sem `.split` em volta, na ordem em que aparecem."""
    procura = ProcuraSplitOrfao()
    procura.feed(marcacao)
    return procura.orfaos


class SplitMainSemSplitEhClasseOrfaTests(TestCase):
    """`split__main` fora de um `.split` é classe que promete o que não tem.

    Achado desta própria missão, e por isso ele tem régua: ao tirar o
    `<div class="split">` do painel do Treino eu deixei o `split__main` no
    filho. A classe não é decoração — `.split__main` é `display: flex` com
    `gap: var(--gap)`, e somada ao `.card + .card` dos cartões ela dobra o
    espaço entre eles NO CELULAR (16px -> 32, medido a 390px em 24/09/2026).
    O desktop parecia certo, porque lá a grade vem de outro seletor; quem
    pagava era o telefone, que é onde o app é usado.
    """

    def test_todo_split_main_tem_um_split_em_volta(self):
        for caminho in sorted(TEMPLATES.rglob("*.html")):
            marcacao = COMENTARIO.sub("", caminho.read_text(encoding="utf-8"))
            if not FILHO_DO_SPLIT.search(marcacao):
                continue
            with self.subTest(template=str(caminho.relative_to(TEMPLATES))):
                self.assertEqual(
                    orfaos_de(marcacao), [],
                    "%s usa `split__main`/`split__aside` sem um `.split` "
                    "ancestral: sem o pai, a classe só traz o flex e o `gap` "
                    "extra do celular." % caminho.relative_to(TEMPLATES),
                )

    def test_a_regua_enxerga_a_marcacao_e_nao_a_prosa(self):
        """Controle positivo, e o contrapeso: um template que só CITA a classe
        num comentário não é achado, e um que a USA sem pai é."""
        self.assertTrue(FILHO_DO_SPLIT.search('<div class="split__main stack">'))
        self.assertFalse(FILHO_DO_SPLIT.search("E é `.stack`, não `.split__main`:"))
        self.assertEqual(COMENTARIO.sub("", '{% comment %}x{% endcomment %}a'), "a")

    def test_a_regua_julga_PARENTESCO_e_nao_coocorrencia(self):
        """Os quatro casos que a revisão adversarial desta missão cobrou.

        O terceiro é o que a versão por coocorrência deixava passar, e o
        quarto é o que ela reprovava sem motivo."""
        self.assertEqual(orfaos_de('<div class="split"><div class="split__main">x</div></div>'), [])
        self.assertEqual(orfaos_de('<div class="split__main">x</div>'), ["split__main"])
        self.assertEqual(
            orfaos_de('<div class="split"><div class="split__main">a</div></div>'
                      '<div class="split__aside">b</div>'),
            ["split__aside"],
            "o `.split` de outro bloco não vale de pai",
        )
        self.assertEqual(
            orfaos_de('<div class="ficha-layout split"><div class="split__main">x</div></div>'),
            [],
            "`split` fora da primeira posição continua sendo pai",
        )
        self.assertEqual(
            orfaos_de('<div class="split"><img src="x"><div class="split__main">x</div></div>'),
            [],
            "tag vazia não pode desalinhar a pilha",
        )
