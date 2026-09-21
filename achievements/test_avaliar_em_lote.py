"""`avaliar` grava em LOTE: o custo não cresce com o que foi detectado.

O achado da auditoria de 20/09/2026 (produção `dc971a0`): `/conquistas/`
respondia com TTFB de 1,1–1,2 s no Render enquanto toda outra tela ficava em
250–350 ms — e localmente, para o Carlos do demo (487 séries), a mesma tela
fazia **252 consultas, 159 repetidas**. A causa era `avaliar`: um
`get_or_create` dentro de `transaction.atomic()` POR DETECÇÃO, e o recorde
detecta um par `(exercício, data)` por exercício — 75 detecções viravam 75 ×
(BEGIN + SELECT + COMMIT). O número cresce com o histórico: quanto mais a
pessoa treina, mais lenta fica a tela que celebra isso.

O que se cobra aqui é a PROPRIEDADE, não um número: duas pessoas com
detecções em quantidades diferentes pagam o MESMO número de consultas, e o
resultado continua idêntico ao de antes — tudo que é novo nasce, nada
duplica, a segunda passagem devolve vazio.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from workouts.models import Exercise, ExerciseLog

from . import services
from .models import UserAchievement
from .tests import SEGUNDA, BaseDeConquistas


class AvaliarEmLoteTests(BaseDeConquistas):
    def _com_recordes(self, email, quantos):
        """Uma pessoa com `quantos` exercícios treinados HOJE pela primeira
        vez — cada um é um "novo recorde" e uma "melhor série" para o
        detector, ou seja, 2 × `quantos` detecções além das fixas."""
        user = self.pessoa(email=email)
        exercicios = list(Exercise.objects.filter(is_active=True)[:quantos])
        self.assertEqual(len(exercicios), quantos, "o catálogo semeado tem exercícios de sobra")
        for i, exercicio in enumerate(exercicios):
            # uma série ontem, mais leve, para o de hoje ser recorde de verdade
            ExerciseLog.objects.create(user=user, exercise=exercicio, date=SEGUNDA - timedelta(days=1),
                                       set_number=1, weight_kg=Decimal("40"), reps=8)
            ExerciseLog.objects.create(user=user, exercise=exercicio, date=SEGUNDA,
                                       set_number=1, weight_kg=Decimal("60") + i, reps=10)
        return user

    def _consultas_de_avaliar(self, user):
        with CaptureQueriesContext(connection) as ctx:
            novas = services.avaliar(user, hoje=SEGUNDA)
        return len(ctx.captured_queries), novas

    def test_o_custo_nao_cresce_com_o_numero_de_deteccoes(self):
        """Duas detecções e vinte detecções custam o mesmo número de consultas.

        Antes da correção o segundo caso pagava dezoito × 3 consultas a mais
        (um `get_or_create` transacional por detecção)."""
        pouca = self._com_recordes("pouca@exemplo.com", 1)
        muita = self._com_recordes("muita@exemplo.com", 10)
        n_pouca, novas_pouca = self._consultas_de_avaliar(pouca)
        n_muita, novas_muita = self._consultas_de_avaliar(muita)
        self.assertGreater(len(novas_muita), len(novas_pouca), "o cenário precisa ter detecções a mais")
        self.assertEqual(n_muita, n_pouca, "avaliar pagou %d consultas para %d conquistas e %d para %d" % (
            n_muita, len(novas_muita), n_pouca, len(novas_pouca)))

    def test_grava_tudo_que_e_novo_uma_vez_e_devolve_com_pk(self):
        """A propriedade de antes continua: nasce tudo, nada duplica, a
        segunda passagem devolve vazio — e o que volta tem `pk`, porque
        `anunciar` guarda os ids na sessão."""
        user = self._com_recordes("lote@exemplo.com", 3)
        novas = services.avaliar(user, hoje=SEGUNDA)
        self.assertTrue(novas)
        self.assertTrue(all(c.pk for c in novas), "toda conquista devolvida tem pk")
        self.assertEqual(sorted((c.slug, c.chave) for c in novas),
                         sorted(UserAchievement.objects.filter(user=user).values_list("slug", "chave")))
        self.assertIn("primeiro-treino", [c.slug for c in novas])
        self.assertEqual(sum(1 for c in novas if c.slug == "novo-recorde"), 3)
        self.assertEqual(services.avaliar(user, hoje=SEGUNDA), [], "a segunda passagem não inventa nada")
        self.assertEqual(UserAchievement.objects.filter(user=user).count(), len(novas))

    def test_o_contexto_de_cada_conquista_e_gravado(self):
        """O lote não pode perder o `contexto` que a regra devolveu — é o que
        a tela usa para dizer QUAL exercício foi recorde."""
        user = self._com_recordes("contexto@exemplo.com", 1)
        services.avaliar(user, hoje=SEGUNDA)
        recorde = UserAchievement.objects.get(user=user, slug="novo-recorde")
        self.assertTrue(recorde.contexto, "o recorde guarda o exercício no contexto")
        self.assertIn("exercicio", str(recorde.contexto).lower() + "".join(recorde.contexto.keys()).lower())
