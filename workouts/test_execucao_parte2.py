"""Execução sem série fantasma nem recorde inventado — Parte 2, onda 3 (28/09/2026).

Os achados vêm do caça-bugs de 27/09/2026 (`achados/caca-bugs-20260927.md`) e
do QA exploratório do mesmo dia. Cada classe abaixo nomeia o achado e o caso
real que o motivou:

- M12: o supino sem histórico mostrava "Na última pressão de peito (flexão de
  braço): 0 kg × 11" — o peso do corpo grava `weight_kg=0.00`, e no empate em
  zero a referência escolhia a PIOR série salva.
- M13: "Suspensão na barra" e "Cadeira na parede" ("segure o máximo que
  aguentar") saíam prescritas em 12–15 REPETIÇÕES; só a prancha, curada em
  segundos no `splits.json`, estava certa.
- M14/M15: duas abas no mesmo exercício mostravam "Série 3 de 3"; a velha
  concluía por cima e o servidor gravava uma 4ª série muda, que sumia da
  execução (a contagem para na ficha) mas somava no volume do placar
  ("24 séries registradas" ao lado de 6.153 kg com a série fantasma).
- M20: 45 kg de ASSISTÊNCIA depois de 25 kg na barra fixa assistida virava
  "RECORDE · MELHOR SÉRIE" e a conquista "Novo recorde" — mais ajuda lida
  como mais força.
- BA11: voltar/avançar na execução devolvia a página do bfcache com o
  descanso e a contagem do momento em que ela foi guardada.
- Item 7: "Buscar no YouTube" era um link cru de 21 px de altura.

Armadilha do repositório (CLAUDE.md, "Testes"): o seletor do JavaScript e o
marcador do HTML são a mesma string. Aqui as asserções de tela leem o TEXTO
VISÍVEL (`texto_visivel`) ou ancoram na tag inteira.
"""
import json
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import reverse

from achievements import services as conquistas
from achievements.models import UserAchievement
from config.test_linguagem import texto_visivel
from plans.tests import create_complete_user
from workouts import services
from workouts.models import (
    Exercise,
    ExerciseLog,
    Measure,
    SessionExercise,
    TrocaDeExercicio,
    WorkoutTemplateItem,
)
from workouts.test_fluxo_do_treino import BaseDoFluxo, pessoa, tornar_hoje

DATA = settings.BASE_DIR / "workouts" / "data"
#: Um dia de treino ANTES da quarta congelada da suíte (16/09/2026).
ANTES = date(2026, 9, 14)

SUSTENTACOES = ("Cadeira na parede", "Suspensão na barra", "Prancha lateral")


def _log(user, exercicio, peso, reps, serie, dia=ANTES):
    return ExerciseLog.objects.create(
        user=user, exercise=exercicio, date=dia, set_number=serie,
        weight_kg=Decimal(str(peso)), reps=reps,
    )


# --------------------------------------------------------------------- M12


