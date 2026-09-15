"""Exercício concluído na execução: a tela diz "concluído", não "Série None de 4".

UX P1-06 (14/09/2026): escolhendo na ficha um exercício com todas as séries
anotadas — o que é legítimo, a pessoa quer conferir a carga —, a execução
renderizava "Série None de 4", o formulário inteiro e um botão "Concluir
série None". `atual.proxima_serie` é `None` quando não há série livre, e o
template não tinha ramo para isso.

O ramo concluído mostra as pastilhas feitas, o desfazer e o próximo, e
oferece — como terceira opção, em texto — registrar uma série a mais. A
série extra continua existindo de propósito: `append_set` aceita até 20 e
a fila offline reenvia; o que muda é a TELA, que não pode oferecer um
formulário de série que não existe sem a pessoa pedir.

`?extra=1` é lista fechada, como `?exercicio=`: valor desconhecido é 404, e
não "ignora e abre a tela normal" — link quebrado que funciona nunca é
consertado.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from . import services
from .models import ExerciseLog
from .test_fluxo_do_treino import BaseDoFluxo, pessoa, tornar_hoje


class ExercicioConcluidoNaExecucaoTests(BaseDoFluxo):
    def setUp(self):
        self.user = pessoa("concluido@exemplo.com")
        self.sessao = tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        self.item = self.sessao.exercises.first()
        for numero in range(1, self.item.sets + 1):
            services.record_load(
                self.user, self.item.exercise, Decimal("40"), set_number=numero, reps=10
            )
        self.url = "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)

    def _html(self, url=None):
        resposta = self.client.get(url or self.url)
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode()

    def test_concluido_nao_mostra_serie_none_nem_formulario(self):
        html = self._html()
        self.assertNotIn("Série None", html)
        self.assertNotIn("série None", html)
        self.assertNotIn('<form class="registro', html)
        self.assertIn("Concluído", html)
        self.assertEqual(html.count('series__item--feita'), self.item.sets)

    def test_concluido_mantem_desfazer_proximo_e_a_porta_da_serie_extra(self):
        html = self._html()
        self.assertIn('class="agora__desfazer"', html)
        self.assertIn('class="agora__proximo-link"', html)
        self.assertIn(
            'href="%s?exercicio=%d&amp;extra=1"' % (reverse("workouts:now"), self.item.exercise_id),
            html,
        )
        self.assertIn("Registrar uma série a mais", html)

    def test_extra_reabre_o_formulario_com_o_numero_previsto(self):
        html = self._html(self.url + "&extra=1")
        self.assertIn('<form class="registro', html)
        self.assertIn("Concluir série %d" % (self.item.sets + 1), html)
        self.assertNotIn("Série None", html)
        self.assertNotIn("série None", html)
        # A carga de hoje vem preenchida: quem faz a quinta repete a quarta.
        self.assertIn('value="40"', html)

    def test_extra_e_lista_fechada(self):
        for valor in ("2", "sim", "", "1&extra=1"):
            with self.subTest(extra=valor):
                self.assertEqual(self.client.get(self.url + "&extra=" + valor).status_code, 404)

    def test_pendente_continua_com_o_formulario_de_sempre(self):
        """Controle positivo: o ramo concluído não vaza para o exercício com série livre."""
        outro = self.sessao.exercises.exclude(pk=self.item.pk).first()
        html = self._html("%s?exercicio=%d" % (reverse("workouts:now"), outro.exercise_id))
        self.assertIn('<form class="registro', html)
        self.assertIn("Concluir série 1", html)
        self.assertNotIn("Registrar uma série a mais", html)

    def test_na_leitura_o_concluido_diz_ver_as_series_e_nao_continuar(self):
        html = self.client.get(
            reverse("workouts:exercicio", args=[self.item.exercise_id])
        ).content.decode()
        self.assertIn("Ver as séries de hoje", html)
        self.assertNotIn("Continuar de onde parou", html)

    def test_controle_a_serie_extra_continua_sendo_gravada(self):
        """O servidor não mudou: `append_set` aceita a quinta, idempotente por `op_id`."""
        resposta = self.client.post(
            reverse("workouts:record_set"),
            {
                "exercise_id": self.item.exercise_id,
                "weight_kg": "42,5",
                "reps": "8",
                "op_id": "extra-0001",
                "exercicio": self.item.exercise_id,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            ExerciseLog.objects.filter(user=self.user, exercise=self.item.exercise).count(),
            self.item.sets + 1,
        )
