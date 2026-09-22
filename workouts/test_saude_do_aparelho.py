"""O que o app instalado importa do Apple Saúde / Health Connect (Fase 2 da
missão Capacitor, 22/09/2026): corridas e pesagens. A LEITURA acontece no
aparelho (plugin `capacitor-health`, `static/js/nativo.js`); o servidor só
recebe o que a pessoa mandou importar, e aplica a MESMA régua das corridas
de arquivo (distância mínima, velocidade impossível) e a mesma unicidade
das pesagens (uma por dia; a do aparelho nunca sobrescreve a que a pessoa
digitou).

Idempotente pelo identificador do registro no aparelho: importar de novo
não duplica — a corrida entra com `Origem.APARELHO`, que não se edita
(como GPS e arquivo), e o `op_id` é `aparelho:<id>`.
"""
import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import WeightEntry
from plans.tests import create_complete_user
from workouts.models import Corrida


def _corrida(id_="hk-1", minutos_atras=120, distancia_m=5200, duracao_s=1830, tipo="running"):
    fim = timezone.now() - timedelta(minutes=minutos_atras)
    inicio = fim - timedelta(seconds=duracao_s)
    return {"id": id_, "comecou_em": inicio.isoformat(), "terminou_em": fim.isoformat(),
            "distancia_m": distancia_m, "duracao_s": duracao_s, "tipo": tipo, "fonte": "Apple Watch"}


class ImportarCorridasDoAparelhoTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="app@exemplo.com")
        self.client.force_login(self.user)
        self.url = reverse("workouts:corridas_do_aparelho")

    def _post(self, corridas):
        return self.client.post(self.url, json.dumps({"corridas": corridas}), content_type="application/json")

    def test_importa_uma_corrida_com_origem_aparelho(self):
        resposta = self._post([_corrida()])
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"importadas": 1, "repetidas": 0, "recusadas": 0})
        corrida = Corrida.objects.get(user=self.user)
        self.assertEqual(corrida.origem, Corrida.Origem.APARELHO)
        self.assertEqual(corrida.distancia_m, 5200)
        self.assertEqual(corrida.duracao_s, 1830)
        self.assertEqual(corrida.op_id, "aparelho:hk-1")

    def test_importar_de_novo_nao_duplica(self):
        self._post([_corrida()])
        resposta = self._post([_corrida()])
        self.assertEqual(resposta.json()["repetidas"], 1)
        self.assertEqual(Corrida.objects.count(), 1)

    def test_a_regua_das_corridas_de_arquivo_vale_aqui(self):
        """Aparelho parado (10 m) e velocidade impossível são recusados, e
        a resposta diz quantos — sem gravar linha morta."""
        resposta = self._post([_corrida(id_="parado", distancia_m=10), _corrida(id_="jato", distancia_m=50_000, duracao_s=600)])
        self.assertEqual(resposta.json()["recusadas"], 2)
        self.assertFalse(Corrida.objects.exists())

    def test_so_corrida_entra_como_corrida(self):
        resposta = self._post([_corrida(id_="bike", tipo="cycling")])
        self.assertEqual(resposta.json()["recusadas"], 1)
        self.assertFalse(Corrida.objects.exists())

    def test_identificador_comprido_cabe_no_op_id(self):
        resposta = self._post([_corrida(id_="x" * 200)])
        self.assertEqual(resposta.json()["importadas"], 1)
        self.assertLessEqual(len(Corrida.objects.get().op_id), 64)

    def test_corpo_invalido_e_400_e_anonimo_nao_entra(self):
        self.assertEqual(self.client.post(self.url, "nao é json", content_type="application/json").status_code, 400)
        self.client.logout()
        self.assertIn(self._post([_corrida()]).status_code, (302, 403))

    def test_a_corrida_do_aparelho_nao_se_edita(self):
        self._post([_corrida()])
        corrida = Corrida.objects.get()
        self.assertEqual(self.client.get(reverse("workouts:corrida_editar", args=[corrida.pk])).status_code, 404)


class ImportarPesagensDoAparelhoTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="app@exemplo.com")
        self.client.force_login(self.user)
        self.url = reverse("accounts:peso_do_aparelho")

    def _post(self, pesagens):
        return self.client.post(self.url, json.dumps({"pesagens": pesagens}), content_type="application/json")

    # O cadastro já grava a pesagem de HOJE; o dia livre é ontem.
    def test_grava_a_pesagem_do_dia_que_nao_tinha(self):
        ontem = timezone.localdate() - timedelta(days=1)
        resposta = self._post([{"data": ontem.isoformat(), "peso_kg": 81.4}])
        self.assertEqual(resposta.json(), {"gravadas": 1, "ja_tinha": 0, "recusadas": 0})
        self.assertEqual(WeightEntry.objects.get(user=self.user, date=ontem).weight_kg, Decimal("81.4"))

    def test_nunca_sobrescreve_o_que_a_pessoa_digitou(self):
        ontem = timezone.localdate() - timedelta(days=1)
        WeightEntry.objects.create(user=self.user, date=ontem, weight_kg=Decimal("80.0"))
        resposta = self._post([{"data": ontem.isoformat(), "peso_kg": 81.4}])
        self.assertEqual(resposta.json()["ja_tinha"], 1)
        self.assertEqual(WeightEntry.objects.get(user=self.user, date=ontem).weight_kg, Decimal("80.0"))

    def test_peso_fora_do_humano_e_recusado(self):
        ontem = timezone.localdate() - timedelta(days=1)
        resposta = self._post([{"data": ontem.isoformat(), "peso_kg": 2}, {"data": ontem.isoformat(), "peso_kg": 900}])
        self.assertEqual(resposta.json()["recusadas"], 2)
        self.assertFalse(WeightEntry.objects.filter(user=self.user, date=ontem).exists())

    def test_data_futura_e_recusada(self):
        amanha = timezone.localdate() + timedelta(days=1)
        resposta = self._post([{"data": amanha.isoformat(), "peso_kg": 81.4}])
        self.assertEqual(resposta.json()["recusadas"], 1)