class AReferenciaDoMovimentoNaoInventaCargaTests(BaseDoFluxo):
    """M12: "Primeira vez neste. Na última pressão de peito (flexão de braço,
    02/10): 0 kg × 11" — na tela do supino de quem só tinha feito flexão."""

    def setUp(self):
        self.user = pessoa("m12@exemplo.com")
        tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        self.supino = Exercise.objects.get(name="Supino reto com barra")
        self.flexao = Exercise.objects.get(name="Flexão de braço")
        self.url = "%s?exercicio=%d" % (reverse("workouts:now"), self.supino.pk)

    def _texto(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        return texto_visivel(resposta.content.decode())

    def test_peso_do_corpo_como_referencia_nao_vira_zero_kg(self):
        """Flexão não tem anilha: a referência diz as repetições, nunca "0 kg"."""
        _log(self.user, self.flexao, 0, 12, 1)
        texto = self._texto()
        self.assertIn("Na última pressão de peito (flexão de braço, 14/09)", texto)
        self.assertNotIn("0 kg", texto)
        self.assertIn("12 reps", texto)

    def test_sem_carga_e_sem_repeticoes_nao_ha_referencia(self):
        """Série de flexão anotada sem reps: não há número para dizer, e a
        frase "Na última pressão de peito (…):" terminaria no vazio."""
        ExerciseLog.objects.create(
            user=self.user, exercise=self.flexao, date=ANTES, set_number=1,
            weight_kg=Decimal("0"), reps=None,
        )
        texto = self._texto()
        self.assertNotIn("Primeira vez neste", texto)
        self.assertNotIn("0 kg", texto)

    def test_a_ultima_vez_sem_carga_e_sem_reps_nao_diz_none(self):
        """F4 da revisão: flexão anotada com 0 kg e reps vazio mostrava
        "última: None reps 14/09" na tela da própria flexão."""
        ExerciseLog.objects.create(
            user=self.user, exercise=self.flexao, date=ANTES, set_number=1,
            weight_kg=Decimal("0"), reps=None,
        )
        html = self.client.get("%s?exercicio=%d" % (reverse("workouts:now"), self.flexao.pk)).content.decode()
        texto = texto_visivel(html)
        self.assertNotIn("None", texto)
        self.assertNotIn("Na última vez você fez", texto)
        # Controle: com reps, a referência aparece — em reps.
        ExerciseLog.objects.filter(user=self.user, exercise=self.flexao).update(reps=11)
        texto = texto_visivel(self.client.get("%s?exercicio=%d" % (reverse("workouts:now"), self.flexao.pk)).content.decode())
        self.assertIn("Na última vez você fez última: 11 reps", texto)

    def test_no_empate_em_zero_a_referencia_e_a_melhor_serie(self):
        """A pior série vinha por último (`-set_number` desempatava) e era ela
        que a tela mostrava: 12 e 10 repetições, a tela dizia 10."""
        _log(self.user, self.flexao, 0, 12, 1)
        _log(self.user, self.flexao, 0, 10, 2)
        referencia = services.ultima_vez_do_movimento(self.user, self.supino)
        self.assertEqual(referencia["reps"], 12)
        self.assertIn("12 reps", self._texto())

    def test_controle_carga_de_verdade_continua_em_kg(self):
        """Controle positivo: o mesmo movimento COM anilha continua "kg × reps"."""
        com_anilha = (
            Exercise.objects.filter(padrao=self.supino.padrao, is_active=True)
            .exclude(equipment="bodyweight").exclude(pk=self.supino.pk).first()
        )
        _log(self.user, com_anilha, 40, 8, 1)
        self.assertIn("40 kg × 8", self._texto())

    def test_a_ultima_vez_tambem_desempata_pela_melhor(self):
        """O bloco irmão ("última:", acima do campo) tinha o mesmo empate: na
        mesma carga, a série com MAIS repetições é a referência."""
        for registros, esperado in (
            ({1: (0, 10), 2: (0, 12)}, 12),
            ({1: (60, 7), 2: (60, 8)}, 8),
        ):
            with self.subTest(esperado=esperado):
                anterior = {
                    n: ExerciseLog(date=ANTES, set_number=n, weight_kg=Decimal(p), reps=r)
                    for n, (p, r) in registros.items()
                }
                ultima = services.ultima_serie_anterior({"anterior": anterior})
                self.assertEqual(ultima["reps"], esperado)


# --------------------------------------------------------------------- M13


def _dose_da_prancha_no_catalogo():
    modelos = json.loads((DATA / "splits.json").read_text(encoding="utf-8"))
    doses = {
        (item[2], item[3])
        for modelo in modelos
        for item in modelo["items"]
        if item[0] == "Prancha abdominal"
    }
    assert len(doses) == 1, doses
    return doses.pop()


class AReferenciaDaSustentacaoEmSegundosTests(BaseDoFluxo):
    """F4 da revisão: "última: 40 reps" na cadeira na parede, e "Na última
    extensão de joelho (cadeira na parede, …): 40 reps" na extensora —
    eram 40 SEGUNDOS."""

    def setUp(self):
        self.user = pessoa("f4-segundos@exemplo.com")
        tornar_hoje(self.user, "C")
        self.client.force_login(self.user)
        self.parede = Exercise.objects.get(name="Cadeira na parede")
        self.extensora = Exercise.objects.get(name="Cadeira extensora")
        _log(self.user, self.parede, 0, 40, 1)

    def _texto(self, exercicio):
        return texto_visivel(self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), exercicio.pk)
        ).content.decode())

    def test_a_referencia_do_movimento_diz_segundos(self):
        texto = self._texto(self.extensora)
        self.assertIn("(cadeira na parede, 14/09): 40 s", texto)
        self.assertNotIn("40 reps", texto)

    def test_a_ultima_vez_da_sustentacao_diz_segundos(self):
        TrocaDeExercicio.objects.create(user=self.user, original=self.extensora, substituto=self.parede)
        texto = self._texto(self.parede)
        self.assertIn("última: 40 s", texto)
        self.assertNotIn("40 reps", texto)


