# -*- coding: utf-8 -*-
"""A folha vai para o navegador SEM os comentários (decisão do dono, 20/09/2026).

Medido em produção na auditoria de 20/09: `app.css` tinha 340 067 bytes, e
60 % eram comentário — o arquivo é lido de ponta a ponta por quem programa,
e isso é decisão de código. Mas o navegador de quem usa recebia os
comentários também: 106 KB gzip na primeira visita, a maior transferência
depois do HTML, com FCP frio de 1,2–2,2 s no Wi-Fi. Sem os comentários a
mesma folha comprime para 23 KB. A cobertura de regras (CDP, 24 rotas × 2
temas × 2 larguras) mostrou que o peso NÃO era CSS morto: 87 % dos bytes de
regra são usados. Era comentário.

O que se prova aqui: a fonte continua o arquivo comentado; a cópia que o
`collectstatic` entrega (a com hash no nome, a que o manifesto aponta) não
tem comentário nenhum; as `url()` continuam reescritas; e a versão dos
estáticos (`push.assets.version`) continua vindo da fonte.
"""
import gzip
import os
import re
import tempfile

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from config.estaticos import ArmazenamentoDeEstaticos, sem_comentarios
from config.settings import BASE_DIR, staticfiles_backend


class SemComentariosTests(SimpleTestCase):
    def test_tira_o_comentario_e_deixa_a_regra(self):
        css = "/* um\n comentário */\n.a { color: red; }\n\n\n/* outro */ .b { top: 0 }\n"
        self.assertEqual(sem_comentarios(css), ".a { color: red; }\n .b { top: 0 }\n")

    def test_nao_toca_em_url_nem_em_string_com_barra(self):
        """`url("x/*y*/z")` dentro de aspas não é comentário — mas o CSS do
        app não tem isso; o que importa é a regra continuar inteira."""
        css = '.a { background: url("../icons/x.png"); content: "a/b"; }\n'
        self.assertEqual(sem_comentarios(css), css)

    def test_a_fonte_do_app_perde_mais_da_metade(self):
        fonte = open(os.path.join(BASE_DIR, "static", "css", "app.css"), encoding="utf-8").read()
        limpo = sem_comentarios(fonte)
        self.assertNotIn("/*", limpo)
        self.assertLess(len(limpo), len(fonte) * 0.5, "a folha é mais da metade comentário; sem eles ela cai abaixo da metade")
        self.assertLess(len(gzip.compress(limpo.encode())), 40 * 1024, "o gzip da folha servida fica abaixo de 40 KB")


class OStorageDeProducaoTests(SimpleTestCase):
    def test_producao_usa_o_storage_que_tira_os_comentarios(self):
        self.assertEqual(staticfiles_backend(debug=False), "config.estaticos.ArmazenamentoDeEstaticos")

    def test_desenvolvimento_continua_sem_manifesto(self):
        self.assertEqual(staticfiles_backend(debug=True), "django.contrib.staticfiles.storage.StaticFilesStorage")


class OCollectstaticEntregaAFolhaLimpaTests(TestCase):
    """Roda o `collectstatic` de verdade numa pasta temporária, com o storage
    de produção, e olha o que ficou lá."""

    def test_a_copia_com_hash_nao_tem_comentario_e_a_fonte_continua_com(self):
        with tempfile.TemporaryDirectory(prefix="nutriplan-static-") as raiz:
            with override_settings(STATIC_ROOT=raiz, STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "config.estaticos.ArmazenamentoDeEstaticos"},
            }):
                # `override_settings(STORAGES=…)` já reinicia o proxy
                # `staticfiles_storage` (django.test.signals.storages_changed).
                from django.contrib.staticfiles import storage as st

                call_command("collectstatic", interactive=False, verbosity=0)
                # O MANIFESTO é o que o `{% static %}` de produção lê; o
                # `hashed_name()` recalcula do conteúdo sem as `url()`
                # reescritas e daria outro nome.
                hashed = st.staticfiles_storage.hashed_files["css/app.css"]
            caminho = os.path.join(raiz, hashed.replace("/", os.sep))
            servida = open(caminho, encoding="utf-8").read()
            self.assertNotIn("/*", servida)
            self.assertRegex(hashed, r"css/app\.[0-9a-f]{12}\.css")
            # as `url()` do CSS continuam reescritas para os nomes com hash
            self.assertRegex(servida, r"url\([^)]*fonts/[a-z-]+\.[0-9a-f]{12}\.woff2")
            # e o gzip que o whitenoise serve é o da folha limpa
            self.assertLess(os.path.getsize(caminho + ".gz"), 40 * 1024)
        fonte = open(os.path.join(BASE_DIR, "static", "css", "app.css"), encoding="utf-8").read()
        self.assertIn("/*", fonte, "a fonte continua comentada")

    def test_so_a_folha_do_app_e_tocada(self):
        """Os JS e as outras folhas (se houver) saem como estão: o alvo é a
        `app.css`, medida; o resto não tem comentário que pese."""
        self.assertEqual(ArmazenamentoDeEstaticos.ALVO, "css/app.css")


class AVersaoDosEstaticosContinuaDaFonteTests(SimpleTestCase):
    def test_version_le_a_fonte(self):
        from push import assets

        assets.reset_cache()
        v1 = assets.version()
        self.assertEqual(len(v1), 8)
        self.assertEqual(assets._find("css/app.css"), BASE_DIR / "static" / "css" / "app.css")
        self.assertRegex(re.sub(r"[0-9a-f]", "", v1), r"^$")
