# -*- coding: utf-8 -*-
"""TREINO EM ANDAMENTO NÃO SOME (22/09/2026).

Observado pelo dono, logado, com quatro séries anotadas no primeiro
exercício do Treino A: outra aba da mesma conta mexeu no programa, e na
mesma hora a ficha que estava aberta passou a responder "Esta página não
existe", o cartão de hoje virou o Treino B com 0 % e as quatro séries
sumiram da visão do dia (continuavam em Progresso, porque `ExerciseLog` é
por exercício e data).

`sync_active_routine` já adiava a remontagem com série anotada hoje
(17/09). O que faltava eram as TRÊS pontas que este arquivo prende:

1. **o pedido explícito** — `POST /treino/regenerar/` chamava
   `create_routine` sem olhar para o dia. Hoje ele ADIA: grava
   `TrainingPlan.regenerar_pedido_em` e a remontagem acontece na primeira
   visita do dia seguinte. Quem não tem série hoje continua remontando na
   hora (controle positivo abaixo);
2. **a ficha do plano anterior** — `plan__is_active=True` no
   `get_object_or_404` transformava a ficha em uso em 404. Hoje a sessão da
   própria pessoa abre em modo HISTÓRICO, sem porta de execução, e diz o
   que foi registrado nela; de outra pessoa continua 404;
3. **a série que chega depois da virada** — o formulário carrega o id da
   sessão; quando ela não é mais a sessão de hoje, a série é gravada do
   mesmo jeito (o registro é por exercício e data, e perder o toque seria o
   pior desfecho) e a tela AVISA que o programa mudou.
"""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import DuracaoTreino, TrainingDay
from plans.tests import create_complete_user
from workouts import services
from workouts.models import ExerciseLog, TrainingPlan


def _pessoa(email="andamento@exemplo.com"):
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference="two",
        split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in (0, 1, 2, 3, 4):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


def _anotar_serie(user, sessao, series=1):
    """Quatro séries no primeiro exercício da sessão — o estado do relato."""
    item = sessao.exercises.select_related("exercise").order_by("order").first()
    for n in range(1, series + 1):
        ExerciseLog.objects.create(
            user=user, exercise=item.exercise, date=timezone.localdate(),
            set_number=n, weight_kg=40, reps=8,
        )
    return item


class RemontarEsperaOTreinoAcabarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = _pessoa()
        self.plano = services.create_routine(self.user)
        self.client.force_login(self.user)

    def test_regenerar_com_serie_de_hoje_nao_troca_a_ficha_debaixo_da_mao(self):
        """O pedido é aceito, mas vale amanhã: hoje a pessoa está treinando."""
        sessao = services.sessao_do_dia(self.plano, timezone.localdate())
        _anotar_serie(self.user, sessao, series=4)

        resposta = self.client.post(reverse("workouts:regenerar"), follow=True)

        self.assertEqual(
            TrainingPlan.objects.filter(user=self.user, is_active=True).first().pk,
            self.plano.pk,
            "a ficha em uso foi remontada no meio do treino",
        )
        texto = " ".join(str(m) for m in resposta.context["messages"])
        self.assertIn("amanhã", texto.lower())
        self.plano.refresh_from_db()
        self.assertIsNotNone(self.plano.regenerar_pedido_em, "o pedido não ficou gravado")

    def test_o_pedido_adiado_remonta_no_dia_seguinte(self):
        """"Espera o dia acabar" só é verdade se alguém cumprir amanhã."""
        sessao = services.sessao_do_dia(self.plano, timezone.localdate())
        _anotar_serie(self.user, sessao)
        self.client.post(reverse("workouts:regenerar"))

        amanha = timezone.localdate() + timedelta(days=1)
        plano, mudou = services.sync_active_routine(self.user, day=amanha)

        self.assertTrue(mudou, "o pedido de ontem não foi cumprido hoje")
        self.assertNotEqual(plano.pk, self.plano.pk)
        self.assertIsNone(plano.regenerar_pedido_em, "o pedido cumprido não foi limpo")

    def test_sem_serie_hoje_regenerar_continua_remontando_na_hora(self):
        """Controle positivo: o adiamento não pode virar 'nunca remonta'."""
        self.client.post(reverse("workouts:regenerar"))
        novo = TrainingPlan.objects.filter(user=self.user, is_active=True).first()
        self.assertNotEqual(novo.pk, self.plano.pk)

    def test_a_serie_de_hoje_sobrevive_a_remontagem_de_amanha(self):
        sessao = services.sessao_do_dia(self.plano, timezone.localdate())
        _anotar_serie(self.user, sessao, series=4)
        services.create_routine(self.user)
        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), 4)


class AFichaDoProgramaAnteriorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = _pessoa("historico@exemplo.com")
        self.plano = services.create_routine(self.user)
        self.sessao = services.sessao_do_dia(self.plano, timezone.localdate())
        _anotar_serie(self.user, self.sessao, series=4)
        self.client.force_login(self.user)

    def test_a_ficha_em_uso_nao_responde_404_depois_da_remontagem(self):
        """O relato do dono: "Esta página não existe" com o treino em curso."""
        services.create_routine(self.user)  # o plano de antes fica inativo

        resposta = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))

        self.assertEqual(resposta.status_code, 200)

    def test_a_ficha_antiga_se_apresenta_como_historico_e_nao_oferece_executar(self):
        services.create_routine(self.user)
        resposta = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))
        html = resposta.content.decode()
        self.assertIn("programa anterior", html.lower())
        self.assertNotIn(reverse("workouts:now"), html)

    def test_a_ficha_antiga_diz_o_que_foi_registrado_nela(self):
        services.create_routine(self.user)
        html = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk])).content.decode()
        self.assertIn("4</span>", html)
        self.assertIn("séries registradas", html)

    def test_a_ficha_de_outra_pessoa_continua_404(self):
        outra = _pessoa("intrusa@exemplo.com")
        self.client.force_login(outra)
        resposta = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))
        self.assertEqual(resposta.status_code, 404)


class ASerieQueChegaDepoisDaViradaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = _pessoa("virada@exemplo.com")
        self.plano = services.create_routine(self.user)
        self.sessao = services.sessao_do_dia(self.plano, timezone.localdate())
        self.item = self.sessao.exercises.select_related("exercise").order_by("order").first()
        self.client.force_login(self.user)

    def _post(self, **extra):
        dados = {
            "exercise_id": self.item.exercise_id,
            "weight_kg": "40",
            "reps": "8",
            "op_id": "op-teste-1",
            "dia": timezone.localdate().isoformat(),
            "sessao": self.sessao.pk,
        }
        dados.update(extra)
        return self.client.post(reverse("workouts:record_set"), dados, follow=True)

    def test_a_serie_e_gravada_mesmo_com_o_programa_remontado_no_meio(self):
        """Perder o toque seria o pior desfecho: o registro é por exercício e data."""
        services.create_routine(self.user)
        resposta = self._post()
        self.assertEqual(
            ExerciseLog.objects.filter(user=self.user, exercise=self.item.exercise).count(), 1,
        )
        texto = " ".join(str(m) for m in resposta.context["messages"]).lower()
        self.assertIn("programa", texto)
        self.assertIn("mudou", texto)

    def test_sem_mudanca_nenhum_aviso_aparece(self):
        """Controle positivo: o aviso não pode aparecer no treino normal."""
        resposta = self._post()
        texto = " ".join(str(m) for m in resposta.context["messages"]).lower()
        self.assertNotIn("programa mudou", texto)