class ASustentacaoEMedidaEmSegundosTests(BaseDoFluxo):
    """M13: sustentação mede tempo. A prancha já media (6º elemento
    `"seconds"` no `splits.json`); as outras três nunca são item de modelo e
    entravam por substituição com a dose EM REPETIÇÕES do item trocado."""

    def test_as_sustentacoes_e_a_prancha_sao_segundos_no_catalogo(self):
        for nome in (*SUSTENTACOES, "Prancha abdominal"):
            with self.subTest(exercicio=nome):
                self.assertEqual(Exercise.objects.get(name=nome).measure, Measure.SECONDS)
        # Controle: o exercício que a cadeira na parede substitui conta repetição.
        self.assertEqual(Exercise.objects.get(name="Cadeira extensora").measure, Measure.REPS)

    def test_todo_item_de_modelo_tem_a_unidade_do_seu_exercicio(self):
        """A unidade é do EXERCÍCIO: nenhum modelo curado pode dizer outra."""
        divergentes = [
            (i.template.split, i.template.label, i.exercise.name, i.measure)
            for i in WorkoutTemplateItem.objects.select_related("exercise", "template")
            if i.measure != i.exercise.measure
        ]
        self.assertEqual(divergentes, [])

    def test_a_dose_da_sustentacao_e_a_da_prancha(self):
        """A dose não é inventada: é a da prancha curada, e as duas não divergem."""
        self.assertEqual(services.DOSE_DA_SUSTENTACAO, _dose_da_prancha_no_catalogo())

    def _item(self, nome, sets=2, faixa=(12, 15), descanso=60):
        return SessionExercise(
            exercise=Exercise.objects.get(name=nome), sets=sets, rep_min=faixa[0],
            rep_max=faixa[1], rest_seconds=descanso, order=1,
        )

    def test_sustentacao_no_lugar_de_item_em_repeticoes_recebe_a_dose_da_prancha(self):
        """Casa sem aparelho: a cadeira extensora (2 × 12–15) vira cadeira na
        parede — 2 × 30–45 SEGUNDOS, com o descanso do item trocado."""
        catalogo = services.catalogo_permitido({"bodyweight"})
        [trocado] = services.substituir_por_equipamento(
            [self._item("Cadeira extensora")], {"bodyweight"}, catalogo
        )
        self.assertEqual(trocado.exercise.name, "Cadeira na parede")
        self.assertEqual(
            (trocado.measure, trocado.sets, trocado.rep_min, trocado.rep_max, trocado.rest_seconds),
            (Measure.SECONDS, 2, 30, 45, 60),
        )
        self.assertEqual(trocado.rep_range, "30-45s")

    def test_controle_substituto_em_repeticoes_mantem_a_dose(self):
        catalogo = services.catalogo_permitido({"dumbbell", "bodyweight"})
        [trocado] = services.substituir_por_equipamento(
            [self._item("Supino reto com barra", sets=4, faixa=(6, 10), descanso=90)],
            {"dumbbell", "bodyweight"}, catalogo,
        )
        self.assertNotEqual(trocado.exercise.name, "Supino reto com barra")
        self.assertEqual(
            (trocado.measure, trocado.rep_min, trocado.rep_max), (Measure.REPS, 6, 10)
        )

    def test_o_degrau_do_iniciante_tambem_veste_a_unidade(self):
        """O segundo ponto de cópia. Nenhum degrau alto de sustentação existe
        hoje no catálogo, então o degrau é fabricado aqui: uma prancha de nível
        5 em repetições desce para a prancha (nível 2), que é tempo."""
        alto = Exercise.objects.create(
            name="Prancha com peso (teste)", muscle_group="core", equipment="bodyweight",
            padrao="anti_extensao", progressao={"movimento": "prancha", "nivel": 5},
        )
        item = SessionExercise(exercise=alto, sets=3, rep_min=10, rep_max=12, rest_seconds=60, order=1)
        catalogo = services.catalogo_permitido({"bodyweight"})
        [trocado] = services.ajustar_degrau_do_iniciante([item], "iniciante", {"bodyweight"}, catalogo)
        self.assertEqual(trocado.exercise.name, "Prancha abdominal")
        self.assertEqual((trocado.measure, trocado.rep_min, trocado.rep_max), (Measure.SECONDS, 30, 45))

    def test_a_troca_da_pessoa_veste_a_unidade_so_em_memoria(self):
        """O terceiro ponto de cópia ("outras formas"): a execução mede em
        segundos, e a linha gravada da ficha NÃO muda — plano é retrato."""
        user = pessoa("m13-troca@exemplo.com")
        sessao = tornar_hoje(user, "C")
        linha = next(i for i in sessao.exercises.all() if i.exercise.name == "Cadeira extensora")
        TrocaDeExercicio.objects.create(
            user=user, original=linha.exercise, substituto=Exercise.objects.get(name="Cadeira na parede"),
        )
        estado = services.estado_do_treino(user)
        item = next(i for i in estado.itens if i.exercise.name == "Cadeira na parede")
        self.assertEqual((item.measure, item.rep_min, item.rep_max), (Measure.SECONDS, 30, 45))
        linha.refresh_from_db()
        self.assertEqual((linha.measure, linha.rep_min, linha.rep_max), (Measure.REPS, 12, 15))

    def test_ficha_nova_de_peso_do_corpo_prescreve_sustentacao_em_segundos(self):
        """O caso da captura `m13-isometria-em-reps-390e.png`: a suspensão na
        barra no lugar da rosca de punho, ficha de peso do corpo."""
        user = create_complete_user(
            email="m13-casa@exemplo.com", experiencia="intermediario",
            split_preference="two", split_preference_confirmada=True, equipamento="peso_corporal",
        )
        plano = services.create_routine(user)
        itens = list(
            SessionExercise.objects.filter(session__plan=plano, exercise__name__in=SUSTENTACOES)
            .select_related("exercise")
        )
        self.assertTrue(itens, "a ficha de peso do corpo não tem sustentação nenhuma")
        for item in itens:
            with self.subTest(exercicio=item.exercise.name):
                self.assertEqual((item.measure, item.rep_min, item.rep_max), (Measure.SECONDS, 30, 45))
        # E a ficha que acabou de nascer é a que o motor produziria hoje.
        self.assertFalse(services.rotina_desatualizada(plano, user))


