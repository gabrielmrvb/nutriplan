# -*- coding: utf-8 -*-
"""RETOMAR e ESTAGNADO falam; nunca baixam número (T2.3, 17/09/2026).

Duas regras novas no módulo puro `workouts/adaptacao.py`, e quatro
NEGATIVOS que congelam o veto do brief de 13/09 ("a adaptação é leitura"):

- RETOMAR: 21 dias ou mais sem NENHUMA série do exercício ⇒ mesma carga (a
  maior da referência), SUBIR suspenso mesmo com a faixa fechada, reps no
  piso, frase "N dias sem este exercício: confirme a carga hoje"; a partir
  de 28 a frase acrescenta "comece mais leve se precisar". O app NÃO propõe
  número menor — `valor` é sempre a carga de referência (sabotagem
  `× 0,9` fica vermelha). 21 e não 15: Hwang 2017 dá duas semanas sem
  perda, Bosquet 2013 diz "significativo a partir da terceira semana";
- ESTAGNADO: três sessões completas seguidas (≤ 27 dias entre elas) na
  mesma carga máxima, nenhuma fechou, total de reps da última ≤ total da
  primeira + 1 (Mitter 2022: uma rep é ruído) ⇒ "manter e dizer" — o campo
  abre com a mesma carga, o verbo na tela é "manter", a frase diz "três
  treinos em 60 kg sem ganhar repetição". `estagnado_persistente` é a trava
  contra RESET em cadeia, escrita antes de existir RESET.

Os negativos: (a) a ficha da semana 8 é igual à da semana 1 com sete
semanas de registro no meio; (b) a prescrição de hoje é idêntica com e sem
a série de ontem; (c) treinar em dia não declarado não altera dias, teto
nem divisão; (d) a adaptação não escreve em `SessionExercise` — controle
textual no módulo e retrato das linhas antes e depois da tela.
"""
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TrainingDay
from workouts import adaptacao, services
from workouts.models import ExerciseLog, Measure, MuscleGroup, SessionExercise
from workouts.test_dupla_progressao import _anterior, _Item, _Log
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts

HOJE = date(2026, 9, 16)
FONTE = Path(__file__).resolve().parent / "adaptacao.py"


def _dia(dias_atras):
    return HOJE - timedelta(days=dias_atras)


def _sessoes(*datas_e_series):
    """[(dias atrás, [(peso, reps), ...]), ...] → o `sessoes` de `load_history`,
    da mais recente para trás."""
    lista = [(_dia(atras), _anterior(*series)) for atras, series in datas_e_series]
    return sorted(lista, key=lambda par: par[0], reverse=True)


def _ajuste(sessoes, **item):
    ultimo = sessoes[0][1][max(sessoes[0][1])] if sessoes else None
    return adaptacao.ajuste(_Item(**item), sessoes, ultimo, HOJE)


FECHOU = [(60, 10), (60, 10), (60, 10)]
NAO_FECHOU = [(60, 10), (60, 9), (60, 10)]


