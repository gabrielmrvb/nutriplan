# -*- coding: utf-8 -*-
"""Semeia a Tabela Brasileira de Composição de Alimentos (TACO) no catálogo.

A fonte e o que foi descartado estão escritos no próprio `catalog/data/
taco.json`, na chave `fonte` — TACO 4ª edição (NEPA/UNICAMP, 2011), pela
cópia normalizada de github.com/brolesi/taco (MIT, DOI
10.5281/zenodo.22145839), que é regenerada das planilhas originais.

POR QUE ISTO EXISTE: "comi outra coisa" só encontrava o que estava no
catálogo CURADO — 102 alimentos escolhidos para montar receita. Quem comeu
pão de queijo, açaí ou tapioca escrevia o nome, não casava com nada, e a
refeição entrava com ZERO caloria (achado #2 das personas). Com a TACO são
quase setecentos alimentos, e o que não casa passa a ser exceção de
verdade.

O CURADO GANHA do importado: se um nome já existe com outra fonte, a linha
da TACO é pulada. Os 102 têm porção ("1 fatia", "meia unidade"), corredor de
mercado e papel no prato — coisas que a tabela não tem e que o cardápio e a
lista de compras usam.
"""
import json
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand

from catalog.busca import normalizar
from catalog.models import Food, FoodSource

ARQUIVO = Path(__file__).resolve().parents[2] / "data" / "taco.json"


class Command(BaseCommand):
    help = "Carrega a TACO 4ª edição no catálogo de alimentos."

    def handle(self, *args, **opcoes):
        dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
        alimentos = dados["alimentos"]

        # UMA consulta para saber o que já existe, e não uma por alimento: o
        # seed roda em todo build, e 583 `get_or_create` seriam 583 idas ao
        # banco para descobrir que nada mudou.
        existentes = {
            nome: fonte
            for nome, fonte in Food.objects.values_list("name", "source")
        }

        novos, atualizados, pulados = [], 0, 0
        for item in alimentos:
            fonte = existentes.get(item["nome"])
            if fonte is not None and fonte != FoodSource.TACO:
                # Nome que o catálogo curado já usa: ele manda.
                pulados += 1
                continue
            campos = {
                # `busca` é CALCULADA aqui, e não lida do arquivo.
                #
                # O JSON já trouxe a chave pronta, e a sabotagem de 26/09/2026
                # mostrou o preço: com `normalizar` estragada de propósito, as
                # linhas da TACO continuavam achando — elas liam o arquivo, não
                # a função. Duas fontes da mesma regra é a fonte que envelhece
                # sozinha. `bulk_create`/`update` não passam pelo `save()` que
                # manteria a coluna, e é por isso que ela aparece aqui.
                "busca": normalizar(item["nome"]),
                "kcal": Decimal(str(item["kcal"])),
                "protein_g": Decimal(str(item["proteina_g"])),
                "carb_g": Decimal(str(item["carboidrato_g"])),
                "fat_g": Decimal(str(item["gordura_g"])),
                "fiber_g": Decimal(str(item["fibra_g"])),
                "source": FoodSource.TACO,
                "is_active": True,
            }
            if fonte is None:
                novos.append(Food(name=item["nome"], **campos))
            else:
                atualizados += Food.objects.filter(
                    name=item["nome"], source=FoodSource.TACO
                ).update(**campos)

        if novos:
            Food.objects.bulk_create(novos, batch_size=200)
        self.stdout.write(
            "  TACO: %d novos, %d atualizados, %d pulados (nome do catálogo curado)"
            % (len(novos), atualizados, pulados)
        )
