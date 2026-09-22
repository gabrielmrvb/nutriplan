# -*- coding: utf-8 -*-
"""Regenera as três provas da landing a partir do demo (decisão 3 da avaliação
de UX, 20/09/2026).

As provas (`static/img/landing/prova-*.png`) são screenshots do DEMO — o
produto de verdade, sobre um usuário fictício. Este comando as refaz a 390 px
de largura, no tema Papel (claro), pelo navegador headless de QA
(`scripts/qa/nav.py`, CDP). Como precisa de um Chrome, ele NÃO roda no build
gratuito do Render (sem navegador lá): é um comando de gestão, rodado local ou
em CI antes de recomitar as imagens. O teste
`plans/test_capturas_landing.py` reprova quando elas ficam velhas demais em
relação ao `app.css`, para ninguém esquecer de rodá-lo depois de mexer no
visual.

Por padrão captura da PRODUÇÃO (o demo está sempre no ar); `--base-url` aponta
para outro lugar (um servidor local, por exemplo).
"""
import json
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

NAV = Path(settings.BASE_DIR) / "scripts" / "qa" / "nav.py"
SESSAO = "capturas-landing"
LARGURA, ALTURA = 390, 844

#: (arquivo, caminho no demo ou None para a ficha que se resolve por link).
ALVOS = (
    ("prova-dia.png", "/demo/hoje/"),
    ("prova-treino.png", None),   # a ficha de um treino, achada por link
    ("prova-progresso.png", "/demo/historico/"),
)


class Command(BaseCommand):
    help = "Regenera as três capturas da landing a partir do demo (390px, tema Papel)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url", default="https://nutriplan-xxfn.onrender.com",
            help="Origem do demo (padrão: produção).",
        )

    def _nav(self, *args, ler=False):
        saida = subprocess.run(
            [sys.executable, str(NAV), SESSAO, *args],
            capture_output=True, text=True,
        )
        if saida.returncode != 0:
            raise CommandError("nav.py %s falhou: %s" % (args[0], saida.stderr.strip() or saida.stdout.strip()))
        return saida.stdout.strip() if ler else None

    def handle(self, *args, **options):
        base = options["base_url"].rstrip("/")
        destino = Path(settings.BASE_DIR) / "static" / "img" / "landing"
        destino.mkdir(parents=True, exist_ok=True)
        if not NAV.exists():
            raise CommandError("scripts/qa/nav.py não encontrado — o QA de navegador é o que captura.")

        try:
            self._nav("viewport", str(LARGURA), str(ALTURA))
            self._nav("tema", "claro")   # Papel
            for arquivo, caminho in ALVOS:
                url = self._url_do_treino(base) if caminho is None else base + caminho
                self._nav("open", url)
                self._nav("screenshot", str(destino / arquivo))
                # O WebP ao lado (22/09/2026): ~24 KB contra ~90 KB do PNG; a
                # landing serve o WebP a quem entende e o PNG a quem não.
                from PIL import Image

                Image.open(destino / arquivo).save(
                    (destino / arquivo).with_suffix(".webp"), "WEBP", quality=90, method=6
                )
                self.stdout.write("  %s (+ .webp) <- %s" % (arquivo, url))
        finally:
            self._nav("close")
        self.stdout.write(self.style.SUCCESS("Três capturas regeneradas em %s" % destino))

    def _url_do_treino(self, base):
        """A ficha de um treino, achada por LINK no painel — o id muda a cada
        seed, então não dá para fixá-lo. Pega o primeiro link de ficha."""
        self._nav("open", base + "/demo/treino/")
        href = self._nav(
            "eval",
            "(document.querySelector('a[href*=\"ficha\"]')||{}).getAttribute&&"
            "document.querySelector('a[href*=\"ficha\"]').getAttribute('href')",
            ler=True,
        )
        try:
            caminho = json.loads(href)
        except (json.JSONDecodeError, TypeError):
            caminho = None
        if not caminho:
            raise CommandError("não achei um link de ficha em /demo/treino/")
        return base + caminho if caminho.startswith("/") else caminho