# ----------------------------------------------------------------- M14/M15


class ASerieAlemDaPrescritaTests(BaseDoFluxo):
    """M14: a aba velha gravava uma 4ª série por cima, sem aviso. M15: essa
    série sumia da execução e somava no volume do placar."""

    def setUp(self):
        self.user = pessoa("m14@exemplo.com")
        tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        estado = services.estado_do_treino(self.user)
        self.item = next(i for i in estado.itens if not i.exercise.sem_carga)
        self.exercicio = self.item.exercise
        for numero in range(1, self.item.sets):
            services.record_load(self.user, self.exercicio, Decimal("30"), set_number=numero, reps=10)

    def _serie(self, op_id, **extra):
        corpo = {
            "exercise_id": self.exercicio.pk, "weight_kg": "32,5", "reps": "9",
            "op_id": op_id, "exercicio": self.exercicio.pk,
        }
        corpo.update(extra)
        return self.client.post(reverse("workouts:record_set"), corpo, follow=True)

    def _gravadas(self):
        return ExerciseLog.objects.filter(user=self.user, exercise=self.exercicio).count()

    def test_a_aba_velha_nao_grava_serie_alem_da_prescrita(self):
        self._serie("aba-nova")
        self.assertEqual(self._gravadas(), self.item.sets)
        resposta = self._serie("aba-velha")
        self.assertEqual(self._gravadas(), self.item.sets)
        texto = texto_visivel(resposta.content.decode())
        self.assertIn("já estavam registradas", texto)
        self.assertIn("não foi gravada", texto)
        # Volta para o exercício, onde mora a porta da série a mais.
        self.assertEqual(
            resposta.redirect_chain[-1][0],
            "%s?exercicio=%d" % (reverse("workouts:now"), self.exercicio.pk),
        )
        self.assertIn("Registrar uma série a mais", texto)

    def test_reenvio_da_mesma_serie_continua_aceito(self):
        """Idempotência da fila offline: o MESMO `op_id` reenviado depois de a
        série fechar a conta não é "série a mais" — é a mesma série."""
        self._serie("mesma-serie")
        resposta = self._serie("mesma-serie")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self._gravadas(), self.item.sets)
        self.assertNotIn("não foi gravada", texto_visivel(resposta.content.decode()))

    def test_o_reenvio_da_fila_depois_do_limite_sai_da_fila_sem_gravar(self):
        """A drenagem de um toque a mais recebe 200 ("processado") e sai da
        fila: 5xx a manteria reenviando para sempre."""
        self._serie("fecha-a-conta")
        resposta = self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": self.exercicio.pk, "weight_kg": "30", "reps": "8", "op_id": "toque-a-mais"},
            HTTP_X_REQUESTED_WITH="fetch", HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(self.user.pk),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self._gravadas(), self.item.sets)
        # E o mesmo toque reenviado da fila, com o op_id que JÁ gravou, passa.
        resposta = self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": self.exercicio.pk, "weight_kg": "30", "reps": "8", "op_id": "fecha-a-conta"},
            HTTP_X_REQUESTED_WITH="fetch", HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(self.user.pk),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self._gravadas(), self.item.sets)

    def test_a_serie_a_mais_pedida_continua_sendo_gravada(self):
        """Controle positivo: "Registrar uma série a mais" é pedido explícito."""
        self._serie("fecha-a-conta")
        self._serie("a-mais", extra="1")
        self.assertEqual(self._gravadas(), self.item.sets + 1)

    def test_o_formulario_da_serie_a_mais_leva_o_pedido(self):
        services.record_load(
            self.user, self.exercicio, Decimal("30"), set_number=self.item.sets, reps=10
        )
        url = "%s?exercicio=%d" % (reverse("workouts:now"), self.exercicio.pk)
        campo = '<input type="hidden" name="extra" value="1">'
        self.assertIn(campo, self.client.get(url + "&extra=1").content.decode())
        # Controle: o formulário de sempre não pede série a mais.
        outro = next(i for i in services.estado_do_treino(self.user).itens if not i.concluido)
        html = self.client.get("%s?exercicio=%d" % (reverse("workouts:now"), outro.exercise_id)).content.decode()
        self.assertIn('<form class="registro', html)
        self.assertNotIn(campo, html)

    def _treino_inteiro_com_uma_a_mais(self):
        hoje = services.timezone.localdate()
        for item in services.estado_do_treino(self.user).itens:
            for numero in range(1, item.sets + 1):
                ExerciseLog.objects.get_or_create(
                    user=self.user, exercise=item.exercise, date=hoje,
                    set_number=numero, defaults={"weight_kg": Decimal("20"), "reps": 10},
                )
        # A série a mais PEDIDA: 35 kg × 8.
        self._serie("a-mais-35", extra="1", weight_kg="35", reps="8")
        return ExerciseLog.objects.filter(user=self.user, date=hoje)

    def test_duas_perguntas_uma_regua_cada(self):
        """M15, revisão de 28/09/2026. "O que eu fiz?" conta TODA série
        gravada — séries, reps e volume, com a série a mais pedida, que é
        trabalho real. "Quanto do plano?" é `progresso_em_series`, recortada
        na ficha: não passa de 100 %. Na mesma tela, "N séries registradas" e
        "X kg" são o MESMO conjunto de linhas."""
        todas = self._treino_inteiro_com_uma_a_mais()
        estado = services.estado_do_treino(self.user)
        self.assertTrue(estado.concluido)
        # O que eu fiz: todas.
        self.assertEqual(estado.placar.series, todas.count())
        self.assertEqual(estado.placar.carga_total, sum(log.weight_kg * log.reps for log in todas))
        self.assertEqual(estado.placar.repeticoes, sum(log.reps for log in todas))
        # Controle — quanto do plano: a fração continua recortada.
        self.assertEqual(estado.series_feitas, estado.total_series)
        self.assertEqual(estado.series_feitas, todas.count() - 1)
        self.assertEqual(estado.pct, 100)
        # Na tela, "séries registradas" e o cartão de compartilhar são o placar.
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn(
            '<span class="fim__valor num">%d</span>' % todas.count(), html,
        )
        self.assertIn('data-compartilhar-series="%d"' % todas.count(), html)

    def test_a_execucao_e_o_treino_de_hoje_dizem_os_mesmos_kg(self):
        """Antes da revisão, a execução dizia 3.965 kg e `/treino/` ("Treino
        de hoje") 4.315 kg no mesmo dia — os dois cartões de compartilhar do
        mesmo treino com números diferentes."""
        self._treino_inteiro_com_uma_a_mais()
        execucao = self.client.get(reverse("workouts:now")).context["estado"].placar
        resumo = self.client.get(reverse("workouts:routine")).context["resumo_hoje"]
        self.assertEqual(execucao.carga_total, resumo.volume_kg)
        self.assertEqual(execucao.series, resumo.series)

    def test_a_serie_a_mais_offline_com_o_pedido_e_gravada_na_drenagem(self):
        """F1 da revisão (CRITICAL): offline, a tela escreve "Concluído — 4 de
        4" e continua oferecendo "Concluir série 5"; o toque seguinte leva
        `extra=1` (`pwa.js`, `serieEnfileirada`) e a drenagem o grava."""
        self._serie("fecha-a-conta")
        resposta = self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": self.exercicio.pk, "weight_kg": "30", "reps": "8",
             "op_id": "offline-a-mais", "extra": "1"},
            HTTP_X_REQUESTED_WITH="fetch", HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(self.user.pk),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self._gravadas(), self.item.sets + 1)


