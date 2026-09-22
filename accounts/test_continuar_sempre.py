"""O botão de continuar existe SEMPRE — e um `<div>` aberto num parcial é o
que o escondia.

Achado das três personas (achados/experiencia-usuario-20260921.md, #1, o
que perde mais gente): na etapa 2 com 0, 1 ou 2 dias de treino "Voltar" e
"CONTINUAR" não apareciam. Não era CSS: o `form-actions` estava DENTRO de
`div.revela[hidden]` (a pergunta da divisão, que só abre com 3 dias) porque
`partials/choice_cards.html` fechava o `<div role="group">` só dentro de
`{% if field.errors %}` — sem erro, o div ficava aberto e engolia tudo o
que vinha depois. Duas das três personas desistiam aqui; a persona que só
corre nem tem dia de musculação para marcar.

A régua aqui é a ÁRVORE, não a string: um parser que sabe que ancestral
está `hidden`. `assertIn("Continuar", html)` passava com o botão morto.
"""
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.test_tres_etapas import ETAPA1, ETAPA2, etapa

VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class BotoesEscondidos(HTMLParser):
    """Lista os `<button>` e os `<a class="btn">` que têm um ancestral `hidden`."""

    def __init__(self):
        super().__init__()
        self.pilha = []
        self.escondidos = []
        self.visiveis = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in VAZIOS:
            return
        self.pilha.append((tag, "hidden" in attrs))
        if tag == "button" or (tag == "a" and "btn" in (attrs.get("class") or "")):
            texto = attrs.get("class", "")
            (self.escondidos if any(h for _, h in self.pilha) else self.visiveis).append((tag, texto))

    def handle_endtag(self, tag):
        if tag in VAZIOS:
            return
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                del self.pilha[i:]
                break


def botoes_escondidos(html):
    p = BotoesEscondidos()
    p.feed(html)
    return p.escondidos, p.visiveis


class ContinuarSempreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="continuar@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)
        self.client.post(etapa(1), ETAPA1)

    def test_a_etapa_2_tem_continuar_visivel_com_zero_um_e_dois_dias(self):
        for dias in ([], ["0"], ["0", "3"]):
            with self.subTest(dias=dias):
                if dias:
                    self.client.post(etapa(2), {**ETAPA2, "weekdays": dias, "split_preference": ""})
                html = self.client.get(etapa(2)).content.decode()
                escondidos, visiveis = botoes_escondidos(html)
                # o convite de instalação nasce `hidden` de propósito; o que
                # não pode estar escondido é o botão do FORMULÁRIO.
                self.assertFalse(
                    [b for b in escondidos if "btn--primary" in b[1] and "install" not in b[1]],
                    "CONTINUAR está dentro de um ancestral hidden com %s dias" % len(dias),
                )
                self.assertTrue([b for b in visiveis if "btn--primary" in b[1]])

    def test_o_parcial_de_cartoes_fecha_o_que_abre(self):
        """A causa, presa na fonte: todo `<div` do parcial tem o seu `</div>`
        FORA de qualquer `{% if %}` — contando só a estrutura, sem os
        comentários do Django."""
        import re
        caminho = Path(settings.BASE_DIR) / "templates" / "partials" / "choice_cards.html"
        fonte = caminho.read_text(encoding="utf-8")
        fonte = re.sub(r"{% comment %}.*?{% endcomment %}", "", fonte, flags=re.S)
        abre = len(re.findall(r"<div\b", fonte))
        fecha = len(re.findall(r"</div>", fonte))
        self.assertEqual(abre, fecha)
        # e nenhum `</div>` mora dentro de um `{% if %}…{% endif %}` que abre
        # fora dele: o fechamento do grupo não pode depender de haver erro.
        for bloco in re.findall(r"{% if [^%]*%}(.*?){% endif %}", fonte, flags=re.S):
            self.assertEqual(len(re.findall(r"<div\b", bloco)), len(re.findall(r"</div>", bloco)), bloco[:80])

    def test_o_parcial_de_campo_tambem(self):
        import re
        for nome in ("field.html", "caixas_de_consentimento.html", "choice_list.html"):
            caminho = Path(settings.BASE_DIR) / "templates" / "partials" / nome
            if not caminho.exists():
                continue
            fonte = re.sub(r"{% comment %}.*?{% endcomment %}", "", caminho.read_text(encoding="utf-8"), flags=re.S)
            self.assertEqual(len(re.findall(r"<div\b", fonte)), len(re.findall(r"</div>", fonte)), nome)
