# -*- coding: utf-8 -*-
"""O orçamento de consultas da Home, no pior estado, com o nome de cada uma.

A Home é a tela mais aberta do app e fazia 44 consultas (medido em
21/09/2026, quarta com série registrada — `plans/test_stress`): uma por
subsistema, cada um relendo o que o vizinho já tinha carregado — o perfil
quatro vezes, o plano de treino duas, as sessões duas, o cardápio duas, os
registros de refeição quatro. Com o web em Oregon e o banco no mesmo data
center isso custa ~1 ms por consulta; com o banco em outro continente
custaria a viagem toda, 41 vezes — foi a conta que decidiu não migrar o
banco (`docs/infra-recuperacao.md`).

A régua aqui é UMA LEITURA POR TABELA: o que a tela precisa de cada tabela é
lido uma vez e passado adiante, em vez de cada função abrir a sua consulta
(`services.plano_do_dia`, `tracking.day_summary(logs=, slots=, corridas_m=)`,
`streaks.calcular(ja_lido=)`, `workouts.services.rotina_ativa_com_linhas`,
`views.agua_e_desfazer`, `weight_trend.convidar_a_pesar(pesagens=)`).

O dono pediu MENOS DE 15 (21/09/2026). O piso medido com esta arquitetura é
17, e as 17 estão nomeadas: sessão e usuário (2, do login), perfil, dias de
treino, pesagens, plano+horários (1), opções+modelos (1), itens+alimentos
(1), porções, registros de refeição de hoje, água+goles (1), corridas, a
rotina inteira (plano+sessões+itens+trocas, 1), a escolha do dia, as
séries de hoje, as datas com série (ofensiva) e os registros de refeição
de 400 dias (ofensiva). Descer daí é decisão de produto — guardar a
ofensiva calculada em vez de reler 400 dias, ou tirar dado da tela —, e
está no relatório. `TETO` é o piso; subir é laço com consulta dentro.

Não é `@tag("lento")` de propósito: um laço com consulta dentro é o defeito
que este teste existe para pegar ANTES do merge.
"""
import re
import traceback

from django.db import connection
from django.test import TestCase
from django.urls import reverse

from plans.test_stress import PopulatedAccountMixin

#: O piso medido em 21/09/2026 (o dono pediu < 15; ver a docstring).
TETO = 17

RAIZ = "nutriplan"


def _origem():
    quadros = [
        q for q in traceback.extract_stack()
        if "/django/" not in q.filename.replace("\\", "/")
        and ".venv" not in q.filename
        and "test_orcamento_da_home" not in q.filename
        and RAIZ in q.filename.replace("\\", "/")
    ]
    return " < ".join("%s:%s" % (q.filename.replace("\\", "/").split("/")[-1], q.lineno) for q in quadros[-3:])


def _tabelas(sql):
    achadas = re.findall(r'(?:FROM|JOIN) "([a-z_]+)"', sql)
    return ",".join(sorted(set(achadas))) or sql[:40]


class AHomeLeCadaTabelaUmaVezTests(PopulatedAccountMixin, TestCase):
    def test_a_home_cabe_no_orcamento(self):
        url = reverse("plans:today")
        self.client.get(url)  # aquece o que é cacheado por processo (o catálogo do datalist)
        consultas = []

        def espia(execute, sql, params, many, context):
            consultas.append((_tabelas(sql), _origem()))
            return execute(sql, params, many, context)

        with connection.execute_wrapper(espia):
            resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        lista = "\n".join("%2d. %-45s %s" % (i, t, o) for i, (t, o) in enumerate(consultas, 1))
        self.assertLessEqual(
            len(consultas), TETO,
            "a Home fez %d consultas (teto %d):\n%s" % (len(consultas), TETO, lista),
        )


