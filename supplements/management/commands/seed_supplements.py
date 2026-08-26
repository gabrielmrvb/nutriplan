"""Carrega o catálogo de suplementos a partir do JSON.

Idempotente e com aposentadoria, como os outros dois seeds do projeto: o que
sai do arquivo é desativado em vez de apagado, para não quebrar o histórico de
quem já marcou aquilo.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from supplements.models import Supplement

DADOS = Path(__file__).resolve().parent.parent.parent / "data" / "supplements.json"


class Command(BaseCommand):
    help = "Popula o catálogo de suplementos."

    def handle(self, *args, **options):
        linhas = json.loads(DADOS.read_text(encoding="utf-8"))
        vistos = set()

        for linha in linhas:
            linha = {k: v for k, v in linha.items() if not k.startswith("_")}
            slug = linha.pop("slug")
            vistos.add(slug)
            Supplement.objects.update_or_create(
                slug=slug, defaults={**linha, "is_active": True}
            )

        # Suplemento que saiu do arquivo é aposentado, não removido: apagar
        # levaria junto todo registro de quem já tomou.
        aposentados = (
            Supplement.objects.filter(is_active=True)
            .exclude(slug__in=vistos)
            .update(is_active=False)
        )

        if options.get("verbosity", 1):
            self.stdout.write(
                f"  {len(vistos)} suplementos ({aposentados} aposentado(s))"
            )
