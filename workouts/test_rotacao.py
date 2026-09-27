# -*- coding: utf-8 -*-
"""SEQUÊNCIA POR PRESENÇA (decisão do dono, 24/09/2026): "qual treino é hoje"
sai da sequência REALIZADA, não da posição no calendário.

O que a doutrina de 17/09 (substituída) fazia: a letra de um dia saía da
POSIÇÃO dele no ciclo, contada pelo calendário — treino pulado contava, como o
quadro da academia. O dono usou o app e viu o defeito: pulou a quarta, e na
quinta o app abriu com a letra da POSIÇÃO (a seguinte à de quarta), fazendo o
treino de quarta sumir. Ninguém na academia faz assim — quem pulou faz o
treino de quarta no dia seguinte.

Hoje o ciclo dá a DIREÇÃO (A → B → C → A…), mas QUAL letra é hoje é a seguinte
à ÚLTIMA FEITA (série registrada). Faltar um dia não avança nada. Quando a
pessoa segue a recomendação em ordem, isso COINCIDE com o antigo calendário —
então o volume médio por grupo, o teto por letra e o dourado ficam intactos.

O que fica preso aqui:

- a letra recomendada de um dia é a seguinte à última FEITA (`sequencia`);
- pular não avança; sem histórico, o recomendado é a primeira letra;
- `inicio_do_ciclo` fica no banco como histórico, mas não decide mais a letra;
- painel, ficha e execução mostram e executam a letra recomendada/escolhida;
- plano de antes da rotação (`inicio_do_ciclo` em branco) ENTRA na regra nova
  sem ser remontado; só o customizado à mão fica preso ao dia da semana;
- o volume médio do ciclo, medido sobre a sequência IDEAL (a pessoa fazendo o
  recomendado em ordem), é o mesmo de antes.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import DuracaoTreino, TrainingDay
from config import relogio
from plans.tests import create_complete_user
from workouts import doutrina, services
from workouts.models import EscolhaDeTreino, ExerciseLog, TrainingPlan
from workouts.test_sequencia import fazer

#: Uma segunda-feira: o plano nasce nela.
SEGUNDA = date(2026, 9, 14)


def _congelar(dia):
    return relogio.Relogio(dia).ligar()


def _janela(dia):
    """Um trecho noutro dia, como gerenciador de contexto."""
    return relogio.congelado_em(dia)


def _pessoa(email, dias=5, preferencia="two", nivel="intermediario", duracao=DuracaoTreino.PADRAO):
    user = create_complete_user(
        email=email, experiencia=nivel, split_preference=preferencia,
        split_preference_confirmada=True, duracao_treino=duracao,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


class ASequenciaPorPresencaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("ciclo@exemplo.com")
        self.plan = services.create_routine(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def _dias(self):
        return services.dias_de_treino_de(self.linhas)

    def test_o_ciclo_da_a_direcao_das_letras(self):
        self.assertEqual(services.letras_do_ciclo(self.linhas), ["A", "B", "C"])
        self.assertEqual(self.plan.split, "abc2")

    def test_o_inicio_do_ciclo_fica_no_banco_mas_nao_decide_a_letra(self):
        self.assertEqual(self.plan.inicio_do_ciclo, SEGUNDA)

    def test_sem_historico_o_recomendado_e_sempre_a_primeira_letra(self):
        """Nada feito: o calendário NÃO avança o ciclo. A segunda da semana 2,
        que a doutrina antiga dava como C, hoje ainda recomenda A."""
        for k in range(0, 21):
            dia = SEGUNDA + timedelta(days=k)
            if dia.weekday() in self._dias():
                self.assertEqual(services.letra_do_dia(self.plan, dia, self.linhas, user=self.user), "A", dia)

    def test_seguindo_a_recomendacao_o_ciclo_gira_e_equilibra(self):
        """Fazendo o recomendado a cada dia de treino, as letras giram
        A B C A B C… — e em 3 semanas (15 treinos) cada letra cai 5 vezes."""
        feitas = []
        dia = SEGUNDA
        while len(feitas) < 15:
            if dia.weekday() in self._dias():
                letra = services.letra_do_dia(self.plan, dia, self.linhas, user=self.user)
                fazer(self.user, self.plan, letra, dia)
                feitas.append(letra)
            dia += timedelta(days=1)
        self.assertEqual(feitas[:6], ["A", "B", "C", "A", "B", "C"])
        self.assertEqual(Counter(feitas), {"A": 5, "B": 5, "C": 5})

    def test_pular_um_dia_nao_avanca_a_letra(self):
        """A na segunda (feito), terça PULADA (nada): quarta continua
        recomendando B — o treino de terça, não o do calendário."""
        fazer(self.user, self.plan, "A", SEGUNDA)
        self.assertEqual(services.letra_do_dia(self.plan, SEGUNDA + timedelta(days=2), self.linhas, user=self.user), "B")

    def test_a_ultima_feita_manda_mesmo_fora_de_ordem(self):
        fazer(self.user, self.plan, "A", SEGUNDA)
        fazer(self.user, self.plan, "C", SEGUNDA + timedelta(days=1))  # pulou B, fez C
        self.assertEqual(services.letra_do_dia(self.plan, SEGUNDA + timedelta(days=2), self.linhas, user=self.user), "A")

    def test_dia_sem_treino_nao_tem_letra(self):
        sabado = SEGUNDA + timedelta(days=5)
        self.assertIsNone(services.letra_do_dia(self.plan, sabado, self.linhas, user=self.user))
        self.assertIsNone(services.sessao_do_dia(self.plan, sabado, self.linhas, user=self.user))

    def test_a_sessao_do_dia_veste_o_horario_do_dia_e_e_a_linha_da_letra(self):
        TrainingDay.objects.filter(user=self.user, weekday=0).update(duration_min=45)
        plan = services.create_routine(self.user)
        linhas = list(plan.sessions.prefetch_related("exercises__exercise"))
        fazer(self.user, plan, "A", SEGUNDA - timedelta(days=3))  # recomendado hoje = B
        sessao = services.sessao_do_dia(plan, SEGUNDA, linhas, user=self.user)
        self.assertEqual(sessao.label, "B")
        self.assertEqual(sessao.weekday, 0)
        self.assertEqual(sessao.duration_min, 45, "a duração é a de segunda")
        linha_b = plan.sessions.filter(label="B").order_by("order").first()
        self.assertEqual(sessao.pk, linha_b.pk, "a ficha é a da letra")
        self.assertEqual(sessao.data, SEGUNDA)

    def test_as_linhas_continuam_sendo_o_retrato_dos_dias(self):
        linhas = list(self.plan.sessions.order_by("order"))
        self.assertEqual([s.weekday for s in linhas], [0, 1, 2, 3, 4])
        self.assertEqual([s.label for s in linhas], ["A", "B", "C", "A", "B"])
        self.assertFalse(services.rotina_invalida(self.plan, self.user))
        self.assertFalse(services.rotina_desatualizada(self.plan, self.user))

    def test_o_teto_semanal_e_o_da_pior_semana_para_toda_letra(self):
        ocorrencias = services.ocorrencias_das_letras(list(self.plan.sessions.all()))
        self.assertEqual(ocorrencias, {"A": 2, "B": 2, "C": 2})
        tetos = services.tetos_da_semana(self.plan)
        self.assertEqual(tetos["quads"], doutrina.teto_semanal("intermediario", 2))
        self.assertEqual(tetos["chest"], doutrina.teto_semanal("intermediario", 2))


class OPainelMostraORecomendadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = _pessoa("painel-ciclo@exemplo.com")
        from plans import services as plan_services

        with _janela(SEGUNDA):
            plan_services.create_plan(self.user)
            self.plan = services.create_routine(self.user)
        self.client.force_login(self.user)

    def test_sem_historico_o_painel_abre_em_a(self):
        with _janela(SEGUNDA):
            resposta = self.client.get(reverse("workouts:routine"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["hoje"].label, "A")

    def test_pulou_a_quarta_e_o_painel_recomenda_c_na_quinta(self):
        with _janela(SEGUNDA + timedelta(days=3)):  # quinta
            fazer(self.user, self.plan, "A", SEGUNDA)
            fazer(self.user, self.plan, "B", SEGUNDA + timedelta(days=1))
            resposta = self.client.get(reverse("workouts:routine"))
            self.assertEqual(resposta.context["hoje"].label, "C")
            # a quarta pulada aparece marcada na projeção da semana (a tira,
            # via `week`); `sessions` é a ESTRUTURA e não carrega projeção.
            projs = {
                d["session"].weekday: d["session"].projecao
                for d in resposta.context["week"] if d["session"]
            }
            self.assertEqual(projs[SEGUNDA.weekday()], "feito")           # segunda A
            self.assertEqual(projs[(SEGUNDA + timedelta(days=2)).weekday()], "pulado")  # quarta
            self.assertEqual(projs[(SEGUNDA + timedelta(days=3)).weekday()], "hoje")    # quinta C

    def test_a_serie_gravada_hoje_conta_na_letra_recomendada(self):
        with _janela(SEGUNDA):
            estado = services.estado_do_treino(self.user)
            self.assertEqual(estado.sessao.label, "A")
            item = estado.itens[0]
            ExerciseLog.objects.create(
                user=self.user, exercise=item.exercise, date=SEGUNDA,
                set_number=1, weight_kg=Decimal("40"), reps=10,
            )
            services.registrar_escolha(self.user, estado.sessao, estado.opcao, dia=SEGUNDA)
            resposta = self.client.get(reverse("workouts:routine"))
            hoje = resposta.context["hoje"]
            self.assertEqual(hoje.label, "A")
            self.assertGreaterEqual(hoje.feitos_hoje, 1)

    def test_o_proximo_treino_num_dia_de_descanso_e_o_recomendado(self):
        with _janela(SEGUNDA + timedelta(days=5)):  # sábado: descanso
            fazer(self.user, self.plan, "A", SEGUNDA)  # última feita A -> recomendado B
            resposta = self.client.get(reverse("workouts:routine"))
            self.assertIsNone(resposta.context["hoje"])
            self.assertEqual(resposta.context["proximo"]["session"].label, "B")


class OPlanoAntigoEntraNaRegraNovaTests(TestCase):
    """Plano de antes da rotação (`inicio_do_ciclo` em branco) NÃO é remontado,
    e passa a valer pela presença — como qualquer outro (24/09/2026)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("antigo-ciclo@exemplo.com")
        self.plan = services.create_routine(self.user)
        TrainingPlan.objects.filter(pk=self.plan.pk).update(inicio_do_ciclo=None)
        self.plan.refresh_from_db()
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def test_entra_na_presenca_sem_ser_remontado(self):
        self.assertTrue(services.usa_presenca(self.plan))
        # sem histórico -> recomendado A
        self.assertEqual(services.letra_do_dia(self.plan, SEGUNDA, self.linhas, user=self.user), "A")
        # fez A ontem -> recomendado hoje B
        fazer(self.user, self.plan, "A", SEGUNDA - timedelta(days=1))
        self.assertEqual(services.letra_do_dia(self.plan, SEGUNDA, self.linhas, user=self.user), "B")

    def test_nao_e_remontado_e_a_home_pergunta(self):
        self.assertFalse(services.rotina_invalida(self.plan, self.user))
        self.assertTrue(services.rotina_desatualizada(self.plan, self.user))
        depois, mudou = services.sync_active_routine(self.user)
        self.assertFalse(mudou)
        self.assertEqual(depois.pk, self.plan.pk)


