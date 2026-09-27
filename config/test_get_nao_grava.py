"""Abrir uma tela não grava nada.

QA exploratório de 27/09/2026 (`achados/qa-exploratorio-20260927.md`, R6).
Para achar escrita escondida atrás de leitura, a varredura comparou os
contadores do Postgres antes e depois de uma passada só de GET. A única
tabela que mudou fora do analytics (que chega por POST) foi
`avisos_preferencia`: `GET /avisos/` chamava `Preferencia.de`, um
`get_or_create`, e criava a linha na primeira visita. O efeito é inofensivo,
porque a linha nasce com os padrões, mas "ver" não pode ser "gravar". Uma
leitura que escreve concorre com a escrita de verdade, suja o `atualizado_em`
e é justamente o tipo de efeito colateral que ninguém procura quando o dado
aparece errado.

A régua abaixo abre as telas logadas de quem já tem os dois planos montados
e exige ZERO `INSERT`/`UPDATE`/`DELETE`. Rota nova que grave num GET deixa
de gravar ou entra aqui com a razão escrita. (A renovação da sessão,
`config/sessao.py`, só escreve depois de metade da vida da sessão e não
aparece numa sessão recém-criada.)
"""
import re

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from plans import services
from plans.tests import create_complete_user
from workouts import services as treino

ROTAS = [
    "plans:today", "plans:alimentacao", "plans:history", "plans:hydration",
    "plans:shopping", "workouts:routine", "workouts:now", "workouts:corridas",
    "achievements:list", "accounts:profile", "avisos:preferencias",
    "ajuda:index", "ajuda:mudancas",
]

ESCRITA = re.compile(r'^\s*(INSERT INTO|UPDATE|DELETE FROM)\s+"?([a-z_]+)"?', re.I)


def escritas(consultas):
    achadas = []
    for consulta in consultas:
        casou = ESCRITA.match(consulta["sql"])
        if casou:
            achadas.append("%s %s" % (casou.group(1).upper(), casou.group(2)))
    return achadas


class NenhumGetGravaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="so-leio@exemplo.com")
        services.sync_active_plan(self.user)
        treino.sync_active_routine(self.user)
        self.client.force_login(self.user)

    def test_abrir_cada_tela_nao_grava(self):
        for nome in ROTAS:
            with self.subTest(rota=nome):
                with CaptureQueriesContext(connection) as consultas:
                    resposta = self.client.get(reverse(nome))
                self.assertIn(resposta.status_code, (200, 302))
                self.assertEqual(escritas(consultas.captured_queries), [], nome)

    def test_a_regua_enxerga_uma_escrita(self):
        """Controle positivo: uma escrita de verdade é pega pela régua."""
        with CaptureQueriesContext(connection) as consultas:
            self.client.post(reverse("plans:log_hydration"), {"ml": "250", "de": "topo"})
        self.assertTrue(any("plans_hydrationlog" in e for e in escritas(consultas.captured_queries)))
