"""O sprite (13 símbolos, 2,9 kB brutos, ~850 B gzip) passa a viver no `base.html`, uma vez por
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
                self.assertEqual(resposta.content.decode().count(MARCADOR), 1)
        self.client.logout()
        for rota in self.ROTAS_ANONIMAS:
            with self.subTest(rota=rota):
                resposta = self.client.get(rota)
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.content.decode().count(MARCADOR), 1)

    def test_o_traco_e_um_so(self):
        """Direção C §7: grade 24, traço 2. O consumidor não redefine.

        O sprite declara `stroke-width="2"` antes do `<defs>`; nenhum
        consumidor escreve um traço fracionário (1.7 nos cartões de escolha,
        1.8 na tabbar eram os dois que existiam)."""
        raiz = Path(settings.BASE_DIR) / "templates"
        sprite = (raiz / "partials" / "icones.html").read_text(encoding="utf-8")
        self.assertIn('stroke-width="2"', sprite.split("<defs>", 1)[0])
        for nome in ("partials/choice_cards.html", "base.html"):
            texto = (raiz / nome).read_text(encoding="utf-8")
            with self.subTest(template=nome):
                self.assertNotRegex(texto, r'stroke-width="1\.[0-9]"', "traço fora de 2 no consumidor")

    def test_controle_o_sprite_continua_sendo_um_arquivo_com_simbolos(self):
        """Se `icones.html` esvaziasse, "exatamente uma vez" ficaria vermelho
        em toda rota — mas este controle diz ONDE o problema está, e garante
        que o marcador dos testes acima ainda é um símbolo real do sprite."""
        sprite = (Path(settings.BASE_DIR) / "templates" / "partials" / "icones.html").read_text(encoding="utf-8")
        self.assertIn(MARCADOR, sprite)
        self.assertGreaterEqual(len(re.findall(r"<symbol id=\"icone-", sprite)), 13)