class OPlanoCustomizadoFicaPresoAoDiaTests(TestCase):
    """Ficha ajustada à mão: a pessoa arranjou os dias, e a presença não
    remexe nisso — a letra é a da linha do dia da semana."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("custom@exemplo.com")
        self.plan = services.create_routine(self.user)
        TrainingPlan.objects.filter(pk=self.plan.pk).update(customized_at=relogio.Relogio(SEGUNDA).agora())
        self.plan.refresh_from_db()
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def test_a_letra_e_a_do_dia_da_semana_em_toda_semana(self):
        self.assertFalse(services.usa_presenca(self.plan))
        for semana in range(3):
            self.assertEqual(
                [services.letra_do_dia(self.plan, SEGUNDA + timedelta(days=7 * semana + d), self.linhas, user=self.user) for d in range(5)],
                ["A", "B", "C", "A", "B"],
            )


class OVolumeMedioEmTresSemanasTests(TestCase):
    """A média semanal por grupo ao longo do ciclo IDEAL (a pessoa fazendo o
    recomendado em ordem — A B C A B C… — 3 semanas em 5 dias), no PIOR CASO
    por dia. É a mesma distribuição do antigo calendário: cada letra 5 vezes."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    @staticmethod
    def media_por_grupo(plan, inicio, semanas=3):
        linhas = list(plan.sessions.prefetch_related("exercises__exercise"))
        letras = services.letras_do_ciclo(linhas)
        dias = services.dias_de_treino_de(linhas)
        total = defaultdict(int)
        k = 0
        for d in range(7 * semanas):
            dia = inicio + timedelta(days=d)
            if dia.weekday() not in dias:
                continue
            letra = letras[k % len(letras)]
            k += 1
            sessao = next(s for s in linhas if s.label == letra)
            por_grupo_por_opcao = defaultdict(lambda: defaultdict(int))
            for opcao in sessao.opcoes:
                for item in sessao.da_opcao(opcao):
                    por_grupo_por_opcao[item.exercise.muscle_group][opcao] += item.sets
            for grupo, opcoes in por_grupo_por_opcao.items():
                total[grupo] += max(opcoes.values())
        return {grupo: Decimal(v) / semanas for grupo, v in total.items()}

    def test_a_media_do_ciclo_fica_na_faixa_e_o_peito_fica_na_tolerancia(self):
        with _janela(SEGUNDA):
            user = _pessoa("media@exemplo.com")
            plan = services.create_routine(user)
            media = self.media_por_grupo(plan, SEGUNDA)
        piso_1x = doutrina.faixa_semanal_direta("intermediario", 1)[0]
        piso_2x, topo_2x = doutrina.faixa_semanal_direta("intermediario", 2)
        alvo, tolerancia = doutrina.tolerancia_da_media()
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
        import re
        from pathlib import Path

        with _janela(SEGUNDA):
            user = _pessoa("doc-media@exemplo.com")
            plan = services.create_routine(user)
            media = self.media_por_grupo(plan, SEGUNDA)
        texto = (Path(__file__).resolve().parent.parent / "docs" / "briefs" / "treino" / "TREINO.md").read_text(encoding="utf-8")
        linha = re.search(r"\| intermediário 5d abc2, Padrão \|(.*)\|", texto).group(1)
        valores = [Decimal(c.strip().strip("*").replace(",", ".")) for c in linha.split("|")]
        colunas = ("chest", "back", "triceps", "biceps", "shoulders", "quads", "hamstrings", "glutes", "calves", "traps", "forearms", "core")
        for grupo, escrito in zip(colunas, valores):
            with self.subTest(grupo=grupo):
                self.assertAlmostEqual(media[grupo], escrito, delta=Decimal("0.06"))