class ARetomadaTests(SimpleTestCase):
    def test_a_matriz_de_intervalos_faixa_grupo_e_completude(self):
        """gap × fechou × tronco/perna × completa/parcial. Antes de 21 dias a
        regra de sempre decide (SUBIR com o degrau do grupo, ou MANTER); de
        21 a 27, RETOMAR na mesma carga; de 28 em diante, RETOMAR com
        "comece mais leve". Na coluna "parcial" a sessão mais recente tem
        duas de três séries e a referência é a completa de 7 dias antes —
        o intervalo conta da parcial, a carga vem da completa."""
        for gap in (0, 14, 20, 21, 27, 28, 90):
            for fechou in (True, False):
                for grupo, degrau in ((MuscleGroup.CHEST, Decimal("2.5")), (MuscleGroup.QUADS, Decimal("5"))):
                    for parcial in (False, True):
                        with self.subTest(gap=gap, fechou=fechou, grupo=grupo, parcial=parcial):
                            series = FECHOU if fechou else NAO_FECHOU
                            if parcial:
                                sessoes = _sessoes((gap, [(60, 10), (60, 10)]), (gap + 7, series))
                            else:
                                sessoes = _sessoes((gap, series))
                            p = _ajuste(sessoes, grupo=grupo)
                            if gap >= adaptacao.DIAS_PARA_RETOMAR:
                                self.assertIs(p.estado, adaptacao.Estado.RETOMAR)
                                self.assertEqual(p.valor, Decimal("60"), "nunca número menor, nunca maior")
                                self.assertIn("%d dias sem este exercício" % gap, p.razao)
                                self.assertEqual("mais leve" in p.razao, gap >= adaptacao.DIAS_PARA_RETOMAR_MAIS_LEVE)
                            elif fechou:
                                self.assertIs(p.estado, adaptacao.Estado.SUBIR)
                                self.assertEqual(p.valor, Decimal("60") + degrau)
                            else:
                                self.assertIs(p.estado, adaptacao.Estado.MANTER)
                                self.assertEqual(p.valor, Decimal("60"))

    def test_vinte_dias_com_a_faixa_fechada_sobe_vinte_e_um_retoma(self):
        """A fronteira, dos dois lados: 20 não freia; 21 freia e devolve 60,
        não 62,5 (sabotagem 21 → 15 e 21 → 0 derrubam)."""
        self.assertEqual(adaptacao.DIAS_PARA_RETOMAR, 21)
        self.assertEqual(adaptacao.DIAS_PARA_RETOMAR_MAIS_LEVE, 28)
        sobe = _ajuste(_sessoes((20, FECHOU)))
        self.assertIs(sobe.estado, adaptacao.Estado.SUBIR)
        self.assertEqual(sobe.valor, Decimal("62.5"))
        retoma = _ajuste(_sessoes((21, FECHOU)))
        self.assertIs(retoma.estado, adaptacao.Estado.RETOMAR)
        self.assertEqual(retoma.valor, Decimal("60"))
        self.assertEqual(retoma.razao, "21 dias sem este exercício: confirme a carga hoje")
        leve = _ajuste(_sessoes((28, FECHOU)))
        self.assertEqual(leve.razao, "28 dias sem este exercício: confirme a carga — comece mais leve se precisar")

    def test_parcial_ha_cinco_dias_com_a_completa_ha_vinte_nao_e_retomada(self):
        """O intervalo conta da ÚLTIMA série, de qualquer sessão: quem fez
        duas séries há 5 dias não parou. A carga sai da completa de 20."""
        p = _ajuste(_sessoes((5, [(60, 10), (60, 10)]), (20, FECHOU)))
        self.assertIs(p.estado, adaptacao.Estado.SUBIR)
        self.assertEqual(p.valor, Decimal("62.5"))

    def test_sem_sessao_completa_nas_quatro_datas_mais_recentes_nao_ha_o_que_dizer(self):
        """Quatro parciais escondem a completa de trás: a referência tem de
        estar entre as quatro datas mais recentes."""
        parcial = [(60, 10), (60, 10)]
        self.assertIsNone(_ajuste(_sessoes((3, parcial), (6, parcial), (9, parcial), (12, parcial), (15, FECHOU))))
        self.assertIsNotNone(_ajuste(_sessoes((3, parcial), (6, parcial), (9, parcial), (12, FECHOU))))

    def test_retomar_leva_as_reps_ao_piso_e_nao_muda_o_numero_do_campo(self):
        self.assertEqual(adaptacao.REPS_NO_PISO, frozenset({adaptacao.Estado.SUBIR, adaptacao.Estado.RETOMAR}))
        self.assertEqual(adaptacao.MUDA_CARGA, frozenset({adaptacao.Estado.SUBIR}))
        self.assertNotIn(adaptacao.Estado.RETOMAR, adaptacao.MUDA_CARGA)
        self.assertNotIn(adaptacao.Estado.ESTAGNADO, adaptacao.MUDA_CARGA)

    def test_o_load_antigo_sem_data_nao_retoma(self):
        """`proxima_carga` com o `load` de 13/09 (só `anterior`, sem data):
        sem intervalo conhecido a regra de sempre decide."""
        item = _Item(load={"anterior": _anterior(*FECHOU), "hoje": {}})
        self.assertIs(services.proxima_carga(item).estado, adaptacao.Estado.SUBIR)