class AsDuasFormasDaoOMesmoNumeroTests(PopulatedAccountMixin, TestCase):
    """Cada leitura compartilhada tem a forma antiga (uma consulta por
    consumidor) e a nova (uma leitura passada adiante). As duas têm de dar o
    MESMO resultado sobre o mesmo banco — senão a Home ficou mais barata
    dizendo outra coisa."""

    def test_o_denominador_da_ofensiva_e_o_mesmo_por_subconsulta(self):
        from plans import tracking
        from plans.models import MealLog

        registros = list(
            MealLog.objects.filter(user=self.user)
            .values("slot__plan_id")
            .annotate(previstas=tracking.previstas_do_plano())
        )
        planos = {r["slot__plan_id"] for r in registros if r["slot__plan_id"]}
        por_plano = tracking.previstas_por_plano(planos)
        self.assertTrue(registros)
        for r in registros:
            self.assertEqual(r["previstas"], por_plano[r["slot__plan_id"]])

    def test_o_plano_e_o_cardapio_numa_consulta_sao_os_de_sempre(self):
        from plans import services

        plan, slots = services.plano_ativo_com_cardapio(self.user)
        self.assertEqual(plan, services.get_active_plan(self.user))
        self.assertEqual([s.pk for s in slots], [s.pk for s in services.slots_com_cardapio(plan)])
        with self.assertNumQueries(0):
            for slot in slots:
                self.assertIs(slot.plan, plan)
                for option in slot.options.all():
                    option.template.name
                    for item in option.template.items.all():
                        item.food.name
                        list(item.food.portions.all())

    def test_um_plano_ativo_sem_horarios_ainda_e_encontrado(self):
        """O JOIN pelos horários não vê plano sem horário; o caminho lento vê,
        e `plan_is_current` o recusa como sempre (retrato sem cardápio)."""
        from plans import services

        self.plan.slots.all().delete()
        plan, slots = services.plano_ativo_com_cardapio(self.user)
        self.assertEqual(plan, self.plan)
        self.assertEqual(slots, [])
        self.assertFalse(services.plan_is_current(plan, services.build_inputs(self.user), slots=slots))

    def test_a_conferencia_do_plano_em_memoria_e_a_do_banco_concordam(self):
        from plans import services

        # A fixture troca o peso depois de criar o plano; `plano_do_dia` o
        # refaz, e é sobre o plano ATUAL que as duas formas são comparadas.
        services.plano_do_dia(self.user)
        inputs = services.build_inputs(self.user)
        plan, slots = services.plano_ativo_com_cardapio(self.user)
        self.assertTrue(services.plan_is_current(plan, inputs))
        self.assertTrue(services.plan_is_current(plan, inputs, slots=slots))
        # receita aposentada: as duas formas recusam
        modelo = slots[0].options.all()[0].template
        modelo.is_active = False
        modelo.save(update_fields=["is_active"])
        plan, slots = services.plano_ativo_com_cardapio(self.user)
        self.assertFalse(services.plan_is_current(plan, inputs))
        self.assertFalse(services.plan_is_current(plan, inputs, slots=slots))

    def test_o_resumo_do_dia_em_memoria_e_o_do_banco_concordam(self):
        from django.utils import timezone

        from plans import services, tracking
        from workouts.models import Corrida

        hoje = timezone.localdate()
        Corrida.objects.create(
            user=self.user, op_id="orc-1", comecou_em=timezone.now() - timezone.timedelta(minutes=30),
            terminou_em=timezone.now(), distancia_m=5_000, duracao_s=1_800,
        )
        plan, slots = services.plano_ativo_com_cardapio(self.user)
        logs = tracking.logs_by_slot(self.user, hoje)
        do_banco = tracking.day_summary(self.user, plan, hoje, peso_kg=plan.weight_kg)
        em_memoria = tracking.day_summary(
            self.user, plan, hoje, peso_kg=plan.weight_kg, logs=logs, slots=slots,
            corridas_m=[5_000],
        )
        self.assertEqual(em_memoria, do_banco)
        self.assertGreater(em_memoria["gasto_corrida_kcal"], 0)

    def test_a_rotina_numa_consulta_e_a_de_sempre_com_as_trocas(self):
        from workouts import services
        from workouts.models import Exercise, SessionExercise, TrocaDeExercicio

        plan = services.get_active_routine(self.user)
        antigas = services.linhas_do_plano(plan)
        item = SessionExercise.objects.filter(session__plan=plan).first()
        substituto = Exercise.objects.filter(is_active=True).exclude(pk=item.exercise_id).first()
        TrocaDeExercicio.objects.create(user=self.user, original=item.exercise, substituto=substituto)

        with self.assertNumQueries(2):  # as linhas + os substitutos
            plano, linhas, trocas = services.rotina_ativa_com_linhas(self.user)
        self.assertEqual(plano, plan)
        self.assertEqual([l.pk for l in linhas], [l.pk for l in antigas])
        self.assertEqual(trocas, services.trocas_de(self.user))
        with self.assertNumQueries(0):
            for nova, antiga in zip(linhas, antigas):
                self.assertEqual(
                    [(i.pk, i.exercise_id, i.opcao) for i in nova.exercises.all()],
                    [(i.pk, i.exercise_id, i.opcao) for i in antiga.exercises.all()],
                )
                self.assertEqual(nova.opcoes, antiga.opcoes)

    def test_sem_troca_a_rotina_custa_uma_consulta(self):
        from workouts import services

        with self.assertNumQueries(1):
            plano, linhas, trocas = services.rotina_ativa_com_linhas(self.user)
        self.assertEqual(trocas, {})
        self.assertTrue(linhas)

    def test_a_agua_e_o_desfazer_numa_consulta_concordam_com_as_duas(self):
        from django.utils import timezone

        from plans import streaks
        from plans.models import GoleDeAgua, HydrationLog
        from plans.views import agua_e_desfazer

        hoje = timezone.localdate()
        inicio = streaks.inicio_do_historico(hoje)
        por_dia, desfazer = agua_e_desfazer(self.user, inicio, hoje)
        self.assertEqual(por_dia, streaks.agua_por_dia_desde(self.user, inicio))
        registro = HydrationLog.objects.filter(user=self.user, date=hoje).first()
        self.assertEqual(por_dia.get(hoje, 0), registro.ml if registro else 0)
        self.assertEqual(desfazer, GoleDeAgua.objects.filter(user=self.user, dia=hoje).exists())
        GoleDeAgua.objects.create(user=self.user, dia=hoje, ml=250)
        self.assertTrue(agua_e_desfazer(self.user, inicio, hoje)[1])

    def test_o_convite_de_pesar_em_memoria_e_o_do_banco_concordam(self):
        from django.utils import timezone

        from plans import weight_trend

        hoje = timezone.localdate()
        pesagens = list(self.user.weight_entries.order_by("-date", "-pk")[:7])
        self.assertEqual(
            weight_trend.convidar_a_pesar(self.user, hoje=hoje, pesagens=pesagens),
            weight_trend.convidar_a_pesar(self.user, hoje=hoje),
        )
        self.user.weight_entries.filter(date=hoje).delete()
        pesagens = list(self.user.weight_entries.order_by("-date", "-pk")[:7])
        self.assertEqual(
            weight_trend.convidar_a_pesar(self.user, hoje=hoje, pesagens=pesagens),
            weight_trend.convidar_a_pesar(self.user, hoje=hoje),
        )

    def test_a_ofensiva_com_o_que_a_home_leu_e_a_mesma(self):
        from django.utils import timezone

        from plans import streaks
        from workouts import services
        from workouts.models import Corrida

        hoje = timezone.localdate()
        inicio = streaks.inicio_do_historico(hoje)
        _, linhas, _ = services.rotina_ativa_com_linhas(self.user)
        ja_lido = streaks.JaLido(
            previstos={l.weekday for l in linhas},
            corridas=list(
                Corrida.objects.filter(user=self.user, comecou_em__date__gte=inicio)
                .values_list("comecou_em", flat=True)
            ),
            agua_por_dia=streaks.agua_por_dia_desde(self.user, inicio),
            tem_plano=True,
        )
        self.assertEqual(
            streaks.calcular(self.user, hoje=hoje, meta_agua_ml=3150, ja_lido=ja_lido),
            streaks.calcular(self.user, hoje=hoje, meta_agua_ml=3150),
        )
