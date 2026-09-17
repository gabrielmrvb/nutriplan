# -*- coding: utf-8 -*-
"""A corrida registrada à mão — esteira, relógio, celular no bolso.

BENCHMARK-2026-09 (d): Strava e NRC têm registro manual de graça; um pilar só
com GPS ao vivo parece inacabado (DELTA de 16/09, D5/U20). Aqui o registro
manual reutiliza os tetos do GPS (`corrida_views`), o `op_id` da fila
(duplo toque = uma corrida) e o padrão de exclusão em duas etapas da conta.

Corrida por GPS não se edita: o traço contradiria os números.
"""
import re
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts.models import Corrida
from workouts.tests import create_user


def _campos(html):
    return dict(re.findall(r'name="([a-z_]+)"[^>]*?value="([^"]*)"', html))


class ORegistroManualTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="manual@exemplo.com")
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()

    def _post(self, op_id=None, **extra):
        dados = {"distancia_km": "5,2", "tempo": "28:10", "data": self.hoje.isoformat(),
                 "sensacao": "normal", "op_id": op_id or uuid.uuid4().hex}
        dados.update(extra)
        return self.client.post(reverse("workouts:corrida_nova"), dados)

    def test_o_get_traz_um_op_id_escondido_e_a_data_de_hoje(self):
        html = self.client.get(reverse("workouts:corrida_nova")).content.decode()
        campos = _campos(html)
        self.assertEqual(len(campos["op_id"]), 32)
        self.assertEqual(campos["data"], self.hoje.isoformat())

    def test_cria_com_virgula_e_mm_ss(self):
        r = self._post()
        self.assertEqual(r.status_code, 302)
        c = Corrida.objects.get(user=self.pessoa)
        self.assertEqual((c.distancia_m, c.duracao_s, c.origem, c.sensacao), (5200, 1690, "manual", "normal"))
        self.assertEqual(timezone.localtime(c.comecou_em).hour, 12)
        self.assertEqual(c.terminou_em - c.comecou_em, timedelta(seconds=1690))

    def test_h_mm_ss_tambem_vale(self):
        self._post(distancia_km="21,1", tempo="1:58:30")
        self.assertEqual(Corrida.objects.get().duracao_s, 7110)

    def test_o_duplo_toque_grava_uma_corrida(self):
        op = uuid.uuid4().hex
        self._post(op_id=op); self._post(op_id=op)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)

    def test_recusa_data_futura_tetos_e_velocidade_impossivel(self):
        amanha = (self.hoje + timedelta(days=1)).isoformat()
        for extra in ({"data": amanha}, {"distancia_km": "0,01"}, {"distancia_km": "301"},
                      {"tempo": "13:00:00"}, {"distancia_km": "10", "tempo": "10:00"}):
            r = self._post(**extra)
            self.assertEqual(r.status_code, 200, extra)
            self.assertContains(r, 'aria-invalid="true"')
        self.assertEqual(Corrida.objects.count(), 0)

    def test_a_lista_mostra_a_mao_a_sensacao_e_os_links(self):
        self._post()
        html = self.client.get(reverse("workouts:corridas")).content.decode()
        c = Corrida.objects.get()
        self.assertIn("à mão", html)
        self.assertIn("normal", html.lower())
        self.assertIn(reverse("workouts:corrida_editar", args=[c.pk]), html)
        self.assertIn(reverse("workouts:corrida_excluir", args=[c.pk]), html)


class EdicaoEExclusaoTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="edita@exemplo.com")
        self.outra = create_user(email="outra@exemplo.com")
        self.client.force_login(self.pessoa)
        agora = timezone.now()
        self.manual = Corrida.objects.create(user=self.pessoa, op_id="m1", origem="manual", comecou_em=agora - timedelta(minutes=30), terminou_em=agora, distancia_m=5000, duracao_s=1800)
        self.gps = Corrida.objects.create(user=self.pessoa, op_id="g1", origem="gps", comecou_em=agora - timedelta(hours=2), terminou_em=agora - timedelta(hours=1), distancia_m=8000, duracao_s=3600)

    def test_edita_a_manual(self):
        url = reverse("workouts:corrida_editar", args=[self.manual.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"distancia_km": "5,5", "tempo": "30:00", "data": timezone.localdate().isoformat(), "sensacao": "pesada"})
        self.assertEqual(r.status_code, 302)
        self.manual.refresh_from_db()
        self.assertEqual((self.manual.distancia_m, self.manual.duracao_s, self.manual.sensacao), (5500, 1800, "pesada"))

    def test_gps_nao_edita_e_corrida_alheia_e_404(self):
        self.assertEqual(self.client.get(reverse("workouts:corrida_editar", args=[self.gps.pk])).status_code, 404)
        self.client.force_login(self.outra)
        self.assertEqual(self.client.get(reverse("workouts:corrida_editar", args=[self.manual.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("workouts:corrida_excluir", args=[self.manual.pk])).status_code, 404)

    def test_exclusao_em_duas_etapas_vale_para_gps_e_manual(self):
        for corrida in (self.manual, self.gps):
            url = reverse("workouts:corrida_excluir", args=[corrida.pk])
            html = self.client.get(url).content.decode()
            self.assertIn("Excluir esta corrida", html)
            self.assertIn("Cancelar", html)
            self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 0)