class AEstagnacaoTests(SimpleTestCase):
    PLATO = ((3, [(60, 8), (60, 8), (60, 7)]), (10, [(60, 8), (60, 8), (60, 8)]), (17, [(60, 8), (60, 9), (60, 7)]))

    def test_tres_treinos_na_mesma_carga_sem_ganhar_repeticao_e_estagnado(self):
        """60×{8,8,7} / {8,8,8} / {8,9,7} em 8–12: 23 reps hoje contra 24 há
        duas sessões — nada avançou. Manter e dizer."""
        p = _ajuste(_sessoes(*self.PLATO), rep_min=8, rep_max=12)
        self.assertIs(p.estado, adaptacao.Estado.ESTAGNADO)
        self.assertEqual(p.valor, Decimal("60"))
        self.assertEqual(p.razao, "três treinos em 60 kg sem ganhar repetição")
        self.assertEqual(p.rotulo, "manter")

    def test_duas_iguais_e_uma_melhor_e_manter(self):
        """29 reps contra 24: ganhou cinco. Não é platô — é a dupla
        progressão andando."""
        sessoes = _sessoes((3, [(60, 10), (60, 10), (60, 9)]), (10, [(60, 8), (60, 8), (60, 8)]), (17, [(60, 8), (60, 8), (60, 8)]))
        p = _ajuste(sessoes, rep_min=8, rep_max=12)
        self.assertIs(p.estado, adaptacao.Estado.MANTER)

    def test_uma_repeticao_a_mais_e_ruido_duas_nao_sao(self):
        """Mitter 2022: o erro de medição de reps é de ~1. 25 contra 24 ainda
        é platô; 26 contra 24 é avanço (sabotagem `+1` → `+2` derruba)."""
        self.assertEqual(adaptacao.REPS_DE_RUIDO, 1)
        base = [(60, 8), (60, 8), (60, 8)]
        mais_uma = _sessoes((3, [(60, 9), (60, 8), (60, 8)]), (10, base), (17, base))
        self.assertIs(_ajuste(mais_uma, rep_min=8, rep_max=12).estado, adaptacao.Estado.ESTAGNADO)
        mais_duas = _sessoes((3, [(60, 9), (60, 9), (60, 8)]), (10, base), (17, base))
        self.assertIs(_ajuste(mais_duas, rep_min=8, rep_max=12).estado, adaptacao.Estado.MANTER)

    def test_parcial_no_meio_nao_quebra_a_sequencia(self):
        """A sequência é de sessões COMPLETAS: a parcial entre elas é pulada,
        e as três completas seguem sendo três."""
        sessoes = _sessoes(
            (3, [(60, 8), (60, 8), (60, 7)]), (6, [(60, 8)]),
            (10, [(60, 8), (60, 8), (60, 8)]), (17, [(60, 8), (60, 9), (60, 7)]),
        )
        self.assertIs(_ajuste(sessoes, rep_min=8, rep_max=12).estado, adaptacao.Estado.ESTAGNADO)

    def test_quarenta_dias_entre_a_segunda_e_a_terceira_nao_e_plato(self):
        """Mais de 27 dias entre duas sessões é pausa, não estagnação."""
        self.assertEqual(adaptacao.DIAS_ENTRE_SESSOES_DO_PLATO, 27)
        sessoes = _sessoes((3, [(60, 8), (60, 8), (60, 7)]), (10, [(60, 8), (60, 8), (60, 8)]), (50, [(60, 8), (60, 9), (60, 7)]))
        self.assertIs(_ajuste(sessoes, rep_min=8, rep_max=12).estado, adaptacao.Estado.MANTER)

    def test_reps_nao_anotadas_numa_das_tres_e_manter(self):
        """Sem número não há como medir avanço (sabotagem `reps or 0` derruba)."""
        sessoes = _sessoes((3, [(60, 8), (60, 8), (60, 7)]), (10, [(60, 8), (60, None), (60, 8)]), (17, [(60, 8), (60, 9), (60, 7)]))
        self.assertIs(_ajuste(sessoes, rep_min=8, rep_max=12).estado, adaptacao.Estado.MANTER)

    def test_carga_diferente_numa_das_tres_nao_e_plato(self):
        sessoes = _sessoes((3, [(60, 8), (60, 8), (60, 7)]), (10, [(57.5, 8), (57.5, 8), (57.5, 8)]), (17, [(60, 8), (60, 9), (60, 7)]))
        self.assertIs(_ajuste(sessoes, rep_min=8, rep_max=12).estado, adaptacao.Estado.MANTER)

    def test_fechar_a_faixa_vence_o_plato(self):
        """A referência fechou 3×12: SUBIR, mesmo que as duas anteriores
        estivessem paradas — a precedência é RETOMAR > SUBIR > ESTAGNADO."""
        sessoes = _sessoes((3, [(60, 12), (60, 12), (60, 12)]), (10, [(60, 8), (60, 8), (60, 8)]), (17, [(60, 8), (60, 8), (60, 8)]))
        self.assertIs(_ajuste(sessoes, rep_min=8, rep_max=12).estado, adaptacao.Estado.SUBIR)

    def test_a_retomada_vence_o_plato(self):
        sessoes = _sessoes((25, [(60, 8), (60, 8), (60, 7)]), (32, [(60, 8), (60, 8), (60, 8)]), (39, [(60, 8), (60, 9), (60, 7)]))
        self.assertIs(_ajuste(sessoes, rep_min=8, rep_max=12).estado, adaptacao.Estado.RETOMAR)

    def test_o_plato_depois_de_um_recomeco_e_persistente(self):
        """Antes do platô houve uma sessão a 55 seguida da volta a 60 em 14
        dias — o rastro de um recomeço. O segundo platô na mesma carga é
        PERSISTENTE: só frase, nunca outro RESET (a trava de C2-B). Com a
        sessão leve 70 dias antes da volta, é o platô comum."""
        self.assertEqual(adaptacao.DIAS_DO_RECOMECO, 56)
        recente = _sessoes(*self.PLATO)
        leve_e_volta = _sessoes((24, [(60, 8), (60, 8), (60, 8)]), (38, [(55, 10), (55, 10), (55, 10)]))
        p = _ajuste(recente + leve_e_volta, rep_min=8, rep_max=12)
        self.assertIs(p.estado, adaptacao.Estado.ESTAGNADO_PERSISTENTE)
        self.assertEqual(p.valor, Decimal("60"))
        self.assertEqual(p.rotulo, "manter")
        self.assertIn("três treinos em 60 kg", p.razao)
        self.assertIn("recomeçou", p.razao)
        leve_antiga = _sessoes((24, [(60, 8), (60, 8), (60, 8)]), (94, [(55, 10), (55, 10), (55, 10)]))
        self.assertIs(_ajuste(recente + leve_antiga, rep_min=8, rep_max=12).estado, adaptacao.Estado.ESTAGNADO)

    def test_o_rotulo_e_o_verbo_da_tela(self):
        for estado, verbo in (("subir", "subir"), ("manter", "manter"), ("retomar", "retomar"), ("estagnado", "manter"), ("estagnado_persistente", "manter")):
            self.assertEqual(adaptacao.Progressao(adaptacao.Estado(estado), Decimal("60"), "").rotulo, verbo)

    def test_a_mesma_entrada_da_a_mesma_saida(self):
        sessoes = _sessoes(*self.PLATO)
        self.assertEqual(_ajuste(sessoes, rep_min=8, rep_max=12), _ajuste(sessoes, rep_min=8, rep_max=12))

    def test_o_modulo_nao_escreve_em_lugar_nenhum(self):
        """Controle textual: nenhuma escrita de ORM no módulo — sem
        `objects.`, `.save(`, `.update(`, `.create(`. E o verificador
        enxerga uma linha inserida."""
        proibidos = ("objects.", ".save(", ".update(", ".create(", "bulk_")
        texto = re.sub(r'"""[\s\S]*?"""', "", FONTE.read_text(encoding="utf-8"))
        linhas = [l for l in texto.splitlines() if not l.lstrip().startswith("#") and any(p in l for p in proibidos)]
        self.assertEqual(linhas, [])
        sabotado = texto + "\nSessionExercise.objects.filter(pk=1).update(sets=2)\n"
        self.assertTrue([l for l in sabotado.splitlines() if any(p in l for p in proibidos)])


class ATelaMostraRetomarEEstagnadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="retomar@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS and i.sets >= 3
        )

    def _registra(self, dias_atras, reps_por_serie, peso="60"):
        for n, reps in enumerate(reps_por_serie, start=1):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.item.exercise, date=self.hoje - timedelta(days=dias_atras),
                set_number=n, weight_kg=Decimal(peso), reps=reps,
            )

    def _html(self):
        return sem_scripts(self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        ).content.decode())

    def _sugestao(self, html):
        return html.split('class="agora__anterior-sugestao"', 1)[1].split("</span>", 1)[0]

    def _campo(self, html, nome):
        return re.search(r'name="%s"[^>]*value="([^"]*)"' % nome, html).group(1)

    def test_vinte_e_cinco_dias_parado_a_tela_pede_para_confirmar_a_carga(self):
        """Fechou a faixa há 25 dias: sem a retomada seria "subir 62,5". A
        tela diz "retomar 60 kg", o campo abre com 60 e as reps no piso."""
        self._registra(25, [self.item.rep_max] * self.item.sets)
        html = self._html()
        sugestao = self._sugestao(html)
        self.assertIn("retomar", sugestao)
        self.assertIn("25 dias sem este exercício: confirme a carga hoje", sugestao)
        self.assertNotIn("subir", sugestao)
        self.assertEqual(self._campo(html, "weight_kg"), "60")
        self.assertEqual(self._campo(html, "reps"), str(self.item.rep_min))

    def test_tres_treinos_parados_a_tela_diz_manter_e_conta(self):
        """O verbo é "manter" (o estado interno "estagnado" não aparece), o
        número é 60 e a frase diz que são três treinos sem ganhar rep."""
        abaixo = self.item.rep_max - 1
        self._registra(3, [abaixo] * self.item.sets)
        self._registra(10, [abaixo] * self.item.sets)
        self._registra(17, [abaixo] * self.item.sets)
        html = self._html()
        sugestao = self._sugestao(html)
        self.assertIn("manter", sugestao)
        self.assertIn("três treinos em 60 kg sem ganhar repetição", sugestao)
        self.assertNotIn("estagnado", sugestao)
        self.assertEqual(self._campo(html, "weight_kg"), "60")


