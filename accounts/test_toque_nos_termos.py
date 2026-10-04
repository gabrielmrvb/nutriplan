# -*- coding: utf-8 -*-
"""Tocar no cartão "Li e aceito os Termos" marca a caixa — os links são alvos
PRÓPRIOS, fora do cartão.

O caso real (28/09/2026): o lote noturno (#196) reprovou em `cadastro` com
"não consegui marcar input[name=termos]" e o snapshot parado em `/termos/`. Os
links "Termos de Uso" e "Política de Privacidade" moravam DENTRO do
`<label class="choice-card">`, com 12 px de preenchimento vertical cada (o alvo
de 44 px do link) — e esse preenchimento cobria o cartão. Medido com
`elementFromPoint` numa grade sobre o cartão, a 390 px: 28% da área do cartão
era link e só 72% marcava a caixa; a 290 px o CENTRO do cartão era link. O E2E
foi contornado com `e.click()` no `<input>` (#198), mas a pessoa real tocando
no meio do cartão sofria o mesmo: abria outra aba em vez de marcar.

Princípio: o cartão inteiro é o alvo da caixa (é o desenho da `choice-card`),
e cada link é um alvo de 44 x 44 px que NÃO invade o cartão.

Os textos de consentimento são texto jurídico aprovado: aqui só mudou ONDE os
links moram. `test_as_palavras_do_aceite_sao_as_de_antes` pina as palavras.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.test_consentimento import CONTA
from accounts.test_tres_etapas import ETAPA1_SEM_CAIXAS, etapa

RAIZ = Path(__file__).resolve().parent.parent

#: Tudo o que a pessoa lia no `<li>` do aceite em main (2231263): o rótulo, e
#: logo depois os dois links com o "·". Não é copiado do código — é o texto
#: aprovado, e é por isso que está escrito aqui.
TEXTO_DO_ACEITE = (
    "Li e aceito os Termos de Uso e a Política de Privacidade. "
    "Termos de Uso · Política de Privacidade"
)
ROTULO = "Li e aceito os Termos de Uso e a Política de Privacidade."


class No:
    def __init__(self, tag, attrs, pai):
        self.tag, self.attrs, self.pai, self.filhos = tag, attrs, pai, []

    def ancestral(self, tag):
        no = self.pai
        while no is not None:
            if no.tag == tag:
                return no
            no = no.pai
        return None

    def todos(self, tag):
        for filho in self.filhos:
            if isinstance(filho, No):
                if filho.tag == tag:
                    yield filho
                yield from filho.todos(tag)

    def texto(self):
        pedacos = []
        for filho in self.filhos:
            if isinstance(filho, No):
                if filho.tag not in ("script", "style") and filho.attrs.get("aria-hidden") != "true":
                    pedacos.append(filho.texto())
            else:
                pedacos.append(filho)
        return re.sub(r"\s+", " ", " ".join(pedacos)).strip()


class Arvore(HTMLParser):
    """O mínimo de árvore para perguntar "este link mora dentro daquele label?".

    Regex sobre HTML responde "a string aparece"; a pergunta aqui é de
    aninhamento, e `<input>` e `<path/>` não fecham.
    """

    VAZIAS = {"input", "br", "hr", "img", "meta", "link"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.raiz = self.atual = No("#raiz", {}, None)
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        no = No(tag, dict(attrs), self.atual)
        self.atual.filhos.append(no)
        if tag not in self.VAZIAS:
            self.atual = no

    def handle_startendtag(self, tag, attrs):
        self.atual.filhos.append(No(tag, dict(attrs), self.atual))

    def handle_endtag(self, tag):
        no = self.atual
        while no.pai is not None and no.tag != tag:
            no = no.pai
        if no.pai is not None:
            self.atual = no.pai

    def handle_data(self, dado):
        self.atual.filhos.append(dado)


def cartao_dos_termos(html):
    """(label, li) do aceite dos Termos — o `<li>` é "a mesma tela" do cartão."""
    caixa = next(
        c for c in Arvore(html).raiz.todos("input") if c.attrs.get("name") == "termos"
    )
    return caixa.ancestral("label"), caixa.ancestral("li")


def telas(teste):
    """As três telas que desenham o aceite: o cadastro (à mão, em
    `signup.html`) e a etapa 1 e a tela de consentimento (as duas pelo parcial
    `caixas_de_consentimento.html`). Quem quebra uma e esquece a outra é
    exatamente o que este teste cobra."""
    cadastro = teste.client.get(reverse("accounts:signup")).content.decode()
    user = User.objects.create_user(email="toque@exemplo.com", password="senha-bem-forte-123")
    teste.client.force_login(user)
    return {
        "cadastro": cadastro,
        "etapa 1": teste.client.get(etapa(1)).content.decode(),
        "consentimento": teste.client.get(reverse("accounts:consentimento")).content.decode(),
    }


def telas_com_erro(teste):
    """As mesmas três telas, devolvidas COM o erro "marque esta caixa": o
    cadastro postado sem `termos`, a etapa 1 e a tela de consentimento postadas
    sem nenhuma caixa. A ordem das telas importa: com a pessoa logada o cadastro
    redireciona, então ele vem primeiro."""
    cadastro = teste.client.post(reverse("accounts:signup"), CONTA)
    user = User.objects.create_user(email="toque-erro@exemplo.com", password="senha-bem-forte-123")
    teste.client.force_login(user)
    return {
        "cadastro": cadastro.content.decode(),
        "etapa 1": teste.client.post(etapa(1), ETAPA1_SEM_CAIXAS).content.decode(),
        "consentimento": teste.client.post(reverse("accounts:consentimento"), {}).content.decode(),
    }


class ToqueNosTermosTests(TestCase):
    def test_os_links_nao_moram_dentro_do_cartao_que_marca_a_caixa(self):
        """O defeito em uma frase: link dentro do `<label>` rouba o toque.
        O controle positivo está no teste seguinte — o link existe, só não
        está dentro."""
        for tela, html in telas(self).items():
            label, _ = cartao_dos_termos(html)
            with self.subTest(tela=tela):
                self.assertIn("choice-card", label.attrs.get("class", ""))
                self.assertEqual(
                    [a.attrs.get("href") for a in label.todos("a")], [],
                    "link dentro do label: o toque no cartão abre a página em vez de marcar",
                )

    def test_os_links_continuam_na_mesma_tela_logo_abaixo_do_cartao(self):
        """Controle positivo do anterior: tirar o link do label NÃO é tirar o
        link da tela. Ficam no mesmo `<li>`, depois do cartão, e abrem em outra
        aba — voltar ao formulário não pode custar o que já foi digitado."""
        for tela, html in telas(self).items():
            label, li = cartao_dos_termos(html)
            with self.subTest(tela=tela):
                links = list(li.todos("a"))
                self.assertEqual(
                    [(a.attrs.get("href"), a.attrs.get("target"), a.attrs.get("rel")) for a in links],
                    [
                        (reverse("termos"), "_blank", "noopener"),
                        (reverse("privacidade"), "_blank", "noopener"),
                    ],
                )
                depois_do_label = li.filhos[li.filhos.index(label) + 1:]
                self.assertTrue(
                    any(isinstance(f, No) and list(f.todos("a")) for f in depois_do_label),
                    "os links têm de vir depois do cartão, no mesmo <li>",
                )

    def test_no_erro_a_mensagem_fica_colada_ao_cartao_e_os_links_vem_depois(self):
        """Postado sem a caixa, o `<li>` tem de ser, em ordem: o cartão, o erro
        e a faixa de links. Sem erro a ordem é a mesma de qualquer posição da
        faixa — se alguém a puser ENTRE o cartão e o erro, todo teste de GET
        continua verde e a mensagem "marque esta caixa" se descola do cartão a
        que ela se refere (só se via no navegador). O `id` do erro é o
        `aria-describedby` da caixa: o leitor de tela anuncia o erro DELA."""
        for tela, html in telas_com_erro(self).items():
            label, li = cartao_dos_termos(html)
            caixa = next(c for c in label.todos("input") if c.attrs.get("name") == "termos")
            filhos = [f for f in li.filhos if isinstance(f, No)]
            with self.subTest(tela=tela):
                self.assertEqual(
                    [(f.tag, f.attrs.get("class")) for f in filhos],
                    [("label", "choice-card"), ("ul", "field__errors"), ("span", "consentimento__links")],
                )
                self.assertEqual(filhos[1].attrs.get("id"), caixa.attrs.get("aria-describedby"))
                self.assertEqual(caixa.attrs.get("aria-invalid"), "true")

    def test_as_palavras_do_aceite_sao_as_de_antes(self):
        """Texto jurídico aprovado: o rótulo e os dois links dizem, na mesma
        ordem, exatamente o que diziam em main. Só mudou onde os links moram."""
        for tela, html in telas(self).items():
            label, li = cartao_dos_termos(html)
            with self.subTest(tela=tela):
                self.assertEqual(label.texto(), ROTULO)
                self.assertEqual(li.texto(), TEXTO_DO_ACEITE)

    def test_o_link_tem_44_por_44_e_nao_invade_o_cartao(self):
        """A régua do projeto mede altura E largura (`CLAUDE.md`: 26 px de
        largura com 44 de altura já passou despercebido uma vez). Preenchimento
        com margem negativa — o jeito antigo — é o que fazia o link cobrir o
        cartão; o alvo agora vem de `min-height`/`min-width`, sem sair da
        própria caixa."""
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        ancora = "\n.consentimento__links a {"
        self.assertIn(ancora, css, "a regra do link dos Termos sumiu")
        bloco = css.split(ancora)[1].split("}", 1)[0]
        with self.subTest("altura"):
            self.assertIn("min-height: 2.75rem", bloco)
        with self.subTest("largura"):
            self.assertIn("min-width: 2.75rem", bloco)
        with self.subTest("sem margem negativa"):
            self.assertNotIn("calc(-1", bloco)

    def test_o_cartao_nao_estica_por_cima_da_faixa_dos_links(self):
        """Achado no navegador, invisível no HTML: `.choice-card` tem
        `height: 100%`, e com a faixa de links depois dele no mesmo `<li>` o
        cartão passava a ocupar a altura do `<li>` INTEIRO — cartão e faixa
        somados — empurrando os links 160 px para baixo, para fora da caixa.
        `height: auto` no cartão do aceite desfaz o círculo."""
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        ancora = "\n.consentimento .choice-card {"
        self.assertIn(ancora, css, "sem a regra, o cartão come a faixa dos links")
        self.assertIn("height: auto", css.split(ancora)[1].split("}", 1)[0])
