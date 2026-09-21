"""Rola o bruto de um dia em agregados diários. Idempotente.

Roda no build (todo deploy) e pode ser chamado com `--dias N` para reprocessar
uma janela. Como o painel lê BRUTO para os últimos dias e AGREGADO para os
longos, e o bruto vive 90 dias, o agregado é a memória que sobrevive à poda.

A conta de PESSOAS distintas usa a mesma chave em todo lugar: o usuário quando
identificado, senão o `anon_id`. Assim uma pessoa que registrou logada e outra
anônima contam como duas, e a mesma pessoa em dez toques conta como uma.
"""
from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics import catalogo
from analytics.models import DailyAggregate, Event


class Command(BaseCommand):
    help = "Agrega os eventos brutos em contagens diárias (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("--dia", help="YYYY-MM-DD; padrão: ontem")
        parser.add_argument(
            "--dias", type=int, default=1,
            help="quantos dias reprocessar, a partir de --dia (ou de ontem) para trás",
        )

    def handle(self, *args, **opts):
        if opts.get("dia"):
            base = datetime.strptime(opts["dia"], "%Y-%m-%d").date()
        else:
            base = (timezone.now() - timezone.timedelta(days=1)).date()

        for i in range(max(1, opts["dias"])):
            dia = base - timezone.timedelta(days=i)
            criados = self._agregar_dia(dia)
            self.stdout.write(f"{dia}: {criados} recortes")

    def _agregar_dia(self, dia):
        baldes = defaultdict(lambda: {"count": 0, "gente": set()})
        linhas = Event.objects.filter(ts__date=dia).values(
            "name", "props", "user_id", "anon_id"
        )
        for linha in linhas.iterator():
            pessoa = linha["user_id"] or linha["anon_id"] or ""
            nome = linha["name"]
            props = linha["props"] or {}
            self._conta(baldes, (nome, "", ""), pessoa)
            for chave in catalogo.CATALOGO.get(nome, {}).get("props", []):
                if chave in props:
                    valor = str(props[chave])[:200]
                    self._conta(baldes, (nome, chave, valor), pessoa)

        # Reescreve o dia inteiro: idempotente, e limpa recortes que sumiram.
        DailyAggregate.objects.filter(day=dia).delete()
        DailyAggregate.objects.bulk_create(
            [
                DailyAggregate(
                    day=dia, name=nome, prop_key=pk, prop_value=pv,
                    count=v["count"], users=len(v["gente"]),
                )
                for (nome, pk, pv), v in baldes.items()
            ]
        )
        return len(baldes)

    @staticmethod
    def _conta(baldes, chave, pessoa):
        baldes[chave]["count"] += 1
        baldes[chave]["gente"].add(pessoa)
