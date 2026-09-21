"""Bloco 4 — privacidade.

A propriedade que atravessa tudo: recusar o rastreio NÃO apaga o evento — ele
continua contando no agregado ANÔNIMO —; o que para é a atribuição à pessoa.
Duas fontes de recusa (DNT e o opt-out do perfil), as duas lidas SEM consulta.
"""
from django.test import TestCase
from django.urls import reverse

from plans import services
from plans.tests import CatalogFixture, create_complete_user

from .models import Event


class OptOutTests(CatalogFixture):
    def setUp(self):
        self.pessoa = create_complete_user(email="priv@exemplo.com")
        services.create_plan(self.pessoa)
        self.client.force_login(self.pessoa)
        # Em uso real o analytics.js já pôs o cookie de primeira parte antes de
        # qualquer ação; aqui o simulamos para ver o anon_id sobreviver ao opt-out.
        self.client.cookies["np_aid"] = "anon-teste"

    def _agua(self):
        self.client.post("/agua/", {"ml": "250"})
        return Event.objects.get(name="agua.registrada")

    def test_por_padrao_o_evento_e_atribuido(self):
        self.assertEqual(self._agua().user, self.pessoa)

    def test_opt_out_mantem_o_evento_anonimo_mas_conta(self):
        self.client.post(reverse("accounts:rastreio"), {})  # checkbox desmarcado
        self.pessoa.profile.refresh_from_db()
        self.assertFalse(self.pessoa.profile.rastrear_uso)
        evento = self._agua()
        self.assertIsNone(evento.user)              # não é da pessoa
        self.assertEqual(evento.anon_id, "anon-teste")  # anônimo, mas conta no agregado

    def test_permitir_de_novo_volta_a_atribuir(self):
        self.client.post(reverse("accounts:rastreio"), {})
        self.client.post(reverse("accounts:rastreio"), {"rastrear_uso": "1"})
        self.assertEqual(self._agua().user, self.pessoa)

    def test_dnt_tambem_mantem_anonimo(self):
        self.client.post("/agua/", {"ml": "250"}, HTTP_DNT="1")
        self.assertIsNone(Event.objects.get(name="agua.registrada").user)


class LoginCarregaOptOutTests(TestCase):
    def test_o_login_leva_o_opt_out_para_a_sessao(self):
        from analytics.privacidade import CHAVE_SEM_RASTREIO
        from analytics.identidade import _costura_no_login
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory
        from django.contrib.sessions.backends.db import SessionStore

        User = get_user_model()
        u = create_complete_user_min(User)
        u.profile.rastrear_uso = False
        u.profile.save(update_fields=["rastrear_uso"])

        req = RequestFactory().get("/")
        req.session = SessionStore()
        _costura_no_login(sender=User, request=req, user=u)
        self.assertTrue(req.session.get(CHAVE_SEM_RASTREIO))


class PaginaTests(TestCase):
    def test_privacidade_explica_o_analytics_e_a_base_legal(self):
        html = self.client.get(reverse("privacidade")).content.decode()
        self.assertIn("Análise de uso", html)
        self.assertIn("leg", html.lower())  # legítimo interesse
        self.assertIn("13.709", html)  # a LGPD citada
        self.assertIn("Do-Not-Track", html)


def create_complete_user_min(User):
    from plans.tests import create_complete_user
    return create_complete_user(email="loginopt@exemplo.com")
