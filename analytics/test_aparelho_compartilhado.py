# -*- coding: utf-8 -*-
"""Duas falhas de LGPD da revisão final de 28/09/2026, as duas de APARELHO.

I-1 — navegador compartilhado. O cookie `np_aid` dura dois anos e atravessa
logout. Evento de pessoa LOGADA que não fica com ela (DNT, ou
`evento_anonimo` como `conta.excluida`) era gravado com `user=NULL` e o
`anon_id` do aparelho; no próximo login naquele navegador, o `alias` o dava
a OUTRA pessoa — e a exportação o entregava como "seus dados". Hoje essas
linhas nascem com `anon_id=""`: contam no agregado e ninguém as costura.

I-A — segundo aparelho. O opt-out vivia só na sessão onde a pessoa o
desligou; a sessão do celular seguia gravando eventos identificados. O
`OnboardingRequiredMixin` sincroniza o flag com o perfil que já carrega."""
from django.contrib.auth.signals import user_logged_in
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from accounts.forms import PALAVRA_DE_EXCLUSAO
from analytics.identidade import COOKIE_ANON
from analytics.models import Event
from analytics.tests import corpo
from plans.tests import create_complete_user

APARELHO = "aparelho-da-familia"


def _login_de(user, anon=APARELHO):
    """O `user_logged_in` de um login de verdade naquele navegador: é ele que
    roda o `alias` com o cookie do aparelho."""
    req = RequestFactory().get("/")
    req.COOKIES[COOKIE_ANON] = anon
    user_logged_in.send(sender=user.__class__, request=req, user=user)


class ONavegadorCompartilhadoNaoPassaEventoAdianteTests(TestCase):
    def setUp(self):
        self.b = create_complete_user(email="b-dnt@exemplo.com")
        self.a = create_complete_user(email="a-depois@exemplo.com")
        self.client.cookies[COOKIE_ANON] = APARELHO
        self.client.force_login(self.b)

    def test_evento_do_servidor_com_dnt_nasce_sem_anon_id_e_nao_vai_para_a(self):
        self.client.post(reverse("plans:log_hydration"),
                         {"ml": "250", "de": "topo"}, HTTP_DNT="1")
        linhas = Event.objects.filter(name="agua.registrada")
        self.assertTrue(linhas.exists())
        self.assertEqual(list(linhas.values_list("user", "anon_id")), [(None, "")] * linhas.count())

        self.client.logout()
        _login_de(self.a)
        self.assertEqual(Event.objects.filter(user=self.a).count(), 0)

    def test_ingestao_com_dnt_nasce_sem_anon_id_e_nao_vai_para_a(self):
        self.client.post(reverse("analytics:ingest"),
                         data=corpo([{"name": "agua.registrada"}]),
                         content_type="text/plain", HTTP_DNT="1")
        e = Event.objects.get()
        self.assertEqual((e.user, e.anon_id), (None, ""))

        self.client.logout()
        _login_de(self.a)
        self.assertEqual(Event.objects.filter(user=self.a).count(), 0)

    def test_conta_excluida_conta_no_agregado_sem_anon_id(self):
        self.client.post(reverse("accounts:excluir_conta"),
                         {"confirmacao": PALAVRA_DE_EXCLUSAO, "senha": "senha-bem-forte-123"})
        e = Event.objects.get(name="conta.excluida")
        self.assertEqual((e.user, e.anon_id), (None, ""))

        _login_de(self.a)
        self.assertEqual(Event.objects.filter(user=self.a).count(), 0)

    def test_controle_positivo_visitante_anonimo_e_costurado_no_proprio_login(self):
        anonimo = Client()
        anonimo.cookies[COOKIE_ANON] = "aparelho-do-visitante"
        anonimo.post(reverse("analytics:ingest"),
                     data=corpo([{"name": "tela.vista"}]), content_type="text/plain")
        self.assertEqual(Event.objects.get().anon_id, "aparelho-do-visitante")

        _login_de(self.a, anon="aparelho-do-visitante")
        self.assertEqual(Event.objects.get().user, self.a)


class OOptOutValeNoOutroAparelhoTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="dois-aparelhos@exemplo.com")
        self.notebook, self.celular = Client(), Client()
        self.notebook.force_login(self.user)
        self.celular.force_login(self.user)

    def test_desligar_no_notebook_para_o_celular_na_proxima_tela(self):
        self.notebook.post(reverse("accounts:rastreio"), {"rastrear_uso": "0"})
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.rastrear_uso)

        self.celular.get(reverse("plans:today"))
        self.celular.post(reverse("plans:log_hydration"), {"ml": "250", "de": "topo"})
        self.assertEqual(Event.objects.filter(user=self.user).count(), 0)

    def test_controle_positivo_religar_volta_a_gravar_no_celular(self):
        self.notebook.post(reverse("accounts:rastreio"), {"rastrear_uso": "0"})
        self.celular.get(reverse("plans:today"))
        self.notebook.post(reverse("accounts:rastreio"), {"rastrear_uso": "1"})
        self.celular.get(reverse("plans:today"))
        self.celular.post(reverse("plans:log_hydration"), {"ml": "250", "de": "topo"})
        self.assertGreater(Event.objects.filter(user=self.user).count(), 0)
