"""Reps fora de 1..100 são recusadas com mensagem — e nada é gravado.

UX TR-08 / E08 (14/09/2026): `ConcluirSerieView` aparava em silêncio —
`reps=999` virava 100 e `reps=0` virava 1 —, e a série entrava com um
número que a pessoa não digitou. O teto (1..100) continua sendo da TREINO;
o que muda é o comportamento: recusa com mensagem, zero `ExerciseLog`, e a
tela volta ao exercício em foco pelo mesmo PRG que a carga inválida já
usa ("Carga inválida — use números, como 42,5.").

O brief pedia "200 com o valor preservado"; a convenção desta view é
redirecionar com mensagem (é o que a carga faz desde 30/08), e os campos
reabrem com a sugestão da série — que é o último valor VÁLIDO. O HTML
ganha `pattern` e `title`: o navegador barra 0 e 999 antes de enviar, e
a fila offline nunca captura item inválido.

TR-02: fechar a última série do exercício diz que ele fechou. TR-03: o
desfazer diz qual série de qual exercício saiu; MOB-12: desfazer série de
OUTRO exercício pede um segundo toque.
"""

from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from . import services
from .models import ExerciseLog
from .test_fluxo_do_treino import BaseDoFluxo, pessoa, tornar_hoje


class RepsForaDaFaixaTests(BaseDoFluxo):
    def setUp(self):
        self.user = pessoa("reps@exemplo.com")
        self.sessao = tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        self.item = self.sessao.exercises.first()

    def _post(self, reps, op_id):
        return self.client.post(
            reverse("workouts:record_set"),
            {
                "exercise_id": self.item.exercise_id,
                "weight_kg": "40",
                "reps": reps,
                "op_id": op_id,
                "exercicio": self.item.exercise_id,
            },
        )

    def _mensagens(self, resposta):
        return [str(m) for m in get_messages(resposta.wsgi_request)]

    def test_999_e_0_sao_recusados_sem_gravar(self):
        for reps in ("999", "0", "-3", "101"):
            with self.subTest(reps=reps):
                resposta = self._post(reps, "op-" + reps)
                self.assertEqual(resposta.status_code, 302)
                self.assertTrue(any("1 a 100" in m for m in self._mensagens(resposta)))
                self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), 0)
                # Volta ao exercício em foco, e não ao primeiro pendente.
                self.assertIn("exercicio=%d" % self.item.exercise_id, resposta["Location"])

    def test_dez_grava_e_texto_ilegivel_e_recusado(self):
        resposta = self._post("10", "op-10")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(ExerciseLog.objects.get(user=self.user).reps, 10)
        resposta = self._post("dez", "op-dez")
        self.assertTrue(any("1 a 100" in m for m in self._mensagens(resposta)))
        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), 1)

    def test_reps_em_branco_continua_aceito(self):
        """Reps é opcional desde sempre: quem anota só a carga não é barrado."""
        self._post("", "op-vazio")
        self.assertIsNone(ExerciseLog.objects.get(user=self.user).reps)

    def test_o_html_barra_antes_de_enviar(self):
        html = self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        ).content.decode()
        inicio = html.index('name="reps"')
        campo = html[html.rindex("<input", 0, inicio): html.index(">", inicio)]
        self.assertIn('pattern="', campo)
        self.assertIn('title="', campo)


class FecharEDesfazerFalamTests(BaseDoFluxo):
    def setUp(self):
        self.user = pessoa("fala@exemplo.com")
        self.sessao = tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        self.item = self.sessao.exercises.first()

    def _serie(self, op_id):
        return self.client.post(
            reverse("workouts:record_set"),
            {
                "exercise_id": self.item.exercise_id,
                "weight_kg": "40",
                "reps": "10",
                "op_id": op_id,
                "exercicio": self.item.exercise_id,
            },
        )

    def test_fechar_a_ultima_serie_diz_que_o_exercicio_fechou(self):
        for numero in range(1, self.item.sets):
            self._serie("op-%d" % numero)
        resposta = self._serie("op-ultima")
        textos = [str(m) for m in get_messages(resposta.wsgi_request)]
        self.assertTrue(any(
            self.item.exercise.name in m and "%d/%d" % (self.item.sets, self.item.sets) in m
            for m in textos
        ), textos)

    def test_uma_serie_no_meio_nao_diz_nada(self):
        resposta = self._serie("op-1")
        self.assertEqual([str(m) for m in get_messages(resposta.wsgi_request)], [])

    def test_desfazer_diz_qual_serie_de_qual_exercicio_saiu(self):
        self._serie("op-1")
        self._serie("op-2")
        resposta = self.client.post(
            reverse("workouts:record_set"),
            {
                "exercise_id": self.item.exercise_id,
                "acao": "desfazer",
                "op_id": "op-desfazer",
                "exercicio": self.item.exercise_id,
            },
        )
        textos = [str(m) for m in get_messages(resposta.wsgi_request)]
        self.assertTrue(any("Série 2" in m and self.item.exercise.name in m for m in textos), textos)

    def test_desfazer_serie_de_outro_exercicio_pede_o_segundo_toque(self):
        self._serie("op-1")
        outro = self.sessao.exercises.exclude(pk=self.item.pk).first()
        html = self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), outro.exercise_id)
        ).content.decode()
        inicio = html.index('class="agora__desfazer"')
        bloco = html[inicio: html.index("</form>", inicio)]
        self.assertIn("<details", bloco)
        self.assertIn(self.item.exercise.name, bloco)
        # No próprio exercício é um toque só.
        html = self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        ).content.decode()
        inicio = html.index('class="agora__desfazer"')
        self.assertNotIn("<details", html[inicio: html.index("</form>", inicio)])
