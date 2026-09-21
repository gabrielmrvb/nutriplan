# -*- coding: utf-8 -*-
"""Suplementos saíram do produto de vez (decisão do dono, 20/09/2026).

A FUNCIONALIDADE já tinha saído em `3536b61`; o código que sobrou (modelos,
admin, catálogo, seed, permissão, export, painel) saiu no PR #57, que deixou
só a migration `0002_apaga_suplementos` — `DeleteModel` das duas tabelas —
e a app em `INSTALLED_APPS` por causa dela. O deploy `6426ee7` (21/09/2026,
01:47) rodou essa migration em produção (`build.sh` migra com `errexit`),
com o backup `nutriplan-20260921-012106.dump` restaurado e conferido num
PostgreSQL 18 local antes de entrar na fila.

Este é o segundo passo: a pasta `supplements/` não existe mais e a app saiu
de `INSTALLED_APPS`. O que fica no banco de produção são as DUAS LINHAS de
`django_migrations` (`supplements.0001_initial` e `0002_apaga_suplementos`),
e é isso que o teste de baixo prende: uma app que saiu deixa migrações
aplicadas sem arquivo, e o `migrate` do próximo deploy tem de passar por
elas sem reclamar — o Django ignora migração aplicada de app que não está
no grafo, e o teste grava as duas linhas de propósito para provar que
continua ignorando.
"""
from importlib import util

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from accounts import papeis


class AAppNaoExisteMaisTests(TestCase):
    def test_nao_esta_instalada_nem_importavel(self):
        self.assertFalse(apps.is_installed("supplements"))
        self.assertIsNone(util.find_spec("supplements"))
        self.assertFalse((settings.BASE_DIR / "supplements").exists())

    def test_nenhuma_migration_no_disco_e_nenhum_modelo(self):
        loader = MigrationLoader(connection)
        self.assertEqual([k for k in loader.disk_migrations if k[0] == "supplements"], [])
        self.assertEqual([m for m in apps.get_models() if m._meta.app_label == "supplements"], [])

    def test_as_migracoes_aplicadas_em_producao_nao_travam_o_proximo_migrate(self):
        """Produção tem `supplements.0001_initial` e `0002_apaga_suplementos`
        gravadas em `django_migrations` e nenhum arquivo para elas. O próximo
        `migrate` (todo deploy) precisa passar: histórico consistente, plano
        vazio e `migrate --check` calado."""
        recorder = MigrationRecorder(connection)
        recorder.record_applied("supplements", "0001_initial")
        recorder.record_applied("supplements", "0002_apaga_suplementos")
        loader = MigrationLoader(connection)
        loader.check_consistent_history(connection)  # levanta InconsistentMigrationHistory se travar
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan(executor.loader.graph.leaf_nodes()), [])
        call_command("migrate", check_unapplied=True, verbosity=0)

    def test_o_admin_nao_tem_a_tela(self):
        with self.assertRaises(NoReverseMatch):
            reverse("admin:supplements_supplement_changelist")

    def test_a_permissao_saiu_dos_papeis(self):
        chaves = {chave for papel in papeis.PAPEIS.values() for chave in papel}
        self.assertFalse(any(app == "supplements" for app, _ in chaves), chaves)

    def test_o_build_e_o_hook_nao_conhecem_mais_a_app(self):
        build = (settings.BASE_DIR / "scripts" / "build.sh").read_text(encoding="utf-8")
        self.assertNotIn("supplements", build)
        hook = (settings.BASE_DIR / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
        conhecidas = next(l for l in hook.splitlines() if l.startswith("CONHECIDAS="))
        self.assertNotIn("supplements", conhecidas, "pasta que não existe não é 'conhecida'")
        escopo = (settings.BASE_DIR / "scripts" / "hooks" / "escopo_do_push.py").read_text(encoding="utf-8")
        self.assertNotIn("supplements", escopo)