class ASerieAMaisOfflineLevaOPedidoTests(SimpleTestCase):
    """F1 da revisão (CRITICAL, 28/09/2026). Offline, `serieEnfileirada`
    escreve "Concluído — 4 de 4" e deixa o formulário com "Concluir série
    5". Sem `extra=1` no corpo, o toque seguinte seria recusado na drenagem
    como o da aba velha — e a fila o apagaria calada, depois de a tela dizer
    "Série guardada". Régua estrutural, como `push.test_toque_offline_na_tela`
    (sem Node no ambiente); a drenagem que grava está em
    `ASerieAlemDaPrescritaTests.test_a_serie_a_mais_offline_com_o_pedido_e_gravada_na_drenagem`."""

    def test_passada_a_ficha_o_formulario_ganha_o_pedido_uma_vez(self):
        from push.test_toque_offline_na_tela import PWA, sem_comentarios

        js = sem_comentarios(PWA.read_text(encoding="utf-8"))
        funcao = js.split("function serieEnfileirada", 1)[1].split('addEventListener("nutriplan:enfileirado"', 1)[0]
        ramo = funcao.split("n + 1 > m) {", 1)[1].split("} else {", 1)[0]
        self.assertIn("if (!form.querySelector('input[name=\"extra\"]'))", ramo)
        self.assertIn('pedido.type = "hidden";', ramo)
        self.assertIn('pedido.name = "extra";', ramo)
        self.assertIn('pedido.value = "1";', ramo)
        self.assertIn("form.appendChild(pedido);", ramo)
        # Controle: o ramo de dentro da ficha não pede série a mais.
        dentro = funcao.split("} else {", 1)[1].split("}", 1)[0]
        self.assertNotIn("extra", dentro)


