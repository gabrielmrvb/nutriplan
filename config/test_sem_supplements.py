# -*- coding: utf-8 -*-
"""Suplementos saíram do produto de vez (decisão do dono, 20/09/2026).

A FUNCIONALIDADE já tinha saído em `3536b61` ("Remove a funcionalidade de
Suplementos do produto"): ficaram os modelos, o admin, o catálogo em JSON, o
seed no build, uma permissão em `papeis.py`, uma linha no export de dados e
duas fontes no painel de gestão — código que a auditoria de 20/09 encontrou
sem tela nenhuma. Produção tinha 6 suplementos de catálogo e UM registro de
`SupplementLog` (backup `nutriplan-20260920-183736.dump`, restaurado e
verificado num PostgreSQL 18 local antes desta migration existir).

A remoção é em dois passos, como o Django pede para uma app com tabela: este
PR tira tudo que é código e deixa a migration que APAGA as duas tabelas; a
pasta `supplements/` some no PR seguinte, depois que o deploy provar que a
migration rodou. Até lá a app está em `INSTALLED_APPS` só por causa dela.
"""
from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.db import connection
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from accounts import papeis


class AAppFicouSoComAMigrationTests(TestCase):
    def test_nenhum_modelo_registrado(self):
        self.assertEqual(list(apps.get_app_config("supplements").get_models()), [])

    def test_a_migration_apaga_as_duas_tabelas(self):
        loader = MigrationLoader(connection)
        ultima = max(k for k in loader.disk_migrations if k[0] == "supplements")
        operacoes = loader.disk_migrations[ultima].operations
        apagadas = sorted(op.name for op in operacoes if op.__class__.__name__ == "DeleteModel")
        self.assertEqual(apagadas, ["Supplement", "SupplementLog"])

    def test_nao_ha_seed_nem_catalogo(self):
        from importlib import util

        self.assertIsNone(util.find_spec("supplements.management"))
        self.assertIsNone(util.find_spec("supplements.models"))
        self.assertIsNone(util.find_spec("supplements.admin"))

    def test_o_admin_nao_tem_mais_a_tela(self):
        with self.assertRaises(NoReverseMatch):
            reverse("admin:supplements_supplement_changelist")

    def test_a_permissao_saiu_dos_papeis(self):
        chaves = {chave for papel in papeis.PAPEIS.values() for chave in papel}
        self.assertFalse(any(app == "supplements" for app, _ in chaves), chaves)

    def test_o_build_nao_semeia_suplemento(self):
        build = open(settings.BASE_DIR / "scripts" / "build.sh", encoding="utf-8").read()
        self.assertNotIn("seed_supplements", build)
