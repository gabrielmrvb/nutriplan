"""O sprite (17 símbolos, ~3,7 kB brutos) passa a viver no `base.html`, uma vez por
página — o onboarding e a vitrine o incluíam por conta própria e a vitrine
duplicaria `<symbol id>` na hora em que a base o trouxesse. E ele NÃO entra no
shell offline: aquela tela é pré-cacheada e servida a quem pegar o aparelho
depois (CLAUDE.md, "três ausências no mapa").

A âncora é `<symbol id="icone-chama"` — o primeiro símbolo do sprite —, e a
contagem é EXATA. "Pelo menos um" deixaria passar a duplicata que motivou o
teste: `id` repetido não dá erro, o `<use>` resolve para o primeiro e o
segundo fica na página como peso morto.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from plans.tests import create_complete_user

MARCADOR = '<symbol id="icone-chama"'


class SpriteUmaVezPorPaginaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # `/treino/` monta a ficha na primeira visita e precisa do catálogo de
        # divisões; sem o seed a rota estoura em `NoTrainingDays` e o teste
        # reprovaria por falta de fixture, não por sprite.
        call_command("seed_workouts", verbosity=0)

    #: A etapa 2 do onboarding entra para quem JÁ terminou, que a reabre para
    #: editar — é a rota que incluía o sprite por conta própria e ficaria com
    #: dois quando a base passasse a trazê-lo.
    ROTAS_LOGADAS = (
        "/",
        "/treino/",
        "/historico/",
        "/hidratacao/",
        "/areas/",
        "/conta/perfil/",
        "/conta/onboarding/2/",
    )
    ROTAS_ANONIMAS = ("/conta/entrar/",)

    def test_toda_pagina_tem_o_sprite_exatamente_uma_vez(self):
        user = create_complete_user("sprite@exemplo.com")
        self.client.force_login(user)
        for rota in self.ROTAS_LOGADAS:
            with self.subTest(rota=rota):
                resposta = self.client.get(rota, follow=True)
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.redirect_chain, [], "a rota redirecionou: mediria outra página")
                self.assertEqual(resposta.content.decode().count(MARCADOR), 1)
        self.client.logout()
        for rota in self.ROTAS_ANONIMAS:
            with self.subTest(rota=rota):
                resposta = self.client.get(rota)
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.content.decode().count(MARCADOR), 1)

    #: O único traço fora de 2 que a base e os cartões de escolha podem
    #: escrever: o visto do cartão MARCADO (`choice_cards.html`), um glifo de
    #: 12 px onde 2 vira fio — é ênfase de estado, não ícone da grade de 24.
    TRACOS_PERMITIDOS_NO_CONSUMIDOR = {"2", "2.8"}

    def test_cada_simbolo_do_sprite_declara_traco_2(self):
        """Direção C §7: grade 24, traço 2. E o atributo tem de estar em CADA
        `<symbol>`: medido em 16/09/2026, o clone do `<use>` herda do consumidor
        e dos ancestrais DELE, não da raiz do sprite — com o atributo só na
        raiz, o cartão de escolha desenhava o ícone com traço 1 (1 397 px de
        tinta contra 2 789). Ler a raiz seria ler um atributo inerte."""
        sprite = (Path(settings.BASE_DIR) / "templates" / "partials" / "icones.html").read_text(encoding="utf-8")
        simbolos = re.findall(r"<symbol [^>]*>", sprite)
        # 17 desde 22/09/2026: os quatro das abas (sol, talher, barras,
        # grade) entraram no sprite quando a navegação virou cinco itens.
        # Eles moravam como `<path>` copiado dentro do `base.html`, um jogo
        # por barra — o sprite existe exatamente para isso não acontecer.
        self.assertEqual(len(simbolos), 17, "o sprite tem 17 símbolos")
        for tag in simbolos:
            with self.subTest(simbolo=tag):
                self.assertIn('stroke-width="2"', tag)

    def test_o_consumidor_nao_redefine_o_traco(self):
        """A tabbar escrevia 1.8 e os cartões de escolha 1.7 — dois traços para
        a mesma grade. Todo `stroke-width` que a base e os cartões escrevem, fora
        de comentário, está na lista fechada acima."""
        raiz = Path(settings.BASE_DIR) / "templates"
        for nome in ("partials/choice_cards.html", "base.html"):
            texto = re.sub(r"{% comment %}.*?{% endcomment %}", "", (raiz / nome).read_text(encoding="utf-8"), flags=re.S)
            texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
            tracos = set(re.findall(r'stroke-width="([^"]+)"', texto))
            with self.subTest(template=nome):
                self.assertTrue(tracos, "o template não desenha ícone nenhum: o controle positivo sumiu")
                self.assertLessEqual(tracos, self.TRACOS_PERMITIDOS_NO_CONSUMIDOR, f"traço fora da lista: {tracos}")

    def test_controle_o_sprite_continua_sendo_um_arquivo_com_simbolos(self):
        """Se `icones.html` esvaziasse, "exatamente uma vez" ficaria vermelho
        em toda rota — mas este controle diz ONDE o problema está, e garante
        que o marcador dos testes acima ainda é um símbolo real do sprite."""
        sprite = (Path(settings.BASE_DIR) / "templates" / "partials" / "icones.html").read_text(encoding="utf-8")
        self.assertIn(MARCADOR, sprite)
        self.assertGreaterEqual(len(re.findall(r"<symbol id=\"icone-", sprite)), 17)
