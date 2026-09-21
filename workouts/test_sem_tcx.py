# -*- coding: utf-8 -*-
"""Exportar TCX saiu (decisão do dono, 20/09/2026).

A rota `/treino/exportar/saude.tcx` existia porque uma PWA não escreve no
Apple Saúde nem no Health Connect; o arquivo era a ponte. A auditoria de
20/09 achou nela a segunda fórmula de duração ("42 min" no painel contra
"~59 min" no cartão — parte A, `fix/duracao-do-resumo`) e nenhum sinal de
uso. O que sai: a rota, a view, o `tcx()` e os dois links ("Exportar para
o Saúde", "Exportar para o app de saúde"). O que FICA: `resumo_da_sessao`,
que o painel usa para dizer "N séries, M minutos"; o módulo
`health_export.py` guarda esse resumo até o PR da duração (parte A) entrar
— renomeá-lo agora seria conflito de merge sem ganho.
"""
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from workouts import health_export
from workouts.tests import create_user


class OTcxSaiuTests(TestCase):
    def test_a_rota_nao_existe(self):
        with self.assertRaises(NoReverseMatch):
            reverse("workouts:health_export")
        self.client.force_login(create_user())
        self.assertEqual(self.client.get("/treino/exportar/saude.tcx").status_code, 404)

    def test_o_modulo_nao_gera_mais_arquivo(self):
        self.assertFalse(hasattr(health_export, "tcx"))
        self.assertTrue(hasattr(health_export, "resumo_da_sessao"), "o resumo do painel fica")

    def test_nenhum_template_oferece_exportar(self):
        from pathlib import Path

        from django.conf import settings

        for arquivo in sorted((settings.BASE_DIR / "templates").rglob("*.html")):
            texto = arquivo.read_text(encoding="utf-8")
            self.assertNotIn("health_export", texto, arquivo.name)
            self.assertNotIn("Exportar para o Saúde", texto, arquivo.name)
            self.assertNotIn("Exportar para o app de saúde", texto, arquivo.name)
