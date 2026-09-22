# -*- coding: utf-8 -*-
"""Os avisos por e-mail: preferência, envio, jobs e descadastro.

O que estes testes guardam, e o caso que motivou cada guarda:

- e-mail sai UMA vez por chave (`EmailEnviado` é a constraint): o job roda de
  5 em 5 minutos e duas vezes por engano, como o de push;
- quem desligou o tipo não recebe, e quem nunca abriu a tela recebe (o padrão
  é ligado — a preferência que não existe não é "desligado");
- o descadastro é por LINK com chave própria, sem login, GET e POST, porque o
  cliente de e-mail abre por GET e o "One-Click" (RFC 8058) manda POST;
- o boas-vindas sai no cadastro por senha E por Google, e nunca derruba o
  cadastro quando o SMTP falha.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, WeightEntry
from plans.models import HydrationLog
from plans.tests import create_complete_user
from workouts.models import Exercise, ExerciseLog, MuscleGroup, Padrao, Split, TrainingPlan

from . import jobs, services
from . import brevo
from .models import EmailAberto, EmailBloqueado, EmailEnviado, Preferencia, TipoDeEmail


def _plano(user):
    return TrainingPlan.objects.create(user=user, split=Split.ABC, days_per_week=3)


def _exercicio():
    return Exercise.objects.create(
        name="Supino reto com barra", muscle_group=MuscleGroup.CHEST,
        padrao=Padrao.PRESSAO_DE_PEITO, equipment="barbell", is_compound=True,
    )


def _serie(user, dia, exercicio=None, numero=1):
    return ExerciseLog.objects.create(
        user=user, exercise=exercicio or _exercicio(), date=dia,
        set_number=numero, reps=8, weight_kg=Decimal("40"),
    )


def _agora(y, m, d, h=9, mi=0):
    return timezone.make_aware(datetime(y, m, d, h, mi))


class PreferenciaTests(TestCase):
    def test_a_preferencia_que_nao_existe_e_ligada(self):
        """Ninguém precisa abrir a tela para receber: o padrão é receber."""
        user = create_complete_user()

        pref = Preferencia.de(user)

        self.assertTrue(pref.email_inatividade)
        self.assertTrue(pref.email_resumo_semanal)
        self.assertTrue(pref.push_refeicoes)
        self.assertEqual(pref.hora_email, time(8, 0))
        self.assertEqual(len(pref.chave), 32)

    def test_a_chave_de_descadastro_e_propria_de_cada_pessoa(self):
        a = Preferencia.de(create_complete_user("a@exemplo.com"))
        b = Preferencia.de(create_complete_user("b@exemplo.com"))

        self.assertNotEqual(a.chave, b.chave)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   NUTRIPLAN_URL_BASE="https://app.exemplo")
class EnvioTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()

    def test_boas_vindas_sai_com_html_texto_e_link_de_descadastro(self):
        resultado = services.boas_vindas(self.user)

        self.assertEqual(resultado, "enviado")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [self.user.email])
        self.assertIn("NutriPlan", msg.subject)
        self.assertEqual(msg.alternatives[0][1], "text/html")
        chave = Preferencia.de(self.user).chave
        self.assertIn(f"https://app.exemplo/avisos/sair/{chave}/", msg.body)
        self.assertIn(f"https://app.exemplo/avisos/sair/{chave}/", msg.alternatives[0][0])
        self.assertIn("List-Unsubscribe", msg.extra_headers)
        self.assertEqual(msg.extra_headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")

    def test_boas_vindas_nao_sai_duas_vezes(self):
        """O cadastro pode ser reenviado, o adapter pode ser chamado de novo:
        a chave `conta` só passa uma vez pela constraint."""
        services.boas_vindas(self.user)
        resultado = services.boas_vindas(self.user)

        self.assertEqual(resultado, "pulado")
        self.assertEqual(len(mail.outbox), 1)

    def test_endereco_invalid_nao_recebe_boas_vindas_nem_ganha_linha(self):
        """O E2E noturno cadastra `qa-e2e-…@nutriplan.invalid` e o boas-vindas
        saía: 19 soft bounces num dia no Brevo (21/09/2026). `enviar()` é a
        porta única, então o "pulado" vale para os três tipos."""
        self.user.email = "qa-e2e-lote@nutriplan.invalid"
        self.user.save()

        self.assertEqual(services.boas_vindas(self.user), "pulado")
        self.assertEqual(mail.outbox, [])
        self.assertFalse(EmailEnviado.objects.filter(user=self.user).exists())

    def test_falha_de_smtp_fica_no_log_e_nao_estoura(self):
        with patch("avisos.services.EmailMultiAlternatives.send", side_effect=OSError("smtp caiu")):
            resultado = services.boas_vindas(self.user)

        self.assertEqual(resultado, "falhou")
        registro = EmailEnviado.objects.get(user=self.user, tipo=TipoDeEmail.BOAS_VINDAS)
        self.assertFalse(registro.sucesso)
        self.assertIn("smtp caiu", registro.erro)

    def test_o_nome_da_pessoa_nunca_entra_cru_no_html(self):
        """O e-mail de senha já pagou por isso (B13, 16/09/2026): o nome é
        cadastrável por qualquer um e o HTML sai do remetente oficial."""
        self.user.first_name = "<b>x</b>"
        self.user.save()

        services.boas_vindas(self.user)

        html = mail.outbox[0].alternatives[0][0]
        self.assertNotIn("<b>x</b>", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   NUTRIPLAN_URL_BASE="https://app.exemplo")
class InatividadeTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()
        _plano(self.user)
        self.exercicio = _exercicio()
        # Os e-mails do relógio só saem para caixa PROVADA (abriu algum
        # e-mail nosso) — a régua de 21/09/2026.
        EmailAberto.objects.create(email=self.user.email)

    def test_cinco_dias_sem_serie_recebe_um_email(self):
        _serie(self.user, date(2026, 9, 16), self.exercicio)

        resumo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("5 dias", mail.outbox[0].subject)
        self.assertIn("16/09", mail.outbox[0].body)

    def test_quatro_dias_ainda_nao(self):
        _serie(self.user, date(2026, 9, 17), self.exercicio)

        resumo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_um_email_por_pausa_e_nao_um_por_dia(self):
        """Seis dias parado é a MESMA pausa de cinco: a chave é a data da
        última série, então o segundo dia do job não manda de novo."""
        _serie(self.user, date(2026, 9, 16), self.exercicio)
        jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        resumo = jobs.rodar_inatividade(_agora(2026, 9, 22, 8, 5))

        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_treinar_de_novo_abre_uma_pausa_nova(self):
        _serie(self.user, date(2026, 9, 10), self.exercicio)
        jobs.rodar_inatividade(_agora(2026, 9, 15, 8, 5))
        _serie(self.user, date(2026, 9, 16), self.exercicio)

        resumo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_endereco_invalid_nunca_recebe_nem_inatividade_nem_resumo(self):
        """`.invalid` é domínio reservado (RFC 2606): o Carlos do demo e a conta
        de QA moram lá. Medido no staging em 21/09/2026: o resumo da semana
        SAIU para o Carlos — bounce no Brevo toda segunda. O job não escreve
        para quem não existe, e a régua é a TERMINAÇÃO do e-mail, não o nome."""
        demo = create_complete_user(email="carlos.demo@nutriplan.invalid")
        _plano(demo)
        EmailAberto.objects.create(email=demo.email)
        User.objects.filter(pk__in=(demo.pk, self.user.pk)).update(date_joined=_agora(2026, 9, 10))

        inatividade = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))
        resumo = jobs.rodar_resumo_semanal(_agora(2026, 9, 21, 8, 5))

        self.assertEqual((inatividade["enviados"], resumo["enviados"]), (1, 1), "só a conta de verdade")
        self.assertEqual({m.to[0] for m in mail.outbox}, {self.user.email})

    def test_quem_nunca_treinou_conta_do_cadastro(self):
        User.objects.filter(pk=self.user.pk).update(date_joined=_agora(2026, 9, 14))

        resumo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 1)

    def test_antes_da_hora_escolhida_espera(self):
        _serie(self.user, date(2026, 9, 10), self.exercicio)
        pref = Preferencia.de(self.user)
        pref.hora_email = time(18, 0)
        pref.save()

        cedo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))
        tarde = jobs.rodar_inatividade(_agora(2026, 9, 21, 18, 10))

        self.assertEqual((cedo["enviados"], tarde["enviados"]), (0, 1))

    def test_quem_desligou_nao_recebe(self):
        _serie(self.user, date(2026, 9, 10), self.exercicio)
        pref = Preferencia.de(self.user)
        pref.email_inatividade = False
        pref.save()

        resumo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_sem_ficha_ativa_nao_ha_o_que_cobrar(self):
        TrainingPlan.objects.filter(user=self.user).update(is_active=False)

        resumo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   NUTRIPLAN_URL_BASE="https://app.exemplo")
class ResumoSemanalTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()
        _plano(self.user)
        self.exercicio = _exercicio()
        EmailAberto.objects.create(email=self.user.email)
        # Semana de 14 a 20/09/2026 (segunda a domingo); o job roda na
        # segunda 21/09.
        _serie(self.user, date(2026, 9, 15), self.exercicio)
        _serie(self.user, date(2026, 9, 15), self.exercicio, numero=2)
        _serie(self.user, date(2026, 9, 18), self.exercicio)
        HydrationLog.objects.create(user=self.user, date=date(2026, 9, 15), ml=2000)
        HydrationLog.objects.create(user=self.user, date=date(2026, 9, 16), ml=1500)
        WeightEntry.objects.create(user=self.user, date=date(2026, 9, 13), weight_kg=Decimal("83.0"))
        WeightEntry.objects.create(user=self.user, date=date(2026, 9, 20), weight_kg=Decimal("82.2"))

    def test_na_segunda_sai_o_resumo_da_semana_anterior(self):
        resumo = jobs.rodar_resumo_semanal(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 1)
        msg = mail.outbox[0]
        self.assertIn("2 treinos", msg.subject)
        self.assertIn("3 séries", msg.subject)
        self.assertIn("Séries registradas: 3", msg.body)
        self.assertIn("82,2 kg", msg.body)
        self.assertIn("-0,8", msg.body)
        self.assertIn("3.500 ml", msg.body)
        self.assertEqual(EmailEnviado.objects.get(tipo=TipoDeEmail.RESUMO_SEMANAL).referencia, "2026-W38")

    def test_em_outro_dia_da_semana_nao_sai(self):
        resumo = jobs.rodar_resumo_semanal(_agora(2026, 9, 22, 8, 5))

        self.assertEqual(resumo["enviados"], 0)

    def test_a_mesma_semana_nao_sai_duas_vezes(self):
        jobs.rodar_resumo_semanal(_agora(2026, 9, 21, 8, 5))
        resumo = jobs.rodar_resumo_semanal(_agora(2026, 9, 21, 9, 5))

        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_quem_desligou_nao_recebe(self):
        pref = Preferencia.de(self.user)
        pref.email_resumo_semanal = False
        pref.save()

        resumo = jobs.rodar_resumo_semanal(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 0)

    def test_semana_vazia_ainda_sai_para_quem_tem_plano(self):
        """Zero é informação: quem tem plano e não registrou nada recebe o
        resumo dizendo isso — é o convite de voltar, não um silêncio."""
        ExerciseLog.objects.all().delete()
        HydrationLog.objects.all().delete()

        resumo = jobs.rodar_resumo_semanal(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 1)
        self.assertIn("0 treinos", mail.outbox[0].subject)


class DescadastroTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()
        self.pref = Preferencia.de(self.user)

    def test_o_link_do_email_desliga_o_tipo_sem_login(self):
        url = reverse("avisos:descadastro", kwargs={"chave": self.pref.chave}) + "?tipo=inatividade"

        resposta = self.client.get(url)

        self.assertEqual(resposta.status_code, 200)
        self.pref.refresh_from_db()
        self.assertFalse(self.pref.email_inatividade)
        self.assertTrue(self.pref.email_resumo_semanal)
        self.assertContains(resposta, "não vai mais receber")

    def test_o_post_de_um_clique_tambem_desliga(self):
        url = reverse("avisos:descadastro", kwargs={"chave": self.pref.chave})

        resposta = self.client.post(url, {"List-Unsubscribe": "One-Click", "tipo": "tudo"})

        self.assertEqual(resposta.status_code, 200)
        self.pref.refresh_from_db()
        self.assertFalse(self.pref.email_inatividade)
        self.assertFalse(self.pref.email_resumo_semanal)

    def test_chave_errada_e_404_e_nao_mexe_em_ninguem(self):
        resposta = self.client.get(reverse("avisos:descadastro", kwargs={"chave": "0" * 32}))

        self.assertEqual(resposta.status_code, 404)
        self.pref.refresh_from_db()
        self.assertTrue(self.pref.email_inatividade)


class TelaDePreferenciasTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)

    def test_exige_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("avisos:preferencias"))
        self.assertEqual(resposta.status_code, 302)

    def test_mostra_e_salva_as_escolhas(self):
        resposta = self.client.get(reverse("avisos:preferencias"))
        self.assertContains(resposta, "Avisos")

        resposta = self.client.post(reverse("avisos:preferencias"), {
            "emails": ["resumo"], "pushes": [], "hora_email": "19:30",
        })

        self.assertEqual(resposta.status_code, 302)
        pref = Preferencia.de(self.user)
        self.assertFalse(pref.email_inatividade)
        self.assertTrue(pref.email_resumo_semanal)
        self.assertFalse(pref.push_refeicoes)
        self.assertEqual(pref.hora_email, time(19, 30))

    def test_o_perfil_leva_a_tela(self):
        resposta = self.client.get(reverse("accounts:profile"))
        self.assertContains(resposta, reverse("avisos:preferencias"))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CadastroTests(TestCase):
    def test_criar_conta_por_senha_manda_o_boas_vindas(self):
        resposta = self.client.post(reverse("accounts:signup"), {
            "first_name": "Nova", "email": "nova@exemplo.com", "password1": "senha-bem-forte-123", "password2": "senha-bem-forte-123",
        })

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual([m.to for m in mail.outbox], [["nova@exemplo.com"]])

    def test_smtp_fora_do_ar_nao_derruba_o_cadastro(self):
        with patch("avisos.services.EmailMultiAlternatives.send", side_effect=OSError("smtp caiu")):
            resposta = self.client.post(reverse("accounts:signup"), {
                "first_name": "Nova", "email": "nova@exemplo.com", "password1": "senha-bem-forte-123", "password2": "senha-bem-forte-123",
            })

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(User.objects.filter(email="nova@exemplo.com").exists())


class PushRespeitaAPreferenciaTests(TestCase):
    def test_quem_desligou_o_push_de_refeicao_sai_da_rodada(self):
        from push.models import PushSubscription
        from push.services import due_slots
        from plans.models import MealSlot, NutritionPlan

        user = create_complete_user()
        plano = NutritionPlan.objects.create(
            user=user, weight_kg=Decimal("82"), height_cm=178, age_years=31, sex="M",
            activity_level="light", goal="cut", bmr_kcal=1800, tdee_kcal=2500,
            target_kcal=2100, protein_g=150, carb_g=240, fat_g=60,
        )
        MealSlot.objects.create(plan=plano, name="Almoço", category="main", time=time(12, 0), order=1,
                                target_kcal=600, target_protein_g=40, target_carb_g=60, target_fat_g=20)
        PushSubscription.objects.create(user=user, endpoint="https://push/x", p256dh_key="p", auth_key="a")
        agora = _agora(2026, 9, 21, 11, 50)
        self.assertEqual(due_slots(agora).count(), 1)

        pref = Preferencia.de(user)
        pref.push_refeicoes = False
        pref.save()

        self.assertEqual(due_slots(agora).count(), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   NUTRIPLAN_URL_BASE="https://app.exemplo")
class RegraDeEnvioTests(TestCase):
    """Quem recebe: endereço em que o Brevo não desistiu, e — nos e-mails do
    relógio — caixa provada. Medido em 21/09/2026: 46,6 % de hard bounce
    num dia, com gmail inventado no cadastro; é reputação de remetente."""

    def setUp(self):
        self.user = create_complete_user()
        _plano(self.user)
        self.exercicio = _exercicio()
        _serie(self.user, date(2026, 9, 16), self.exercicio)

    def test_endereco_bloqueado_nao_recebe_nada_nem_o_boas_vindas(self):
        EmailBloqueado.objects.create(email=self.user.email, motivo="hardBounce")

        self.assertEqual(services.boas_vindas(self.user), "pulado")
        resumo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 0)
        self.assertEqual(mail.outbox, [])
        self.assertFalse(EmailEnviado.objects.filter(user=self.user).exists(), "sem linha: a chave não é queimada")

    def test_o_bloqueio_nao_diferencia_maiusculas(self):
        EmailBloqueado.objects.create(email=self.user.email.lower(), motivo="hardBounce")
        self.user.email = self.user.email.upper()
        self.user.save()

        self.assertEqual(services.boas_vindas(self.user), "pulado")

    def test_caixa_nunca_provada_nao_recebe_os_emails_do_relogio(self):
        self.assertFalse(EmailAberto.objects.filter(email=self.user.email).exists())

        inatividade = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))
        semana = jobs.rodar_resumo_semanal(_agora(2026, 9, 21, 8, 5))

        self.assertEqual((inatividade["enviados"], semana["enviados"]), (0, 0))
        self.assertEqual(mail.outbox, [])
        self.assertFalse(EmailEnviado.objects.exists(), "pulado sem gravar linha: quando a caixa for provada, o e-mail sai")

    def test_o_boas_vindas_sai_sem_prova_porque_ele_e_a_prova(self):
        """É o primeiro contato: a abertura DELE é o que vira `EmailAberto`.
        Exigir prova antes seria nunca mandá-lo."""
        self.assertEqual(services.boas_vindas(self.user), "enviado")
        self.assertEqual(len(mail.outbox), 1)

    def test_quem_abriu_algum_email_recebe_os_do_relogio(self):
        EmailAberto.objects.create(email=self.user.email)

        resumo = jobs.rodar_inatividade(_agora(2026, 9, 21, 8, 5))

        self.assertEqual(resumo["enviados"], 1)

    def test_o_campo_de_verificacao_do_cadastro_vale_como_prova_quando_existir(self):
        """O contrato com a sessão de segurança (ledger, 21/09/2026):
        `email_verificado_em` no usuário. `verificado()` olha o campo antes
        da tabela — aqui simulado no objeto, porque o campo ainda não existe."""
        self.user.email_verificado_em = timezone.now()

        self.assertTrue(services.verificado(self.user))
        self.assertEqual(services.enviar(self.user, TipoDeEmail.INATIVIDADE, "x", {"dias": 5, "ultima": None, "nunca": True}), "enviado")


class SincronizacaoComOBrevoTests(TestCase):
    """`avisos.brevo` copia bloqueados e abertos por GET — e só GET."""

    PAGINA_BLOQUEADOS = {"contacts": [
        {"email": "Ainda@gmail.com", "reason": {"code": "hardBounce"}, "blockedAt": "2026-09-21T13:35:00.000+00:00"},
        {"email": "spam@exemplo.com", "reason": {"code": "contactFlaggedAsSpam"}, "blockedAt": "2026-09-20T10:00:00Z"},
    ], "count": 2}
    PAGINA_ABERTOS = {"events": [
        {"email": "QA@maildrop.cc", "event": "opened", "date": "2026-09-21T16:44:10.000+00:00"},
        {"email": "qa@maildrop.cc", "event": "opened", "date": "2026-09-21T16:44:00.000+00:00"},
    ]}

    def _falsa(self, chamadas):
        def _get(caminho, params):
            chamadas.append(("GET", caminho, params))
            return self.PAGINA_BLOQUEADOS if "blockedContacts" in caminho else self.PAGINA_ABERTOS
        return _get

    @override_settings(BREVO_API_KEY="chave-de-teste")
    def test_sincroniza_bloqueados_e_a_primeira_abertura_em_minusculas(self):
        chamadas = []
        with patch.object(brevo, "_get", self._falsa(chamadas)):
            resultado = brevo.sincronizar()

        self.assertEqual(resultado["bloqueados_novos"], 2)
        self.assertEqual(resultado["abertos_novos"], 1)
        self.assertEqual(EmailBloqueado.objects.get(email="ainda@gmail.com").motivo, "hardBounce")
        self.assertEqual(EmailAberto.objects.count(), 1, "QA@ e qa@ são a mesma caixa")
        self.assertEqual(EmailAberto.objects.get(email="qa@maildrop.cc").primeira_abertura.isoformat(), "2026-09-21T16:44:00+00:00")
        self.assertEqual({c[1] for c in chamadas}, {"/smtp/blockedContacts", "/smtp/statistics/events"})

    def test_sem_chave_nada_roda_e_nada_estoura(self):
        with override_settings(BREVO_API_KEY=""):
            self.assertEqual(brevo.sincronizar(), {"pulado": "BREVO_API_KEY ausente"})

    @override_settings(BREVO_API_KEY="chave-de-teste")
    def test_api_fora_do_ar_fica_no_log_e_nao_derruba_a_rodada(self):
        import urllib.error

        with patch.object(brevo, "_get", side_effect=urllib.error.URLError("fora")):
            resultado = brevo.sincronizar()

        self.assertIn("falhou", resultado)

    @override_settings(BREVO_API_KEY="chave-de-teste")
    def test_a_api_so_recebe_get_e_a_chave_vai_no_cabecalho(self):
        """Como `scripts/render_api.py`: leitura é leitura por construção."""
        pedidos = []

        class _Resposta:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"contacts": [], "events": []}'

        def _urlopen(pedido, timeout=0):
            pedidos.append(pedido)
            return _Resposta()

        with patch("avisos.brevo.urllib.request.urlopen", _urlopen):
            brevo.sincronizar()

        self.assertTrue(pedidos)
        self.assertEqual({p.get_method() for p in pedidos}, {"GET"})
        self.assertTrue(all(p.get_header("Api-key") == "chave-de-teste" for p in pedidos))
        self.assertTrue(all(p.full_url.startswith("https://api.brevo.com/v3/") for p in pedidos))

    @override_settings(BREVO_API_KEY="chave-de-teste")
    def test_a_rodada_sincroniza_uma_vez_a_cada_doze_horas(self):
        brevo._ultima["em"] = None
        chamadas = []
        with patch.object(brevo, "_get", self._falsa(chamadas)):
            primeira = brevo.sincronizar_se_vencido(_agora(2026, 9, 21, 8, 0))
            segunda = brevo.sincronizar_se_vencido(_agora(2026, 9, 21, 9, 0))
            terceira = brevo.sincronizar_se_vencido(_agora(2026, 9, 21, 21, 0))
        brevo._ultima["em"] = None

        self.assertIn("bloqueados", primeira)
        self.assertIn("pulado", segunda)
        self.assertIn("bloqueados", terceira)
        self.assertEqual(len(chamadas), 4)

    def test_o_build_sincroniza_e_o_comando_existe(self):
        from io import StringIO
        from pathlib import Path

        from django.core.management import call_command

        build = (Path(__file__).resolve().parent.parent / "scripts" / "build.sh").read_text(encoding="utf-8")
        self.assertIn("python manage.py sincronizar_brevo", build)
        saida = StringIO()
        with override_settings(BREVO_API_KEY=""):
            call_command("sincronizar_brevo", stdout=saida)
        self.assertIn("BREVO_API_KEY ausente", saida.getvalue())
