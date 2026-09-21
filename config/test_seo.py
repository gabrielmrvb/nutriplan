# -*- coding: utf-8 -*-
"""SEO das rotas públicas: o que um buscador vê, e só onde ele deve ver.

Medido em produção em 21/09/2026, antes deste módulo: toda página tinha a
MESMA `<meta name="description">` (a frase genérica do `base.html`), nenhuma
tinha `canonical` nem Open Graph, e `/robots.txt` e `/sitemap.xml`
respondiam 404 com a página de "não encontrada" — um buscador que chegasse
pela demonstração indexaria as telas do Carlos como se fossem o produto.

O contrato: SETE rotas públicas são indexáveis, cada uma com descrição
própria, `canonical` e Open Graph; TODO o resto — telas do app (que exigem
sessão), as telas internas do demo, o shell offline — leva `noindex`, por
PADRÃO, no `base.html`. O sitemap lista exatamente as sete, e cada uma
responde 200 sem login: um sitemap com rota que redireciona para o login é
um sitemap que mente.
"""
import re
from pathlib import Path
from xml.etree import ElementTree

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from config.seo import DESCRICAO_PADRAO, ROTAS_PUBLICAS
from plans.tests import create_complete_user

RAIZ = Path(settings.BASE_DIR)
BASE = RAIZ / "templates" / "base.html"
#: Teto prático do trecho que o Google mostra; acima disso ele corta.
DESCRICAO_MAXIMA = 160


def _meta(html, nome, atributo="name"):
    padrao = r'<meta %s="%s" content="([^"]*)"' % (atributo, re.escape(nome))
    achados = re.findall(padrao, html)
    return achados


def _titulo(html):
    return re.search(r"<title>([^<]*)</title>", html).group(1).strip()


class RobotsESitemapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        call_command("seed_demo", verbosity=0)

    def test_robots_existe_aponta_para_o_sitemap_e_nao_lista_o_admin(self):
        """`robots.txt` diz onde não perder tempo e onde está o sitemap. Ele
        NÃO lista o admin: a rota vai deixar de ser óbvia (missão de
        segurança de 21/09), e um `Disallow` a anunciaria para quem procura."""
        resposta = self.client.get("/robots.txt")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta["Content-Type"].startswith("text/plain"))
        texto = resposta.content.decode()
        self.assertIn("User-agent: *", texto)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", texto)
        for privado in ("/gestao/", "/saude/", "/tarefas/", "/offline/"):
            self.assertIn("Disallow: %s" % privado, texto)
        self.assertNotIn("admin", texto)

    def test_o_sitemap_lista_exatamente_as_rotas_publicas_e_todas_respondem_200_sem_login(self):
        resposta = self.client.get("/sitemap.xml")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta["Content-Type"].startswith("application/xml"))
        raiz = ElementTree.fromstring(resposta.content)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [e.text for e in raiz.findall("s:url/s:loc", ns)]
        self.assertEqual(sorted(locs), sorted("http://testserver" + rota for rota in ROTAS_PUBLICAS))
        self.assertEqual(len(locs), len(set(locs)), "sem rota repetida")
        for loc in locs:
            caminho = loc.replace("http://testserver", "")
            with self.subTest(rota=caminho):
                self.assertEqual(self.client.get(caminho).status_code, 200, "rota pública tem de abrir sem sessão")

    def test_toda_rota_publica_e_indexavel_com_descricao_propria_canonical_e_open_graph(self):
        for rota in ROTAS_PUBLICAS:
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                cabeca = html.split("</head>", 1)[0]
                self.assertNotIn('name="robots"', cabeca, "rota pública não leva noindex")
                descricoes = _meta(cabeca, "description")
                self.assertEqual(len(descricoes), 1, "UMA description por página")
                self.assertNotEqual(descricoes[0], DESCRICAO_PADRAO, "descrição própria, não a genérica")
                self.assertLessEqual(len(descricoes[0]), DESCRICAO_MAXIMA)
                self.assertIn('<link rel="canonical" href="http://testserver%s">' % rota, cabeca)
                self.assertEqual(_meta(cabeca, "og:url", "property"), ["http://testserver" + rota])
                self.assertEqual(_meta(cabeca, "og:title", "property"), [_titulo(cabeca)])
                self.assertEqual(_meta(cabeca, "og:description", "property"), descricoes)
                self.assertEqual(_meta(cabeca, "og:type", "property"), ["website"])
                self.assertEqual(_meta(cabeca, "og:locale", "property"), ["pt_BR"])
                imagem = _meta(cabeca, "og:image", "property")
                self.assertEqual(len(imagem), 1)
                self.assertTrue(imagem[0].startswith("http://testserver/static/img/og-landing"), imagem)
                self.assertEqual(_meta(cabeca, "og:image:width", "property"), ["1200"])
                self.assertEqual(_meta(cabeca, "og:image:height", "property"), ["630"])
                self.assertEqual(_meta(cabeca, "twitter:card"), ["summary_large_image"])
                self.assertEqual(_meta(cabeca, "twitter:image"), imagem)
                self.assertEqual(_meta(cabeca, "twitter:title"), [_titulo(cabeca)])

    def test_o_que_nao_e_publico_leva_noindex_e_nao_tem_canonical(self):
        """A tela do app (com sessão), a tela interna do demo (o Carlos) e o
        shell offline não são o produto para um buscador — são instâncias."""
        pessoa = create_complete_user(email="seo@exemplo.com")
        self.client.force_login(pessoa)
        casos = [reverse("plans:today"), reverse("plans:hydration")]
        self.client.logout()
        casos += ["/demo/treino/", "/demo/hidratacao/", reverse("offline")]
        for rota in casos:
            with self.subTest(rota=rota):
                if rota.startswith("/demo/") or rota == reverse("offline"):
                    resposta = self.client.get(rota)
                else:
                    self.client.force_login(pessoa)
                    resposta = self.client.get(rota)
                    self.client.logout()
                self.assertEqual(resposta.status_code, 200)
                cabeca = resposta.content.decode().split("</head>", 1)[0]
                self.assertEqual(_meta(cabeca, "robots"), ["noindex"])
                self.assertNotIn('rel="canonical"', cabeca)
                self.assertNotIn('property="og:', cabeca)
                self.assertEqual(_meta(cabeca, "description"), [DESCRICAO_PADRAO])


