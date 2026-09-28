# -*- coding: utf-8 -*-
"""Histórico e salvar corrida pedem consentimento em dia (28/09/2026, Parte 2, item 11).

`HistoricoDeCorridasView` e `SalvarCorridaView` eram as DUAS ÚNICAS views de
`corrida_views.py` sem `OnboardingRequiredMixin` — todas as outras (form
manual, importação de arquivo, edição, exclusão, plano, aparelho) já exigem
onboarding completo e consentimento em dia. Nestas duas dava para ver o
histórico e GRAVAR uma corrida nova — dado de saúde — com uma versão de
consentimento vencida. Achado no mapa de auditoria de 27/09
(`.superpowers/sdd/2026-09-28-parte-2/parte2-mapa.md`, item 11).
"""
import json

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.consentimento import VERSAO_DOS_LEGAIS
from accounts.models import Profile
from workouts.models import Corrida
from workouts.tests import create_user


def _sem_reconsentir(user):
    """Marca o perfil como quem consentiu uma versão ANTERIOR dos legais —
    o estado real de uma conta que passou pelo cadastro antes de uma versão
    nova subir. `create_user` deixa `consentimento_versao=""`, que é o
    perfil de FIXTURE (não barrado, ver `accounts.test_consentimento`); aqui
    o valor precisa ser verdadeiro e diferente do vigente para acionar
    `deve_consentir`."""
    Profile.objects.filter(user=user).update(consentimento_versao="2020-01-01")


class CorridaExigeConsentimentoEmDiaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(email="corrida-consentimento@exemplo.com")
        self.client.force_login(self.user)

    def test_o_historico_de_corridas_redireciona_quem_nao_reconsentiu(self):
        """ALTERADO em 28/09/2026 (achado 2 da revisão): o redirecionamento
        agora carrega `?next=`, "com volta" — como o brief pedia."""
        _sem_reconsentir(self.user)
        alvo = reverse("workouts:corridas")
        resposta = self.client.get(alvo)
        esperado = "%s?next=%s" % (reverse("accounts:consentimento"), alvo)
        self.assertRedirects(resposta, esperado, fetch_redirect_response=False)

    def test_o_historico_de_corridas_abre_para_quem_esta_em_dia(self):
        Profile.objects.filter(user=self.user).update(consentimento_versao=VERSAO_DOS_LEGAIS)
        self.assertEqual(self.client.get(reverse("workouts:corridas")).status_code, 200)

    def test_salvar_corrida_redireciona_quem_nao_reconsentiu_em_vez_de_gravar(self):
        """Hoje a view devolve JSON 200 mesmo sem consentimento em dia — o
        mixin troca isso por um redirect, como as outras telas de saúde, e a
        corrida não pode ser gravada por quem está com o consentimento
        vencido."""
        _sem_reconsentir(self.user)
        payload = {
            "op_id": "corrida-sem-consentimento",
            "comecou_em": "2026-09-28T08:00:00Z",
            "terminou_em": "2026-09-28T08:30:00Z",
            "distancia_m": 5000,
            "duracao_s": 1800,
        }
        alvo = reverse("workouts:salvar_corrida")
        resposta = self.client.post(alvo, data=json.dumps(payload), content_type="application/json")
        esperado = "%s?next=%s" % (reverse("accounts:consentimento"), alvo)
        self.assertRedirects(resposta, esperado, fetch_redirect_response=False)
        self.assertFalse(Corrida.objects.filter(op_id="corrida-sem-consentimento").exists())

    def test_salvar_corrida_grava_para_quem_esta_em_dia(self):
        Profile.objects.filter(user=self.user).update(consentimento_versao=VERSAO_DOS_LEGAIS)
        payload = {
            "op_id": "corrida-com-consentimento",
            "comecou_em": "2026-09-28T08:00:00Z",
            "terminou_em": "2026-09-28T08:30:00Z",
            "distancia_m": 5000,
            "duracao_s": 1800,
        }
        resposta = self.client.post(
            reverse("workouts:salvar_corrida"), data=json.dumps(payload), content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(Corrida.objects.filter(op_id="corrida-com-consentimento").exists())
