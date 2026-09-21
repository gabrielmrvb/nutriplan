# -*- coding: utf-8 -*-
"""As capturas da landing não podem envelhecer atrás do design (decisão 3 da
avaliação de UX, 20/09/2026).

As três provas da landing (`static/img/landing/prova-*.png`) são screenshots
do demo. Screenshot envelhece quando a tela muda — e o design mora em
`app.css`. Este teste falha quando o último commit que mexeu no `app.css` é
mais de `TOLERANCIA_DIAS` mais NOVO que a captura mais velha: sinal de que o
visual mudou e ninguém rodou `manage.py capturas_landing`.

Usa a data do COMMIT (git), não o mtime do arquivo — mtime muda a cada
checkout e não diz nada sobre o conteúdo.
"""
import subprocess
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

#: Duas semanas. A captura não precisa acompanhar cada ajuste de tinta, mas
#: não pode ficar meses atrás de uma mudança de layout.
TOLERANCIA_DIAS = 14

CAPTURAS = ("prova-dia.png", "prova-treino.png", "prova-progresso.png")


def _commit_ct(caminho):
    """Unixtime do último commit que tocou `caminho`, ou None se não versionado."""
    saida = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "--", caminho],
        cwd=str(settings.BASE_DIR), capture_output=True, text=True,
    ).stdout.strip()
    return int(saida) if saida else None


class AsCapturasNaoEnvelhecemAtrasDoDesign(SimpleTestCase):
    def test_as_capturas_nao_estao_velhas_demais_em_relacao_ao_app_css(self):
        base = Path(settings.BASE_DIR) / "static" / "img" / "landing"
        css = _commit_ct("static/css/app.css")
        self.assertIsNotNone(css, "app.css não está versionado?")

        for nome in CAPTURAS:
            caminho = base / nome
            with self.subTest(captura=nome):
                self.assertTrue(caminho.exists(), "captura sumiu: %s" % nome)
                ct = _commit_ct("static/img/landing/%s" % nome)
                self.assertIsNotNone(ct, "captura não commitada: %s" % nome)
                atraso_dias = (css - ct) / 86400
                self.assertLessEqual(
                    atraso_dias, TOLERANCIA_DIAS,
                    "%s está %.0f dias atrás do último commit de app.css — "
                    "rode `manage.py capturas_landing` e recomite as três."
                    % (nome, atraso_dias),
                )
