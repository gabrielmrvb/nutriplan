# -*- coding: utf-8 -*-
"""`manage.py pico_de_sessoes`: o número que decide o plano Starter.

Sessões DISTINTAS por janela de 5 min (não eventos, não minutos): três
eventos da mesma sessão contam um; duas sessões em minutos diferentes da
mesma janela contam duas; a janela seguinte recomeça. Uma consulta, e o
texto diz quantos dias bateram o teto.
"""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from analytics.management.commands.pico_de_sessoes import picos
from analytics.models import Event


class OPicoDeSessoesTests(TestCase):
    def setUp(self):
        self.agora = timezone.now().replace(second=0, microsecond=0)
        base = self.agora - timedelta(hours=2)
        # janela A (minutos 0–4): sessões s1 (3 eventos), s2, s3 → 3 distintas
        for i in range(3):
            Event.objects.create(name="pagina", session_id="s1", ts=base + timedelta(minutes=i))
        Event.objects.create(name="pagina", session_id="s2", ts=base + timedelta(minutes=1))
        Event.objects.create(name="pagina", session_id="s3", ts=base + timedelta(minutes=4))
        # janela B (minutos 5–9): só s4 → 1
        Event.objects.create(name="pagina", session_id="s4", ts=base + timedelta(minutes=7))
        # sem sessão: não conta
        Event.objects.create(name="pagina", session_id="", ts=base + timedelta(minutes=2))
        self.base = base

    def test_conta_sessoes_distintas_por_janela_e_o_pico_do_dia(self):
        lista = picos(dias=1, janela=5, agora=self.agora)
        self.assertEqual(len(lista), 1)
        dia, pico, balde = lista[0]
        self.assertEqual(pico, 3, "s1 três vezes conta uma; s2 e s3 na mesma janela")
        self.assertEqual(balde.minute % 5, 0)

    def test_uma_consulta_so(self):
        with CaptureQueriesContext(connection) as consultas:
            picos(dias=1, janela=5, agora=self.agora)
        self.assertEqual(len(consultas), 1)

    def test_o_comando_diz_quantos_dias_bateram_o_teto(self):
        saida = StringIO()
        call_command("pico_de_sessoes", "--dias", "1", "--teto", "3", stdout=saida)
        texto = saida.getvalue()
        self.assertIn("pico  3 sessões", texto)
        self.assertIn("acima do teto (3)", texto)
        self.assertIn("dias no teto ou acima: 1 de 1", texto)
        saida = StringIO()
        call_command("pico_de_sessoes", "--dias", "1", "--teto", "5", stdout=saida)
        self.assertIn("dias no teto ou acima: 0 de 1", saida.getvalue())
