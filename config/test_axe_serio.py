# -*- coding: utf-8 -*-
"""As duas violações `serious` que o axe-core achou na auditoria de 20/09/2026.

Rodado em produção (`dc971a0`) e no servidor local logado, 37 rotas, com o
`agent-browser a11y` (axe 4.12): tudo limpo, menos DUAS regras — e as duas
vinham de parciais, então repetiam em toda tela que os usava.

1. `listitem` — "`<li>` elements must be contained in a `<ul>` or `<ol>`":
   `partials/field.html` e `partials/choice_cards.html` escreviam
   `<ul role="group">`. O `role` troca a semântica da lista pela de grupo, e
   os `<li>` ficam órfãos para a árvore de acessibilidade — 24 nós na etapa 2
   do onboarding, 17 na etapa 3, 2 na etapa 1, 4 na corrida manual. O leitor
   de tela perde "item 1 de 4"; o grupo fica.
2. `nested-interactive` — "Interactive controls must not be nested": o
   `<summary>` de "Dados do cálculo" (`plans/today.html`) carregava um
   `<a>Editar</a>`. O `summary` já é o controle que abre; um link dentro dele
   é dois alvos num só toque, e o teclado não chega ao segundo.

A régua aqui é estrutural, sobre o HTML RENDERIZADO (não o template): todo
`<li>` tem um `<ul>`/`<ol>` como pai, e esse pai não muda de papel; nenhum
`<a>`/`<button>`/`<input>` mora dentro de `<summary>`.
"""
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from plans.tests import create_complete_user


class _Arvore(HTMLParser):
    """Um parser pequeno: pilha de elementos abertos e as duas listas que a
    régua precisa — `li` órfãos e controles dentro de `summary`."""

    VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    CONTROLES = {"a", "button", "input", "select", "textarea"}

    def __init__(self):
        super().__init__()
        self.pilha = []
        self.li_orfaos = []
        self.dentro_de_summary = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li":
            pai = self.pilha[-1] if self.pilha else None
            papel = (pai[1].get("role") or "").strip() if pai else ""
            if not pai or pai[0] not in ("ul", "ol", "menu") or papel not in ("", "list"):
                self.li_orfaos.append("li dentro de <%s%s>" % (pai[0] if pai else "nada", ' role="%s"' % papel if papel else ""))
        if tag in self.CONTROLES and any(t == "summary" for t, _ in self.pilha):
            self.dentro_de_summary.append("<%s %s>" % (tag, " ".join("%s=%r" % kv for kv in attrs.items() if kv[0] in ("href", "class", "type"))))
        if tag not in self.VAZIOS:
            self.pilha.append((tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                del self.pilha[i:]
                break


def _arvore(html):
    p = _Arvore()
    p.feed(html)
    return p


class NenhumLiOrfaoTests(TestCase):
    def _html(self, rota, metodo="get", dados=None):
        r = getattr(self.client, metodo)(rota, dados or {})
        self.assertEqual(r.status_code, 200, rota)
        return r.content.decode()

    def test_as_listas_de_escolha_do_onboarding_sao_listas_de_verdade(self):
        """Etapas 1, 2 e 3: os rádios em `.choice-list`/`.choice-cards` têm
        um `<ul>` sem `role` como pai; o grupo (rótulo, ajuda, erro) mora
        num elemento que envolve a lista."""
        user = create_complete_user()
        self.client.force_login(user)
        for etapa in (1, 2, 3):
            html = self._html(reverse("accounts:onboarding_step", kwargs={"step": etapa}))
            arvore = _arvore(html)
            self.assertIn("<li", html, "a etapa %d tem lista de escolha" % etapa)  # controle positivo
            self.assertEqual(arvore.li_orfaos, [], "etapa %d" % etapa)

    def test_a_corrida_manual_tambem(self):
        """`sensacao` é um rádio pelo mesmo parcial."""
        user = create_complete_user()
        self.client.force_login(user)
        html = self._html(reverse("workouts:corrida_nova"))
        self.assertIn("<li", html)
        self.assertEqual(_arvore(html).li_orfaos, [])

    def test_o_grupo_continua_rotulado(self):
        """Tirar o `role` da lista não pode tirar o grupo: rótulo e descrição
        continuam num `role="group"` que ENVOLVE a lista de escolha."""
        user = create_complete_user()
        self.client.force_login(user)
        html = self.client.post(reverse("accounts:onboarding_step", kwargs={"step": 2}), {}).content.decode()
        self.assertIn("Este campo é obrigatório", html)
        self.assertRegex(html, r'role="group"[^>]*aria-labelledby="id_goal_label"[^>]*aria-describedby="[^"]*id_goal_error"')
        self.assertRegex(html, r'role="group"[^>]*aria-labelledby="id_goal_label"[^>]*>\s*<ul class="choice-')


class NenhumControleDentroDeSummaryTests(TestCase):
    def test_a_alimentacao_nao_tem_link_dentro_de_summary(self):
        """"Dados do cálculo" tinha `<a>Editar</a>` no `<summary>`.

        O bloco mora na tela de Alimentação desde 22/09/2026 — a Hoje virou o
        orquestrador do dia e não explica mais o cálculo da meta.
        """
        user = create_complete_user()
        self.client.force_login(user)
        r = self.client.get(reverse("plans:alimentacao"))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("Dados do cálculo", html)  # controle positivo: o bloco está na tela
        arvore = _arvore(html)
        self.assertEqual(arvore.dentro_de_summary, [])
        # e o caminho para editar continua existindo, fora do summary
        self.assertIn(reverse("accounts:profile"), html)

    def test_o_parser_ve_o_que_procura(self):
        """Controle positivo do parser: um `<li>` órfão e um link no summary
        são achados quando existem."""
        arvore = _arvore('<div role="group"><ul role="group"><li>a</li></ul></div><details><summary><a href="/x">e</a></summary></details><ul><li>ok</li></ul>')
        self.assertEqual(len(arvore.li_orfaos), 1)
        self.assertEqual(len(arvore.dentro_de_summary), 1)
