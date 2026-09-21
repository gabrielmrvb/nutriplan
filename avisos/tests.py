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
from .models import EmailEnviado, Preferencia, TipoDeEmail


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