class ODesfazerOfflineNaoViraSerieTests(SimpleTestCase):
    """Revisão N3 (anterior a esta tarefa): o desfazer posta na MESMA rota, e
    `serieEnfileirada` o tratava como série nova — "✓" na pastilha, contador
    adiantado, "Série guardada" e, desde o F1, `extra=1` no formulário de
    desfazer. Régua estrutural (sem Node): o desfazer sai antes de tudo isso."""

    def test_o_desfazer_sai_antes_da_pastilha_do_contador_e_do_pedido(self):
        from push.test_toque_offline_na_tela import PWA, sem_comentarios

        js = sem_comentarios(PWA.read_text(encoding="utf-8"))
        funcao = js.split("function serieEnfileirada", 1)[1].split('addEventListener("nutriplan:enfileirado"', 1)[0]
        guarda = 'if (valorDoPar(dados, "acao") === "desfazer") {'
        self.assertIn(guarda, funcao)
        ramo = funcao.split(guarda, 1)[1].split("}", 1)[0]
        self.assertIn("return;", ramo)
        self.assertNotIn("Série guardada", ramo)
        self.assertLess(funcao.index(guarda), funcao.index("series__item--atual"))
        self.assertLess(funcao.index(guarda), funcao.index('pedido.name = "extra"'))


class AFichaDizAUltimaVezSemNoneEEmSegundosTests(BaseDoFluxo):
    """Revisão N4: a ficha repetia o resíduo do F4 — "None reps" na flexão
    anotada sem reps e "40 reps" na prancha, que são 40 SEGUNDOS."""

    def setUp(self):
        self.user = pessoa("n4-ficha@exemplo.com")
        tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        self.sessoes = {s.label: s for s in self.user.training_plans.get(is_active=True).sessions.all()}

    def _texto(self, letra):
        url = reverse("workouts:ficha", args=[self.sessoes[letra].pk])
        return texto_visivel(self.client.get(url).content.decode())

    def test_sem_carga_e_sem_reps_a_ficha_nao_diz_none(self):
        ExerciseLog.objects.create(
            user=self.user, exercise=Exercise.objects.get(name="Flexão de braço"), date=ANTES,
            set_number=1, weight_kg=Decimal("0"), reps=None,
        )
        # Controle: a ficha continua dizendo a última vez de quem tem número.
        _log(self.user, Exercise.objects.get(name="Supino reto com barra"), 40, 8, 1)
        texto = self._texto("A")
        self.assertNotIn("None", texto)
        self.assertIn("Última vez: 40 kg × por 8", texto)

    def test_a_sustentacao_na_ficha_diz_segundos(self):
        _log(self.user, Exercise.objects.get(name="Prancha abdominal"), 0, 40, 1)
        texto = self._texto("C")
        self.assertIn("Última vez: 40 s", texto)
        self.assertNotIn("40 reps", texto)


# --------------------------------------------------------------------- M20


