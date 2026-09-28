# -*- coding: utf-8 -*-
"""O opt-out (`Profile.rastrear_uso` desligado) bloqueia o evento INTEIRO de
quem está logado — antes só anonimizava (`pode_identificar`) e a linha
continuava gravando com `anon_id`. Decisão 2 do plano de 28/09/2026: quem
desligou o rastreio na sessão não quer NENHUMA linha, nem anônima.

O DNT continua sendo o caminho de "conta no agregado, mas sem me
identificar" — ele não passa por `pode_registrar`, só por `pode_identificar`
(`analytics/tests.py::test_dnt_mantem_o_evento_anonimo_mesmo_logado` prende
isso). Visitante anônimo (sem sessão de opt-out) continua contando.

I1 (revisão de 28/09/2026): o `alias` do login também precisa respeitar o
opt-out — sem a guarda, uma pessoa que navegou anônima e depois desligou o
rastreio (ou já tinha desligado) recebia o histórico anônimo COSTURADO a si
no próximo login, o oposto de "zero linha sobre a pessoa" que o opt-out
promete. `OAliasNaoIdentificaQuemDesligouTests`, abaixo, prende isso."""
from django.contrib.auth.signals import user_logged_in
from django.test import RequestFactory, TestCase
from django.urls import reverse

from analytics.identidade import COOKIE_ANON
from analytics.models import Event
from analytics.privacidade import CHAVE_SEM_RASTREIO
from analytics.tests import corpo
from plans.tests import create_complete_user


class OOptOutBloqueiaTudoTests(TestCase):
    """Toggle desligado = nenhuma linha de Event, nem anônima."""

    def setUp(self):
        self.user = create_complete_user(email="optout@exemplo.com")
        self.client.force_login(self.user)

    def _desligar(self):
        # Perfil E sessão: desde I-A (28/09/2026) o `OnboardingRequiredMixin`
        # ressincroniza a sessão com o perfil, que é a fonte da verdade.
        self.user.profile.rastrear_uso = False
        self.user.profile.save(update_fields=["rastrear_uso"])
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

    def test_a_ingestao_grava_com_toggle_ligado(self):  # controle positivo (M2)
        """Sem este controle, um corpo que o parser descartasse em silêncio
        também daria zero linhas — o teste acima passaria pelo motivo
        errado. Este prova que o MESMO corpo grava quando o toggle está
        ligado."""
        r = self.client.post(
            reverse("analytics:ingest"),
            data=corpo([{"name": "agua.registrada"}]),
            content_type="text/plain",
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(Event.objects.count(), 1)


class OAliasNaoIdentificaQuemDesligouTests(TestCase):
    """I1: o `alias` do login não pode costurar histórico anônimo à pessoa
    que já desligou o rastreio (ou manda DNT) — senão o opt-out vira
    ATRIBUIÇÃO em vez de zero linha, pior do que o estado que ele promete
    evitar."""

    def _evento_anonimo(self):
        self.client.post(
            reverse("analytics:ingest"),
            data=corpo([{"name": "tela.vista"}]),
            content_type="text/plain",
        )
        return Event.objects.get().anon_id

    def test_pessoa_que_desligou_nao_tem_o_historico_costurado(self):
        anon = self._evento_anonimo()
        user = create_complete_user(email="desligou-alias@exemplo.com")
        user.profile.rastrear_uso = False
        user.profile.save(update_fields=["rastrear_uso"])

        req = RequestFactory().get("/")
        req.COOKIES[COOKIE_ANON] = anon
        user_logged_in.send(sender=user.__class__, request=req, user=user)

        self.assertIsNone(Event.objects.get(anon_id=anon).user)

    def test_dnt_tambem_impede_o_alias(self):
        anon = self._evento_anonimo()
        user = create_complete_user(email="dnt-alias@exemplo.com")

        req = RequestFactory().get("/", HTTP_DNT="1")
        req.COOKIES[COOKIE_ANON] = anon
        user_logged_in.send(sender=user.__class__, request=req, user=user)

        self.assertIsNone(Event.objects.get(anon_id=anon).user)

    def test_controle_positivo_pessoa_que_nao_desligou_tem_o_historico_costurado(self):
        anon = self._evento_anonimo()
        user = create_complete_user(email="ligou-alias@exemplo.com")

        req = RequestFactory().get("/")
        req.COOKIES[COOKIE_ANON] = anon
        user_logged_in.send(sender=user.__class__, request=req, user=user)

        self.assertEqual(Event.objects.get(anon_id=anon).user, user)
