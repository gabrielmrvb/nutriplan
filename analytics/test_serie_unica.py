"""Uma série gravada = UM `treino.serie_concluida` (decisão do dono, 27/09/2026).

De 24/09 a 27/09/2026 `ConcluirSerieView` emitia o evento DUAS vezes por série
nova — um bloco de 21/09 com `exercicio` = nome, outro de 24/09 com `exercicio`
= pk —, e o "uso por área" da gestão contava o treino em dobro. Agora ele nasce
num lugar só, `telas.concluir_serie`, logo depois de a série ser gravada, com a
UNIÃO dos dois payloads. A view só entrega o `analytics.evento` com o request.

O histórico já dobrado NÃO é reescrito: o painel de gestão deixa de contar a
cópia (`consultas.SEM_COPIA_DA_SERIE`), e a tabela continua com as duas linhas.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Pilar
from analytics import consultas, servidor
from analytics.models import Event
from workouts import telas
from workouts.models import ExerciseLog
from workouts.test_fluxo_do_treino import BaseDoFluxo, pessoa, tornar_hoje

NOME = "treino.serie_concluida"


class UmaSerieUmEventoTests(BaseDoFluxo):
    def setUp(self):
        self.user = pessoa("serie-unica@exemplo.com")
        self.item = tornar_hoje(self.user, "A").exercises.select_related("exercise").first()
        self.client.force_login(self.user)

    def _postar(self, op_id="op-serie-unica-1", **extra):
        return self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": self.item.exercise_id, "weight_kg": "42,5",
             "reps": "8", "op_id": op_id},
            **extra,
        )

    def test_uma_serie_gravada_pela_tela_emite_um_evento_com_os_quatro_campos(self):
        """O caso real: o painel contava cada série duas vezes. Um POST que
        grava uma série deixa UMA linha, com a pk E o nome do exercício (a
        união do que os dois blocos antigos mandavam)."""
        self.assertEqual(self._postar().status_code, 302)
        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), 1)
        evento = Event.objects.get(name=NOME)
        self.assertEqual(evento.user, self.user)
        self.assertEqual(
            evento.props,
            {"exercicio": self.item.exercise_id, "exercicio_nome": self.item.exercise.name,
             "carga": 42.5, "reps": 8},
        )

    def test_reenvio_da_fila_com_o_mesmo_op_id_nao_emite_de_novo(self):
        """A fila offline reenvia o mesmo toque; é a mesma série chegando duas
        vezes, e contá-la de novo inflaria a gestão."""
        self._postar()
        self._postar()
        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Event.objects.filter(name=NOME).count(), 1)

    def test_quem_grava_fora_do_http_nao_emite_nada(self):
        """Sem `evento`, o service grava e cala — ele não tem request para
        atribuir o evento, e não inventa um."""
        criada, _ = telas.concluir_serie(
            self.user, self.item.exercise, Decimal("40"), timezone.localdate(), reps=10
        )
        self.assertTrue(criada)  # controle: a série nasceu
        self.assertFalse(Event.objects.filter(name=NOME).exists())

    def test_o_service_emite_pelo_callable_que_recebe(self):
        """Controle positivo do anterior: o MESMO service, com `evento`, emite."""
        request = RequestFactory().post("/")
        request.user = self.user
        request.session = {}
        telas.concluir_serie(
            self.user, self.item.exercise, Decimal("40"), timezone.localdate(), reps=10,
            evento=partial(servidor.evento, request),
        )
        self.assertEqual(Event.objects.filter(name=NOME).count(), 1)

    def test_dnt_grava_o_evento_sem_usuario(self):
        """Do-Not-Track recusa a IDENTIFICAÇÃO, não a contagem: o evento nasce
        anônimo, como sempre nasceu."""
        self._postar(HTTP_DNT="1")
        evento = Event.objects.get(name=NOME)
        self.assertIsNone(evento.user)


#: O fim do deploy 3a6094b em produção (API do Render): dali em diante, cada
#: série nova gravava o par. Escrito aqui por extenso, e não importado, para
#: o teste prender o VALOR que o dono decidiu.
CORTE = datetime.fromisoformat("2026-09-24T12:30:35+00:00")

#: Janela larga o bastante para os eventos de setembro de 2026 caberem em
#: qualquer relógio — o congelado da suíte ou o real da noturna, meses depois.
DIAS = 36500


class OPainelNaoContaACopiaDaSerieTests(TestCase):
    """De 24/09 a 27/09/2026 cada série nova gravou DUAS linhas: a cópia do
    bloco de 21/09, com `exercicio` em TEXTO, e a de 24/09, com a pk. O dono
    decidiu não reescrever o histórico; o painel deixa de contar a cópia."""

    def setUp(self):
        self.pessoa = get_user_model().objects.create_user(
            email="historico@exemplo.com", password="senha-bem-forte-123"
        )

    def _evento(self, quando, exercicio):
        return Event.objects.create(
            name=NOME, ts=quando, user=self.pessoa,
            props={"exercicio": exercicio, "carga": 40.0, "reps": 10},
        )

    def _contagens(self):
        """O que cada leitura do painel diz sobre a série — todas as que
        contam ou listam linha a linha."""
        treino = [
            area["registros"]
            for semana in consultas.uso_por_area(semanas=DIAS // 7)
            for area in semana["areas"] if area["area"] == Pilar.TREINO.value
        ]
        return {
            "eventos_por_dia": sum(d["n"] for d in consultas.eventos_por_dia(DIAS)),
            "top_eventos": sum(t["n"] for t in consultas.top_eventos(DIAS) if t["name"] == NOME),
            "explorar": sum(d["n"] for d in consultas.explorar(NOME, DIAS)),
            "uso_por_area": sum(treino),
            "linha_do_tempo": len(consultas.linha_do_tempo(str(self.pessoa.pk))),
        }

    def _todas(self, n):
        return dict.fromkeys(
            ("eventos_por_dia", "top_eventos", "explorar", "uso_por_area", "linha_do_tempo"), n
        )

    def test_o_par_depois_do_corte_conta_uma_vez(self):
        """O caso real: a mesma série, em texto e em pk, no mesmo instante."""
        depois = CORTE + timedelta(hours=1)
        self._evento(depois, "Supino reto")
        self._evento(depois, 12)
        self.assertEqual(self._contagens(), self._todas(1))

    def test_o_texto_sozinho_antes_do_corte_conta(self):
        """Antes do deploy, o texto era o ÚNICO evento da série — é real."""
        self._evento(CORTE - timedelta(days=1), "Supino reto")
        self.assertEqual(self._contagens(), self._todas(1))

    def test_o_evento_novo_com_a_pk_conta(self):
        """Controle positivo: o payload de hoje (a união) não é confundido."""
        Event.objects.create(
            name=NOME, ts=CORTE + timedelta(days=3), user=self.pessoa,
            props={"exercicio": 12, "exercicio_nome": "Supino reto", "carga": 40.0, "reps": 10},
        )
        self.assertEqual(self._contagens(), self._todas(1))

    def test_o_par_continua_na_tabela(self):
        """Histórico não se reescreve: a poda de 90 dias, o alias e a agregação
        leem `Event.objects`, e ali as duas linhas continuam existindo."""
        depois = CORTE + timedelta(hours=1)
        self._evento(depois, "Supino reto")
        self._evento(depois, 12)
        self._contagens()
        self.assertEqual(Event.objects.filter(name=NOME).count(), 2)
