# -*- coding: utf-8 -*-
"""O ciclo da divisão roda CONTÍNUO (17/09/2026): a semana seguinte continua
de onde a anterior parou.

O desequilíbrio que motivou isto era do CALENDÁRIO, não do motor: em cinco
dias com ABC o ciclo fixo A B C A B recomeçava toda segunda-feira, e a letra
C — "Pernas e ombros" — caía uma vez por semana para sempre, enquanto peito e
costas caíam duas. Com a rotação, A B C A B → C A B C A → B C A B C: em três
semanas cada letra cai cinco vezes, e o volume MÉDIO por grupo é o da
frequência 5/3.

O que fica prendido aqui:

- a letra de um dia sai da POSIÇÃO dele no ciclo, contada pelo calendário
  (`posicao_no_ciclo`), não pelo dia da semana;
- painel, ficha e execução mostram e executam a letra da posição;
- o histórico (`ExerciseLog`, por exercício e data) e a escolha
  (`EscolhaDeTreino`, por data e SESSÃO-letra) seguem a letra;
- plano de antes da rotação (`inicio_do_ciclo` em branco) continua preso ao
  dia da semana — a política da Fase 5: não remonta, a Home pergunta.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import DuracaoTreino, TrainingDay
from plans.tests import create_complete_user
from workouts import doutrina, services
from workouts.models import EscolhaDeTreino, ExerciseLog, TrainingPlan

#: Uma segunda-feira: o plano nasce nela, e a posição zero é ela.
SEGUNDA = date(2026, 9, 14)


def _congelar(dia):
    patcher = mock.patch("django.utils.timezone.localdate", return_value=dia)
    patcher.start()
    return patcher


def _pessoa(email, dias=5, preferencia="two", nivel="intermediario", duracao=DuracaoTreino.PADRAO):
    user = create_complete_user(
        email=email, experiencia=nivel, split_preference=preferencia,
        split_preference_confirmada=True, duracao_treino=duracao,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


class OCicloRodaContinuoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.stop)
        self.user = _pessoa("ciclo@exemplo.com")
        self.plan = services.create_routine(self.user)

    def _letras(self, semanas):
        return [
            services.letra_do_dia(self.plan, SEGUNDA + timedelta(days=7 * s + d))
            for s in range(semanas) for d in range(5)
        ]

    def test_o_plano_nasce_com_a_posicao_zero_no_primeiro_dia_de_treino(self):
        self.assertEqual(self.plan.inicio_do_ciclo, SEGUNDA)
        self.assertEqual(self.plan.split, "abc2")

    def test_quem_entra_no_meio_da_semana_faz_a_semana_de_sempre_e_roda_depois(self):
        """Plano nascido na quarta: a posição zero é a segunda desta semana,
        a quarta é C — como as linhas dizem e como sempre foi — e a segunda
        seguinte é a posição 5, letra C. A primeira semana é a de sempre; a
        rotação começa na segunda."""
        self.relogio.stop()
        self.relogio = _congelar(SEGUNDA + timedelta(days=2))
        self.addCleanup(self.relogio.stop)
        user = _pessoa("quarta@exemplo.com")
        plan = services.create_routine(user)
        self.assertEqual(plan.inicio_do_ciclo, SEGUNDA)
        self.assertEqual(services.letra_do_dia(plan, SEGUNDA + timedelta(days=2)), "C")
        self.assertEqual(services.letra_do_dia(plan, SEGUNDA + timedelta(days=7)), "C")

    def test_a_semana_seguinte_continua_de_onde_parou(self):
        self.assertEqual(self._letras(1), ["A", "B", "C", "A", "B"])
        self.assertEqual(self._letras(2)[5:], ["C", "A", "B", "C", "A"])
        self.assertEqual(self._letras(3)[10:], ["B", "C", "A", "B", "C"])

    def test_em_tres_semanas_cada_letra_cai_cinco_vezes(self):
        self.assertEqual(Counter(self._letras(3)), {"A": 5, "B": 5, "C": 5})
        # E depois de três semanas o ciclo volta ao começo.
        self.assertEqual(self._letras(4)[15:], ["A", "B", "C", "A", "B"])

    def test_dia_sem_treino_nao_tem_letra_e_nao_conta_posicao(self):
        sabado = SEGUNDA + timedelta(days=5)
        self.assertIsNone(services.letra_do_dia(self.plan, sabado))
        self.assertIsNone(services.sessao_do_dia(self.plan, sabado))
        # O fim de semana não avança o ciclo: a segunda seguinte é a posição 5.
        self.assertEqual(services.letra_do_dia(self.plan, SEGUNDA + timedelta(days=7)), "C")

    def test_a_posicao_e_do_calendario_nao_do_treino_feito(self):
        """Pular o treino de terça não muda a letra de quarta: o quadro da
        academia anda com o calendário. (Nenhum registro é criado aqui.)"""
        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), 0)
        self.assertEqual(services.letra_do_dia(self.plan, SEGUNDA + timedelta(days=2)), "C")

    def test_com_dias_alternados_a_posicao_pula_o_descanso(self):
        """Segunda, quarta e sexta: a sexta é a posição 2 (C), não a 4 — o
        dia de descanso não conta posição. Duas semanas: A B C A B C."""
        user = create_complete_user(
            email="alternado@exemplo.com", experiencia="intermediario", split_preference="three",
            split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO,
        )
        TrainingDay.objects.filter(user=user).delete()
        for d in (0, 2, 4):
            TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
        plan = services.create_routine(user)
        letras = [
            services.letra_do_dia(plan, SEGUNDA + timedelta(days=7 * s + d))
            for s in range(2) for d in (0, 2, 4)
        ]
        self.assertEqual(letras, ["A", "B", "C", "A", "B", "C"])
        self.assertIsNone(services.letra_do_dia(plan, SEGUNDA + timedelta(days=1)))

    def test_a_sessao_do_dia_veste_o_horario_do_dia_e_e_a_linha_da_letra(self):
        TrainingDay.objects.filter(user=self.user, weekday=0).update(duration_min=45)
        plan = services.create_routine(self.user)
        segunda_2 = SEGUNDA + timedelta(days=7)  # posição 5: letra C
        sessao = services.sessao_do_dia(plan, segunda_2)
        self.assertEqual(sessao.label, "C")
        self.assertEqual(sessao.weekday, 0)
        self.assertEqual(sessao.duration_min, 45, "a duração é a de segunda, não a de quarta")
        linha_c = plan.sessions.filter(label="C").order_by("order").first()
        self.assertEqual(sessao.pk, linha_c.pk, "a ficha é a da letra")
        self.assertEqual(sessao.data, segunda_2)

    def test_as_linhas_continuam_sendo_o_retrato_dos_dias(self):
        """Uma linha por dia de treino, com a letra da primeira semana: é o
        que `rotina_invalida` compara com os dias cadastrados."""
        linhas = list(self.plan.sessions.order_by("order"))
        self.assertEqual([s.weekday for s in linhas], [0, 1, 2, 3, 4])
        self.assertEqual([s.label for s in linhas], ["A", "B", "C", "A", "B"])
        self.assertFalse(services.rotina_invalida(self.plan, self.user))
        self.assertFalse(services.rotina_desatualizada(self.plan, self.user))

    def test_o_teto_semanal_e_o_da_pior_semana_para_toda_letra(self):
        """Com a rotação toda letra cai duas vezes em alguma semana: o teto
        e o número de opções de C são os de 2×, como os de A e B."""
        ocorrencias = services.ocorrencias_das_letras(list(self.plan.sessions.all()))
        self.assertEqual(ocorrencias, {"A": 2, "B": 2, "C": 2})
        tetos = services.tetos_da_semana(self.plan)
        self.assertEqual(tetos["quads"], doutrina.teto_semanal("intermediario", 2))
        self.assertEqual(tetos["chest"], doutrina.teto_semanal("intermediario", 2))


class OPainelEAFichaMostramALetraDaPosicaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.stop)
        self.user = _pessoa("painel-ciclo@exemplo.com")
        from plans import services as plan_services

        plan_services.create_plan(self.user)
        self.plan = services.create_routine(self.user)
        self.client.force_login(self.user)

    def _na_segunda_semana(self):
        self.relogio.stop()
        self.relogio = _congelar(SEGUNDA + timedelta(days=7))
        self.addCleanup(self.relogio.stop)

    def test_o_painel_na_segunda_semana_abre_com_a_letra_c(self):
        self._na_segunda_semana()
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["hoje"].label, "C")
        letras = {c["label"]: c for c in resposta.context["letras"]}
        self.assertEqual(letras["C"]["dias"], ["Segunda-feira", "Quinta-feira"])
        self.assertEqual(letras["A"]["dias"], ["Terça-feira", "Sexta-feira"])
        self.assertEqual(letras["B"]["dias"], ["Quarta-feira"])
        semana = [d["session"].label if d["session"] else None for d in resposta.context["week"]]
        self.assertEqual(semana, ["C", "A", "B", "C", "A", None, None])

    def test_na_primeira_semana_o_painel_e_o_de_sempre(self):
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertEqual(resposta.context["hoje"].label, "A")
        semana = [d["session"].label if d["session"] else None for d in resposta.context["week"]]
        self.assertEqual(semana, ["A", "B", "C", "A", "B", None, None])

    def test_o_painel_diz_que_o_ciclo_gira(self):
        """Avaliação de UX (20/09/2026): a tira mostra a rotação da semana
        corrente (os testes acima provam), MAS sem dizer que ela GIRA a pessoa a
        lê como fixa e estranha o "próximo treino" da semana seguinte cair
        noutra letra (tira SEG=A × próximo=C). A legenda entra quando o ciclo
        roda."""
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertTrue(resposta.context["ciclo_continuo"])
        html = resposta.content.decode()
        self.assertIn("week-strip__ciclo", html)
        self.assertIn("ciclo gira", html)

    def test_plano_preso_ao_dia_da_semana_nao_diz_que_gira(self):
        """Plano de antes da rotação fica preso ao dia da semana — dizer "gira"
        ali seria mentira, então a legenda não aparece."""
        TrainingPlan.objects.filter(pk=self.plan.pk).update(inicio_do_ciclo=None)
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertFalse(resposta.context["ciclo_continuo"])
        self.assertNotIn("week-strip__ciclo", resposta.content.decode())

    def test_a_leitura_do_exercicio_avisa_que_o_ciclo_gira(self):
        """O "Quando" da leitura lista os dias DESTA semana; com o ciclo
        girando, sem o aviso ele é lido como fixo, e quem chega pela ficha da
        semana que vem estranha a letra cair noutro dia (avaliação de UX)."""
        sessao = self.plan.sessions.first()
        ex = sessao.exercises.first().exercise
        resposta = self.client.get(
            reverse("workouts:exercicio", args=[ex.pk]) + "?de=ficha&sessao=%d" % sessao.pk
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["ciclo_continuo"])
        self.assertIn("o ciclo gira", resposta.content.decode())

    def test_o_proximo_treino_atravessa_a_semana_com_a_letra_certa(self):
        """Sexta da primeira semana: o próximo é segunda — e é C, não A."""
        self.relogio.stop()
        self.relogio = _congelar(SEGUNDA + timedelta(days=5))  # sábado
        self.addCleanup(self.relogio.stop)
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertIsNone(resposta.context["hoje"])
        proximo = resposta.context["proximo"]
        self.assertEqual(proximo["dias"], 2)
        self.assertEqual(proximo["session"].label, "C")

    def test_a_ficha_da_letra_de_hoje_e_hoje_e_diz_os_dias_desta_semana(self):
        self._na_segunda_semana()
        linha_c = self.plan.sessions.filter(label="C").order_by("order").first()
        resposta = self.client.get(reverse("workouts:ficha", args=[linha_c.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["sessao"].eh_hoje)
        self.assertIn("Segunda-feira · Quinta-feira", resposta.content.decode())
        linha_a = self.plan.sessions.filter(label="A").order_by("order").first()
        resposta = self.client.get(reverse("workouts:ficha", args=[linha_a.pk]))
        self.assertFalse(resposta.context["sessao"].eh_hoje)

    def test_a_execucao_abre_a_letra_de_hoje_e_a_primeira_serie_pina_a_variacao(self):
        """Na segunda semana a segunda é C: a execução abre C, na variação
        do ciclo (segunda ocorrência de C → opção 2), e a primeira série
        grava a escolha na LINHA de C — não na linha de segunda."""
        self._na_segunda_semana()
        linhas = list(self.plan.sessions.all())
        linha_c = next(s for s in linhas if s.label == "C")
        estado = services.estado_do_treino(self.user)
        self.assertEqual(estado.sessao.label, "C")
        self.assertEqual(estado.opcao, services.variacao_do_dia(self.plan, SEGUNDA + timedelta(days=7), estado.sessao, linhas))
        item = estado.itens[0]
        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": item.exercise_id, "weight_kg": "40", "reps": "8", "op_id": "op-c",
            "dia": (SEGUNDA + timedelta(days=7)).isoformat(),
            "sessao": estado.sessao.pk, "opcao": estado.opcao, "versao": estado.versao,
        })
        escolha = EscolhaDeTreino.objects.get(user=self.user)
        self.assertEqual((escolha.session_id, escolha.opcao), (linha_c.pk, estado.opcao))

    def test_a_serie_gravada_hoje_conta_na_ficha_da_letra_de_hoje(self):
        self._na_segunda_semana()
        estado = services.estado_do_treino(self.user)
        item = estado.itens[0]
        ExerciseLog.objects.create(
            user=self.user, exercise=item.exercise, date=SEGUNDA + timedelta(days=7),
            set_number=1, weight_kg=Decimal("40"), reps=10,
        )
        feitas, prescritas = services.series_de_hoje(self.user, item.exercise)
        self.assertEqual((feitas, prescritas), (1, item.sets))
        resposta = self.client.get(reverse("workouts:routine"))
        hoje = resposta.context["hoje"]
        self.assertEqual(hoje.label, "C")
        self.assertGreaterEqual(hoje.feitos_hoje, 1, "a série de hoje conta na letra de hoje")


class OPlanoAntigoContinuaPresoAoDiaDaSemanaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.stop)
        self.user = _pessoa("antigo-ciclo@exemplo.com")
        self.plan = services.create_routine(self.user)
        TrainingPlan.objects.filter(pk=self.plan.pk).update(inicio_do_ciclo=None)
        self.plan.refresh_from_db()

    def test_a_letra_e_a_do_dia_da_semana_em_toda_semana(self):
        for semana in range(3):
            self.assertEqual(
                [services.letra_do_dia(self.plan, SEGUNDA + timedelta(days=7 * semana + d)) for d in range(5)],
                ["A", "B", "C", "A", "B"],
            )

    def test_nao_e_remontado_e_a_home_pergunta(self):
        self.assertFalse(services.rotina_invalida(self.plan, self.user))
        self.assertTrue(services.rotina_desatualizada(self.plan, self.user))
        depois, mudou = services.sync_active_routine(self.user)
        self.assertFalse(mudou)
        self.assertEqual(depois.pk, self.plan.pk)

    def test_regenerar_da_o_ciclo_novo(self):
        novo = services.create_routine(self.user)
        self.assertEqual(novo.inicio_do_ciclo, SEGUNDA)
        self.assertFalse(services.rotina_desatualizada(novo, self.user))


class OVolumeMedioEmTresSemanasTests(TestCase):
    """A média semanal por grupo ao longo do ciclo inteiro (3 semanas em 5
    dias com ABC), no PIOR CASO por dia — a opção mais pesada no grupo."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    @staticmethod
    def media_por_grupo(plan, inicio, semanas=3):
        linhas = list(plan.sessions.prefetch_related("exercises__exercise"))
        total = defaultdict(int)
        for k in range(7 * semanas):
            sessao = services.sessao_do_dia(plan, inicio + timedelta(days=k), linhas)
            if sessao is None:
                continue
            por_grupo_por_opcao = defaultdict(lambda: defaultdict(int))
            for opcao in sessao.opcoes:
                for item in sessao.da_opcao(opcao):
                    por_grupo_por_opcao[item.exercise.muscle_group][opcao] += item.sets
            for grupo, opcoes in por_grupo_por_opcao.items():
                total[grupo] += max(opcoes.values())
        return {grupo: Decimal(v) / semanas for grupo, v in total.items()}

    def test_a_media_do_ciclo_fica_na_faixa_e_o_peito_fica_na_tolerancia(self):
        """Pernas e ombro entram nos 10–20 (eram 6–9 com o ciclo fixo); tudo
        cabe no topo de 2× do TREINO.md, e peito e costas — a sessão de 4
        exercícios do teste dourado a 5/3 por semana — ficam no ALVO ± a
        TOLERÂNCIA que o documento escreve (24 ± 2: 26 é o teto da média).
        Decisão do dono de 17/09/2026: peito 25,0 aceito, golden intocado;
        ficha real de academia faz 26–28, e uma série na média de 3 semanas
        é ruído. Os dois números saem do TREINO.md — a prosa e o teste não
        podem divergir."""
        relogio = _congelar(SEGUNDA)
        self.addCleanup(relogio.stop)
        user = _pessoa("media@exemplo.com")
        plan = services.create_routine(user)
        media = self.media_por_grupo(plan, SEGUNDA)
        piso_1x = doutrina.faixa_semanal_direta("intermediario", 1)[0]
        piso_2x, topo_2x = doutrina.faixa_semanal_direta("intermediario", 2)
        alvo, tolerancia = doutrina.tolerancia_da_media()
        # O alvo da média É o topo da faixa de 2×: um número, dois lugares.
        self.assertEqual(alvo, topo_2x)
        for grupo in ("quads", "hamstrings", "shoulders", "biceps", "triceps"):
            with self.subTest(grupo=grupo, media=media[grupo]):
                self.assertGreaterEqual(media[grupo], piso_1x)
                self.assertLessEqual(media[grupo], topo_2x)
        for grupo in ("chest", "back"):
            with self.subTest(grupo=grupo, media=media[grupo]):
                self.assertGreaterEqual(media[grupo], piso_2x)
                self.assertLessEqual(media[grupo], alvo + tolerancia)

    def test_a_tabela_medida_do_documento_nao_envelhece(self):
        """A linha "intermediário 5d abc2, Padrão" do TREINO.md é a medição de
        verdade, com uma casa decimal — se o motor mudar, a linha fica
        vermelha antes de a prosa mentir."""
        import re
        from pathlib import Path

        relogio = _congelar(SEGUNDA)
        self.addCleanup(relogio.stop)
        user = _pessoa("doc-media@exemplo.com")
        plan = services.create_routine(user)
        media = self.media_por_grupo(plan, SEGUNDA)
        texto = (Path(__file__).resolve().parent.parent / "docs" / "briefs" / "treino" / "TREINO.md").read_text(encoding="utf-8")
        linha = re.search(r"\| intermediário 5d abc2, Padrão \|(.*)\|", texto).group(1)
        valores = [Decimal(c.strip().strip("*").replace(",", ".")) for c in linha.split("|")]
        colunas = ("chest", "back", "triceps", "biceps", "shoulders", "quads", "hamstrings", "calves", "traps", "forearms", "core")
        for grupo, escrito in zip(colunas, valores):
            with self.subTest(grupo=grupo):
                self.assertAlmostEqual(media[grupo], escrito, delta=Decimal("0.06"))
