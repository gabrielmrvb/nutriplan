# -*- coding: utf-8 -*-
"""O opt-out (`Profile.rastrear_uso` desligado) bloqueia o evento INTEIRO de
quem está logado — antes só anonimizava (`pode_identificar`) e a linha
continuava gravando com `anon_id`. Decisão 2 do plano de 28/09/2026: quem
desligou o rastreio na sessão não quer NENHUMA linha, nem anônima.

O DNT continua sendo o caminho de "conta no agregado, mas sem me
identificar" — ele não passa por `pode_registrar`, só por `pode_identificar`
(`analytics/tests.py::test_dnt_mantem_o_evento_anonimo_mesmo_logado` prende
isso). Visitante anônimo (sem sessão de opt-out) continua contando."""
import json

from django.test import TestCase
from django.urls import reverse

from analytics.models import Event
from analytics.privacidade import CHAVE_SEM_RASTREIO
from plans.tests import create_complete_user


def corpo(eventos, **contexto):
    base = {"session_id": "sess-1", "device": "mobile", "width": 390,
            "theme": "ferro", "pwa": False, "app_version": "abc1234"}
    base.update(contexto)
    base["events"] = eventos
    return json.dumps(base)


class OOptOutBloqueiaTudoTests(TestCase):
    """Toggle desligado = nenhuma linha de Event, nem anônima."""

    def setUp(self):
        self.user = create_complete_user(email="optout@exemplo.com")
        self.client.force_login(self.user)

    def _desligar(self):
        s = self.client.session
        s[CHAVE_SEM_RASTREIO] = True
        s.save()

    def test_evento_do_servidor_nao_grava_com_toggle_desligado(self):
        self._desligar()
        self.client.post(reverse("plans:log_hydration"), {"ml": "250", "de": "topo"})
        self.assertEqual(Event.objects.count(), 0)

    def test_com_toggle_ligado_grava(self):  # controle positivo
        self.client.post(reverse("plans:log_hydration"), {"ml": "250", "de": "topo"})
        self.assertGreater(Event.objects.filter(user=self.user).count(), 0)

    def test_a_ingestao_do_navegador_recusa_com_toggle_desligado(self):
        self._desligar()
        r = self.client.post(
            reverse("analytics:ingest"),
            data=corpo([{"name": "agua.registrada"}]),
            content_type="text/plain",
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(Event.objects.count(), 0)