class AAdaptacaoNaoMexeNaFichaTests(TestCase):
    """Os quatro negativos que congelam o veto: a adaptação é LEITURA."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="leitura@exemplo.com", weekdays=dias_incluindo_hoje(5))
        self.plano = services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        self.linhas = list(self.plano.sessions.prefetch_related("exercises__exercise"))

    def _retrato(self):
        return sorted(
            (i.session_id, i.opcao, i.exercise_id, i.sets, i.rep_min, i.rep_max, i.rest_seconds, i.order)
            for i in SessionExercise.objects.filter(session__plan=self.plano)
        )

    def _ficha_da_semana(self, primeiro_dia):
        """Por letra, o que cada sessão prescreve na semana que começa em
        `primeiro_dia` — o retrato que não pode mudar."""
        ficha = {}
        for k in range(7):
            sessao = services.sessao_do_dia(self.plano, primeiro_dia + timedelta(days=k), self.linhas)
            if sessao is None:
                continue
            ficha[sessao.label] = [
                (i.exercise_id, i.opcao, i.sets, i.rep_min, i.rep_max) for i in sessao.exercises.all()
            ]
        return ficha

    def _treinar(self, dia, carga):
        sessao = services.sessao_do_dia(self.plano, dia, self.linhas)
        if sessao is None:
            return
        for item in sessao.da_opcao(1):
            if item.measure != Measure.REPS or item.exercise.sem_carga:
                continue
            for n in range(1, item.sets + 1):
                ExerciseLog.objects.create(
                    user=self.pessoa, exercise=item.exercise, date=dia, set_number=n,
                    weight_kg=Decimal(carga), reps=item.rep_max if n < item.sets else item.rep_max - 1,
                )

    def test_a_ficha_da_semana_oito_e_igual_a_da_semana_um(self):
        """Sete semanas de registro (cargas subindo, séries fechando e não
        fechando) não movem uma série da ficha: a adaptação fala na tela e
        não escreve na prescrição."""
        segunda = self.hoje - timedelta(days=self.hoje.weekday())
        antes = self._ficha_da_semana(segunda)
        retrato = self._retrato()
        for k in range(49):
            self._treinar(segunda + timedelta(days=k), 40 + k // 7 * 2.5)
        for item in self.linhas[0].exercises.all():
            self.client.get("%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id))
        self.client.get(reverse("workouts:routine"))
        self.assertEqual(self._ficha_da_semana(segunda + timedelta(days=49)), antes)
        self.assertEqual(self._retrato(), retrato)
        self.assertEqual(services.sync_active_routine(self.pessoa)[0].pk, self.plano.pk)

    def test_a_serie_de_ontem_nao_muda_a_prescricao_de_hoje(self):
        """Ontem perdido — ou feito — não compensa nem desconta hoje."""
        # A opção de hoje é a VARIAÇÃO do ciclo (sem escolha gravada): num
        # bloco ímpar — sábado 19/09 com cinco dias a partir de hoje, posição
        # 3 — é a 2, e ler sempre a 1 fazia `prescricao_de_hoje` responder
        # None para um exercício que só está na 1. Medido vermelho no sábado.
        sessao = services.sessao_do_dia(self.plano, self.hoje, self.linhas)
        opcao = services.opcao_do_dia(self.pessoa, sessao, self.hoje)
        sem_ontem = [(i.exercise_id, i.sets, i.rep_min, i.rep_max) for i in sessao.da_opcao(opcao)]
        self._treinar(self.hoje - timedelta(days=1), 50)
        sessao = services.sessao_do_dia(services.get_active_routine(self.pessoa), self.hoje)
        com_ontem = [(i.exercise_id, i.sets, i.rep_min, i.rep_max) for i in sessao.da_opcao(opcao)]
        self.assertEqual(com_ontem, sem_ontem)
        self.assertEqual(
            services.prescricao_de_hoje(self.pessoa, sem_ontem[0][0]),
            sem_ontem[0][1],
        )

    def test_treinar_em_dia_nao_declarado_nao_altera_dias_teto_nem_divisao(self):
        """Seis semanas registrando no fim de semana: `TrainingDay`, o teto
        semanal e a divisão continuam os declarados. Frequência observada
        não é intenção declarada."""
        dias = sorted(TrainingDay.objects.filter(user=self.pessoa).values_list("weekday", flat=True))
        tetos = services.tetos_da_semana(self.plano)
        fora = [d for d in range(7) if d not in dias]
        exercicio = next(i.exercise for i in self.linhas[0].exercises.all() if not i.exercise.sem_carga)
        for semana in range(6):
            for weekday in fora:
                dia = self.hoje - timedelta(days=self.hoje.weekday() + 7 * semana) + timedelta(days=weekday)
                for n in (1, 2, 3):
                    ExerciseLog.objects.create(
                        user=self.pessoa, exercise=exercicio, date=dia, set_number=n, weight_kg=Decimal(40), reps=10,
                    )
        self.client.get(reverse("workouts:routine"))
        self.client.get(reverse("plans:today"))
        plano, mudou = services.sync_active_routine(self.pessoa)
        self.assertFalse(mudou)
        self.assertEqual(plano.pk, self.plano.pk)
        self.assertEqual(plano.split, self.plano.split)
        self.assertEqual(sorted(TrainingDay.objects.filter(user=self.pessoa).values_list("weekday", flat=True)), dias)
        self.assertEqual(services.tetos_da_semana(plano), tetos)
