# -*- coding: utf-8 -*-
"""A coluna de busca do alimento, preenchida para quem já existe.

`RunPython` e não `default`: a normalização depende do NOME de cada linha, e
um default não tem acesso a ele. O `desmarcar` esvazia a coluna em vez de
apagá-la — a reversão do `AddField` faz isso; o que ele garante é que
reverter e reaplicar não deixa lixo de um nome que mudou no meio.
"""
from django.db import migrations, models


def preencher(apps, schema_editor):
    from catalog.busca import normalizar

    Food = apps.get_model("catalog", "Food")
    # Em lote, e sem `save()`: a migration roda com o modelo histórico, que não
    # tem o `save()` do modelo de verdade.
    linhas = list(Food.objects.all().only("pk", "name"))
    for food in linhas:
        food.busca = normalizar(food.name)
    if linhas:
        Food.objects.bulk_update(linhas, ["busca"], batch_size=200)


def esvaziar(apps, schema_editor):
    Food = apps.get_model("catalog", "Food")
    Food.objects.update(busca="")


class Migration(migrations.Migration):

    dependencies = [("catalog", "0008_ilustracao_da_receita")]

    operations = [
        migrations.AddField(
            model_name="food",
            name="busca",
            field=models.CharField(
                blank=True, db_index=True, max_length=120, verbose_name="nome normalizado"
            ),
        ),
        migrations.RunPython(preencher, esvaziar),
    ]