class AImagemDoCardEOsDadosEstruturadosTests(TestCase):
    def test_a_imagem_do_card_tem_o_tamanho_do_open_graph_e_e_leve(self):
        """1200×630 é o que Facebook, WhatsApp, LinkedIn e Twitter pedem
        para o card grande; acima de 120 KB o preview demora a aparecer no
        chat. O CONTEÚDO não é testado: é a landing capturada, e envelhece."""
        from PIL import Image

        arquivo = RAIZ / "static" / "img" / "og-landing.png"
        self.assertTrue(arquivo.exists())
        self.assertLessEqual(arquivo.stat().st_size, 120_000)
        with Image.open(arquivo) as imagem:
            self.assertEqual(imagem.size, (1200, 630))

    def test_a_landing_tem_dados_estruturados_de_app_gratuito(self):
        """`SoftwareApplication` é o que faz o buscador entender "app, na
        web, de graça" — e o bloco é JSON válido, senão não vale nada."""
        import json

        html = self.client.get("/").content.decode()
        blocos = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, flags=re.S)
        self.assertEqual(len(blocos), 1)
        dados = json.loads(blocos[0])
        self.assertEqual(dados["@type"], "SoftwareApplication")
        self.assertEqual(dados["name"], "NutriPlan")
        self.assertEqual(dados["url"], "http://testserver/")
        self.assertEqual(dados["applicationCategory"], "HealthApplication")
        self.assertEqual(dados["offers"]["price"], "0")
        self.assertEqual(dados["inLanguage"], "pt-BR")
        # Só a landing: a tela do app e o demo não são "o software" para o índice.
        self.assertNotIn("application/ld+json", self.client.get("/demo/").content.decode())


class OBlocoMoraNoHeadTests(TestCase):
    def test_a_parcial_e_incluida_uma_vez_dentro_do_head_e_por_padrao_e_noindex(self):
        """Textual: o bloco `seo` está no `<head>` do `base.html`, inclui a
        parcial UMA vez e o padrão (sem argumento) é o `noindex` — quem
        esquecer de declarar uma tela pública fica fora do índice, e não o
        contrário."""
        base = BASE.read_text(encoding="utf-8")
        cabeca = base.split("</head>", 1)[0]
        self.assertEqual(cabeca.count('{% include "partials/seo.html"'), 1)
        self.assertEqual(base.count('{% include "partials/seo.html"'), 1)
        self.assertIn("{% block seo %}", cabeca)
        self.assertNotIn('name="description"', cabeca, "a description mora na parcial, não solta na base")
        parcial = (RAIZ / "templates" / "partials" / "seo.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="noindex">', parcial)
        self.assertNotIn("<script", parcial)
        self.assertNotIn("style=", parcial)
