# -*- coding: utf-8 -*-
"""O consentimento pendente leva "com volta" (achado 2 da revisão de
28/09/2026, Task F, Parte 2).

Antes: `OnboardingRequiredMixin.dispatch` mandava para `accounts:consentimento`
sem dizer de onde a pessoa veio, e `ConsentimentoView` sempre devolvia para
`plans:today` depois de consentir — quem tentava `/treino/corridas/` (ou
qualquer outra tela atrás do mixin) acabava na Home, não de volta para onde
estava indo. Agora o redirecionamento carrega `?next=`, e o `POST`/`GET` da
tela de consentimento honram um `next` SEGURO (mesmo host, mesmo padrão que
`django.contrib.auth`'s `RedirectURLMixin` já usa para o login) — um `next`
de outro domínio ou esquema estranho é ignorado, e a régua cai no padrão.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Consentimento, Profile, User
from accounts.test_tres_etapas import ETAPA1_SEM_CAIXAS, ETAPA2, ETAPA3, etapa

#: As três caixas do onboarding (etapa 1), com os dados demográficos que o
#: formulário dessa etapa também exige.
ETAPA1 = {**ETAPA1_SEM_CAIXAS, "termos": "on", "saude": "on", "transferencia": "on"}
#: `ConsentimentoForm` só tem as três caixas — nenhum dado demográfico.
TRES = {"termos": "on", "saude": "on", "transferencia": "on"}


class ComVoltaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def _completa_sem_consentimento(self, email="volta@exemplo.com"):
        """O mesmo estado de `accounts.test_consentimento::_completa_sem_consentimento`:
        onboarding terminado, e depois desconsentida — o que `precisa_consentir`
        marca em toda conta que existia antes dos legais."""
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        self.client.force_login(user)
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        self.client.post(etapa(3), ETAPA3)
        Consentimento.objects.filter(user=user).delete()
        Profile.objects.filter(user=user).update(consentimento_versao="", precisa_consentir=True)
        return user

    def test_o_redirecionamento_do_mixin_carrega_o_next(self):
        """`workouts:corridas` usa `OnboardingRequiredMixin` desde a Task F
        (item 11) — a mesma tela cujo redirecionamento este achado cobre."""
        self._completa_sem_consentimento()
        alvo = reverse("workouts:corridas")
        resposta = self.client.get(alvo)
        esperado = "%s?next=%s" % (reverse("accounts:consentimento"), alvo)
        self.assertRedirects(resposta, esperado, fetch_redirect_response=False)

    def test_a_tela_de_consentimento_guarda_o_next_num_campo_escondido(self):
        self._completa_sem_consentimento()
        alvo = reverse("workouts:corridas")
        html = self.client.get(
            "%s?next=%s" % (reverse("accounts:consentimento"), alvo)
        ).content.decode()
        self.assertIn('name="next" value="%s"' % alvo, html)

    def test_consentir_com_next_seguro_volta_para_a_tela_certa(self):
        self._completa_sem_consentimento()
        alvo = reverse("workouts:corridas")
        resposta = self.client.post(reverse("accounts:consentimento"), {**TRES, "next": alvo})
        self.assertRedirects(resposta, alvo, fetch_redirect_response=False)

    def test_consentir_sem_next_continua_indo_para_o_dia(self):
        """Controle positivo: nenhum `next` não pode virar um erro nem um
        redirecionamento vazio — o padrão de sempre continua valendo."""
        self._completa_sem_consentimento()
        resposta = self.client.post(reverse("accounts:consentimento"), TRES)
        self.assertRedirects(resposta, reverse("plans:today"), fetch_redirect_response=False)

    def test_next_de_outro_host_e_ignorado(self):
        self._completa_sem_consentimento()
        resposta = self.client.post(
            reverse("accounts:consentimento"),
            {**TRES, "next": "https://evil.example.com/roubado"},
        )
        self.assertRedirects(resposta, reverse("plans:today"), fetch_redirect_response=False)

    def test_next_com_esquema_javascript_e_ignorado(self):
        self._completa_sem_consentimento()
        resposta = self.client.post(
            reverse("accounts:consentimento"),
            {**TRES, "next": "javascript:alert(1)"},
        )
        self.assertRedirects(resposta, reverse("plans:today"), fetch_redirect_response=False)

    def test_next_protocol_relative_e_ignorado(self):
        """`//evil.example.com/roubado` não tem esquema, mas troca de host —
        é o caso clássico que `url_has_allowed_host_and_scheme` existe para
        pegar, e que uma checagem ingênua (só olhar o esquema) deixaria passar."""
        self._completa_sem_consentimento()
        resposta = self.client.post(
            reverse("accounts:consentimento"),
            {**TRES, "next": "//evil.example.com/roubado"},
        )
        self.assertRedirects(resposta, reverse("plans:today"), fetch_redirect_response=False)

    def test_next_relativo_sem_barra_nao_estoura_no_redirect(self):
        """M1 da re-revisão de 28/09/2026: `_next_seguro` aceita um `next`
        relativo sem `/` nem `.` (mesmo host — não é o caso dos testes acima,
        que testam o HOST). `redirect(proximo)` cru passava isso para
        `resolve_url`, que tentava `reverse()` como se fosse nome de rota e
        estourava `NoReverseMatch` — um 500 depois do consentimento JÁ
        GRAVADO (`caixas.registrar` roda antes do redirecionamento). Os três
        casos que a revisão reproduziu com `redirect("foo")`,
        `redirect("?x=1")` e `redirect("#topo")`."""
        self._completa_sem_consentimento()
        for proximo in ("foo", "?x=1", "#topo"):
            with self.subTest(next=proximo):
                resposta = self.client.post(
                    reverse("accounts:consentimento"), {**TRES, "next": proximo}
                )
                self.assertEqual(resposta.status_code, 302)
                self.assertEqual(resposta["Location"], proximo)
