# -*- coding: utf-8 -*-
"""A API v1 saiu (decisão do dono, 20/09/2026).

Ela era "o menor contrato que prova a Fase 1" da Corrida mobile: token, eu e
três rotas de corrida, para um cliente Capacitor que esta máquina não
consegue construir (BACKLOG, "SERVIDOR PRONTO, CLIENTE BLOQUEADO", 04/09).
Sem cliente, a API era seis rotas com `@csrf_exempt` a manter seguras para
sempre, um modelo de token com o próprio ciclo de revogação e uma pasta
`mobile/` que só falava com ela. Tudo isso sai junto: a app `api`, o
`TokenDeApp` (tabela `accounts_tokendeapp`, apagada por migration), o
cliente e o contrato em `docs/api-v1.md`. O que fica é o que a PWA usa:
`SalvarCorridaView`, `TracoDaCorrida` e a importação de GPX/TCX.
"""
from importlib import util

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.urls import NoReverseMatch, reverse


class AApiSaiuTests(TestCase):
    def test_a_app_nao_existe_mais(self):
        self.assertNotIn("api", settings.INSTALLED_APPS)
        self.assertIsNone(util.find_spec("api"))

    def test_as_rotas_respondem_404(self):
        for rota in ("/api/v1/token/", "/api/v1/eu/", "/api/v1/corridas/"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 404)
                self.assertEqual(self.client.post(rota, {}).status_code, 404)
        with self.assertRaises(NoReverseMatch):
            reverse("api:token")

    def test_o_token_de_app_saiu_do_modelo_e_do_banco(self):
        nomes = {m.__name__ for m in apps.get_app_config("accounts").get_models()}
        self.assertNotIn("TokenDeApp", nomes)
        loader = MigrationLoader(connection)
        ultima = max(k for k in loader.disk_migrations if k[0] == "accounts")
        apagados = [op.name for op in loader.disk_migrations[ultima].operations if op.__class__.__name__ == "DeleteModel"]
        self.assertIn("TokenDeApp", apagados)

    def test_o_cliente_e_o_contrato_sairam_do_repositorio(self):
        self.assertFalse((settings.BASE_DIR / "mobile").exists())
        self.assertFalse((settings.BASE_DIR / "docs" / "api-v1.md").exists())

    def test_trocar_a_senha_continua_funcionando_sem_tokens(self):
        """`set_password` revogava os tokens de app; sem eles, trocar a senha é
        só trocar a senha."""
        from accounts.models import User

        pessoa = User.objects.create_user(email="senha@exemplo.com", password="antiga-bem-forte-1")
        pessoa.set_password("nova-bem-forte-2")
        pessoa.save()
        self.assertTrue(User.objects.get(pk=pessoa.pk).check_password("nova-bem-forte-2"))
