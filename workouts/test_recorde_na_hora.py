# -*- coding: utf-8 -*-
"""O recorde aparece NA HORA, na rota que a execução usa.

`achievements.services` diz que as conquistas rodam "no caminho de escrita —
registrar série". Era verdade para `RecordLoadView`, a rota do cartão da
ficha que saiu da tela em 10/09/2026; `ConcluirSerieView`, a rota que a
execução de fato usa, nunca chamou `avaliar`. A chave da regra é
`exercício:data`, então o recorde de hoje só nascia se a pessoa abrisse
/conquistas/ HOJE — amanhã a data mudou e ele nunca mais é detectado.
Achado da pesquisa de 13/09/2026.

Dois consertos, os dois sobre dado que já está carregado:

- `load_history` passa a devolver `recorde_anterior` (a maior carga em
  qualquer data anterior) — a consulta já trazia o histórico inteiro; é uma
  redução a mais no mesmo laço, zero consulta nova;
- `ConcluirSerieView` avalia as conquistas DEPOIS de gravar, com o dia do
  toque (e não `localdate()`, por causa da fila), só no ramo de gravação —
  desfazer não cria conquista.

A tela mostra o recorde como FATO ("recorde: 65 kg") e, quando uma série de
hoje o supera, a palavra "recorde" na pastilha — texto, não só cor.
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from achievements.models import UserAchievement as Conquista
from workouts import services
from workouts.models import ExerciseLog, Measure
from workouts.tests import create_user, dias_incluindo_hoje, sem_scripts


class ORecordeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="recorde@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        plano = services.get_active_routine(self.pessoa)
        sessao = next(s for s in plano.sessions.all() if s.weekday == self.hoje.weekday())
        self.item = next(
            i for i in sessao.exercises.select_related("exercise")
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def _log(self, dias_atras, serie, peso, reps=10):
        return ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.item.exercise,
            date=self.hoje - timedelta(days=dias_atras), set_number=serie,
            weight_kg=Decimal(peso), reps=reps,
        )

    def _html(self):
        url = "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        return sem_scripts(self.client.get(url).content.decode())

    def test_load_history_conhece_a_maior_carga_de_todas_as_datas_anteriores(self):
        self._log(20, 1, "60"); self._log(10, 1, "65"); self._log(3, 1, "62.5")
        carga = services.load_history(self.pessoa, [self.item.exercise])[self.item.exercise_id]
        self.assertEqual(carga["recorde_anterior"], Decimal("65"))
        self.assertEqual(carga["melhor_anterior"], Decimal("62.5"))  # a última data, como antes

    def test_a_tela_mostra_o_recorde_como_fato(self):
        self._log(10, 1, "65"); self._log(3, 1, "62.5")
        html = self._html()
        fato = html.split('class="agora__recorde"', 1)[1].split("</span>", 1)[0]
        self.assertIn("65", fato)
        self.assertIn("recorde", fato.lower())

    def test_a_serie_que_supera_o_recorde_diz_recorde_na_pastilha(self):
        self._log(10, 1, "65"); self._log(0, 1, "67.5", 8)
        pastilhas = re.findall(r'<li class="series__item[^"]*">(.*?)</li>', self._html(), re.S)
        self.assertIn("recorde", pastilhas[0])
        # A segunda série ainda não existe: sem a palavra.
        self.assertNotIn("recorde", pastilhas[1])

    def test_sem_historico_anterior_nao_ha_recorde_nem_estreia_comemorada(self):
        self._log(0, 1, "40")
        html = self._html()
        self.assertNotIn('class="agora__recorde"', html)
        self.assertNotIn("recorde", html.split('class="series__lista"', 1)[1].split("</ol>", 1)[0])

    def test_concluir_uma_serie_acima_do_recorde_cria_a_conquista_no_dia_do_toque(self):
        self._log(10, 1, "65")
        dia = self.hoje - timedelta(days=1)  # a fila drenou no dia seguinte
        resposta = self.client.post(reverse("workouts:record_set"), {
            "exercise_id": self.item.exercise_id, "weight_kg": "70", "reps": "8",
            "op_id": "op-recorde", "dia": dia.isoformat(),
        })
        self.assertEqual(resposta.status_code, 302)
        conquista = Conquista.objects.get(user=self.pessoa, slug="novo-recorde")
        self.assertEqual(conquista.chave, "%d:%s" % (self.item.exercise_id, dia.isoformat()))

    def test_serie_sem_recorde_nao_paga_o_catalogo_inteiro(self):
        """`avaliar` custa 43 consultas (medido em 13/09/2026) e a fila reenvia
        séries em rajada. Sem recorde, o POST fica no custo de sempre; a
        régua é o número medido ANTES da avaliação entrar."""
        self._log(10, 1, "65")
        corpo = {
            "exercise_id": self.item.exercise_id, "weight_kg": "60", "reps": "8",
            "op_id": "op-comum", "dia": self.hoje.isoformat(),
        }
        with CaptureQueriesContext(connection) as consultas:
            self.client.post(reverse("workouts:record_set"), corpo)
        self.assertLessEqual(len(consultas), CONSULTAS_DO_POST_SEM_RECORDE)
        self.assertFalse(Conquista.objects.filter(user=self.pessoa, slug="novo-recorde").exists())

    def test_desfazer_nao_avalia_conquista(self):
        self._log(10, 1, "65"); self._log(0, 1, "70")
        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": self.item.exercise_id, "acao": "desfazer",
            "op_id": "op-desfaz", "dia": self.hoje.isoformat(),
        })
        self.assertFalse(Conquista.objects.filter(user=self.pessoa).exists())

    def test_o_custo_da_execucao_nao_cresce_com_o_recorde(self):
        """Medido em 13/09/2026 ANTES de `recorde_anterior` existir: o número
        abaixo é o de então. O recorde sai do laço que `load_history` já
        fazia — se este teste subir, alguém acrescentou consulta."""
        self._log(10, 1, "65"); self._log(3, 1, "62.5"); self._log(0, 1, "67.5")
        url = "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        self.client.get(url)  # aquece sessão/perfil
        with CaptureQueriesContext(connection) as consultas:
            self.client.get(url)
        self.assertLessEqual(len(consultas), CONSULTAS_DA_EXECUCAO)


#: Consultas de `/treino/agora/?exercicio=<id>` com histórico, medidas em
#: 13/09/2026 antes desta mudança. Teto, não alvo: só sobe com medição escrita.
CONSULTAS_DA_EXECUCAO = 20
#: Consultas do POST de uma série SEM recorde: as 15 de antes mais UMA
#: (`supera_recorde`), medidas em 13/09/2026. Com recorde o catálogo roda e
#: custa ~43 a mais — raro, e é o evento que a conquista existe para marcar.
CONSULTAS_DO_POST_SEM_RECORDE = 16
