# -*- coding: utf-8 -*-
"""Suplementos saem do banco (decisão do dono, 20/09/2026).

A funcionalidade tinha saído do produto em `3536b61`; os modelos, o admin,
o catálogo e o seed ficaram para trás por três campanhas. Esta migration
apaga as duas tabelas — `supplements_supplementlog` primeiro, porque aponta
para `supplements_supplement`. Produção tinha 6 linhas de catálogo e UM
registro de pessoa; o backup `nutriplan-20260920-183736.dump` foi tirado e
restaurado num PostgreSQL 18 local antes de isto existir. Depois que o
deploy provar que ela rodou, a pasta `supplements/` inteira sai do
repositório (é o passo 2; o Django precisa da app em INSTALLED_APPS para
rodar a migration com este rótulo).
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("supplements", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="SupplementLog"),
        migrations.DeleteModel(name="Supplement"),
    ]