class ORecordeDeAssistidaEMenosCargaTests(BaseDoFluxo):
    """M20: na barra fixa assistida, a carga anotada é AJUDA. 25 kg → 45 kg
    é regressão, e virava "RECORDE · MELHOR SÉRIE" e "Novo recorde"."""

    def setUp(self):
        self.user = pessoa("m20@exemplo.com")
        tornar_hoje(self.user, "B")
        self.client.force_login(self.user)
        self.assistida = Exercise.objects.get(name="Barra fixa assistida")
        _log(self.user, self.assistida, 25, 8, 1)
        _log(self.user, self.assistida, 30, 8, 2)

    def _serie(self, peso, op_id):
        return self.client.post(reverse("workouts:record_set"), {
            "exercise_id": self.assistida.pk, "weight_kg": peso, "reps": "8",
            "op_id": op_id, "exercicio": self.assistida.pk,
        })

    def _html(self):
        return self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.assistida.pk)
        ).content.decode()

    def test_o_catalogo_marca_a_barra_assistida(self):
        self.assertTrue(self.assistida.assistido)
        # Controle: a barra sem assistência e a puxada são carga de verdade.
        for nome in ("Barra fixa pronada", "Puxada frente na polia"):
            with self.subTest(exercicio=nome):
                self.assertFalse(Exercise.objects.get(name=nome).assistido)

    def test_mais_assistencia_nao_e_recorde(self):
        self.assertEqual(services.supera_recorde(self.user, self.assistida, Decimal("45"), reps=8), set())
        self._serie("45", "mais-ajuda")
        self.assertNotIn('<span class="series__recorde">', self._html())
        conquistas.avaliar(self.user)
        self.assertFalse(
            UserAchievement.objects.filter(user=self.user, slug__in=("novo-recorde", "melhor-serie")).exists()
        )
        estado = services.estado_do_treino(self.user, escolhido=self.assistida.pk)
        self.assertEqual(services.placar_do_treino(estado.itens).recordes, 0)

    def test_menos_assistencia_e_o_recorde(self):
        self.assertEqual(
            services.supera_recorde(self.user, self.assistida, Decimal("20"), reps=8), {"carga"}
        )
        # Menos ajuda que a ÚLTIMA (30) mas não que a MELHOR (25) não é recorde.
        self.assertEqual(
            services.supera_recorde(self.user, self.assistida, Decimal("28"), reps=8), set()
        )
        historico = services.load_history(self.user, [self.assistida])[self.assistida.pk]
        self.assertEqual(historico["recorde_anterior"], Decimal("25"))
        self.assertIsNone(historico["melhor_serie_anterior"])
        self._serie("20", "menos-ajuda")
        html = self._html()
        self.assertIn('<span class="series__recorde">recorde</span>', html)
        self.assertNotIn('<span class="series__recorde">melhor série</span>', html)
        # A conquista segue a mesma régua: menos ajuda é "Novo recorde".
        slugs = set(UserAchievement.objects.filter(user=self.user).values_list("slug", flat=True))
        self.assertIn("novo-recorde", slugs)
        self.assertNotIn("melhor-serie", slugs)
        # E o placar: com 20 e 45 hoje, a série que conta é a de MENOS ajuda.
        self._serie("45", "mais-ajuda-depois")
        estado = services.estado_do_treino(self.user, escolhido=self.assistida.pk)
        self.assertEqual(services.placar_do_treino(estado.itens).recordes, 1)

    def test_hoje_e_ultima_vez_seguem_a_ajuda(self):
        """F3 da revisão: com 45 de ajuda hoje, "Hoje: ▲ +15 kg" saía VERDE ao
        lado de "Recorde: 25 kg". O número e a seta são o fato; a cor diz se
        melhorou. "Última carga" é a MENOR ajuda da última vez."""
        self._serie("45", "mais-ajuda")
        historico = services.load_history(self.user, [self.assistida])[self.assistida.pk]
        self.assertEqual(historico["melhor_anterior"], Decimal("25"))
        self.assertEqual(historico["melhor_hoje"], Decimal("45"))
        self.assertFalse(historico["progrediu"])
        self.assertIn('<b class="agora__delta agora__delta--down">▲ +20 kg</b>', self._html())
        # Menos ajuda que a última vez: seta para baixo, e é progresso.
        self._serie("20", "menos-ajuda")
        self.assertIn('<b class="agora__delta agora__delta--up">▼ -5 kg</b>', self._html())

    def test_controle_na_remada_mais_carga_e_progresso(self):
        remada = Exercise.objects.get(name="Remada baixa na polia")
        _log(self.user, remada, 40, 10, 1)
        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": remada.pk, "weight_kg": "50", "reps": "10", "op_id": "remada-50",
        })
        historico = services.load_history(self.user, [remada])[remada.pk]
        self.assertTrue(historico["progrediu"])
        html = self.client.get("%s?exercicio=%d" % (reverse("workouts:now"), remada.pk)).content.decode()
        self.assertIn('<b class="agora__delta agora__delta--up">▲ +10 kg</b>', html)

    def test_assistida_nao_recebe_sugestao_de_subir(self):
        """F3: "Sugestão: subir 32,5 kg — fechou 4×10 na última vez" na barra
        assistida mandava pedir MAIS ajuda. A regra do passo certo (menos
        ajuda) não foi decidida; silêncio vence conselho errado."""
        remada = Exercise.objects.get(name="Remada baixa na polia")
        doses = {i.exercise_id: (i.sets, i.rep_max) for i in services.estado_do_treino(self.user).itens}
        for exercicio, peso in ((self.assistida, 30), (remada, 40)):
            series, reps = doses[exercicio.pk]
            for numero in range(1, series + 1):
                _log(self.user, exercicio, peso, reps, numero, dia=date(2026, 9, 15))
        estado = services.estado_do_treino(self.user, escolhido=self.assistida.pk)
        self.assertIsNone(estado.atual.progressao)
        self.assertNotIn("Sugestão: subir", texto_visivel(self._html()))
        # Controle: a remada, com a mesma história, sobe.
        estado = services.estado_do_treino(self.user, escolhido=remada.pk)
        self.assertEqual(estado.atual.progressao.rotulo, "subir")
        html = self.client.get("%s?exercicio=%d" % (reverse("workouts:now"), remada.pk)).content.decode()
        self.assertIn("Sugestão: subir", texto_visivel(html))

    def test_a_ultima_vez_da_assistida_e_a_menor_ajuda(self):
        """Revisão N1: "última: 30 kg × 8" logo acima do campo, e na mesma
        tela "Última carga (14/09): 25 kg" e "Recorde: 25 kg". A última vez
        é a MELHOR série daquele dia — na assistida, a de menos ajuda."""
        self.assertIn("última: 25 kg × 8 14/09", texto_visivel(self._html()))
        # Controle: no exercício comum, a mais pesada.
        remada = Exercise.objects.get(name="Remada baixa na polia")
        _log(self.user, remada, 40, 10, 1)
        _log(self.user, remada, 50, 8, 2)
        html = self.client.get("%s?exercicio=%d" % (reverse("workouts:now"), remada.pk)).content.decode()
        self.assertIn("última: 50 kg × 8 14/09", texto_visivel(html))

    def test_controle_exercicio_comum_segue_a_maior_carga(self):
        remada = Exercise.objects.get(name="Remada baixa na polia")
        self.assertFalse(remada.assistido)
        _log(self.user, remada, 40, 10, 1)
        self.assertEqual(services.supera_recorde(self.user, remada, Decimal("50"), reps=10), {"carga", "melhor_serie"})
        self.assertEqual(services.supera_recorde(self.user, remada, Decimal("30"), reps=10), set())


# --------------------------------------------------------------------- BA11


class AVoltaDoNavegadorRecarregaAExecucaoTests(BaseDoFluxo):
    """BA11: `forward` 16 s depois mostrava o descanso em 1:13 congelado e
    "2/24 séries" com a 3ª já gravada. Sem Node no ambiente (CLAUDE.md), a
    régua lê o `pwa.js`; a prova de comportamento é a do navegador, no
    relatório da tarefa."""

    PWA = settings.BASE_DIR / "static" / "js" / "pwa.js"

    def _tratador_do_bfcache(self):
        js = self.PWA.read_text(encoding="utf-8")
        inicio = js.index('window.addEventListener("pageshow", function (evento) {')
        return js[inicio:js.index("});", js.index("catch(", inicio))]

    def test_a_execucao_restaurada_do_bfcache_e_recarregada(self):
        tratador = self._tratador_do_bfcache()
        self.assertIn("if (!evento.persisted) return;", tratador)
        self.assertRegex(
            tratador,
            r'r\.ok && document\.documentElement\.classList\.contains\("modo-foco"\)\) location\.reload\(\)',
        )

    def test_controle_a_execucao_e_a_tela_modo_foco(self):
        user = pessoa("ba11@exemplo.com")
        tornar_hoje(user, "A")
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn('<html lang="pt-br" class="modo-foco"', html)
        # E a tela comum não é: voltar para ela continua sem recarga.
        self.assertNotIn('class="modo-foco"', self.client.get(reverse("workouts:routine")).content.decode())


# ------------------------------------------------------------------- item 7


class OBotaoDoYoutubeTemAlvoDeToqueTests(SimpleTestCase):
    """"Buscar no YouTube" media 21 px de altura: um `<a>` cru. `btn
    btn--ghost` já existe (`.btn { min-height: 3.25rem }`)."""

    def _html(self, **campos):
        return render_to_string(
            "workouts/_demonstracao.html",
            {"exercicio": Exercise(name="Cadeira na parede", cue="Segure.", **campos)},
        )

    def test_sem_demonstracao_o_link_e_um_botao(self):
        html = self._html()
        self.assertRegex(
            html,
            r'<a class="btn btn--ghost" href="https://www\.youtube\.com/results\?search_query=[^"]+"'
            r' target="_blank" rel="noopener">\s*Buscar no YouTube\s*</a>',
        )

    def test_controle_com_video_nao_ha_busca(self):
        html = self._html(video_url="https://www.youtube.com/shorts/lRCROSJkTKM")
        self.assertNotIn("Buscar no YouTube", html)
        self.assertIn("ver vídeo", html)
