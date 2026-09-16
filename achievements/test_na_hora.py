# -*- coding: utf-8 -*-
"""A conquista nasce NA HORA em que a condição fecha, e a tela avisa.

Avaliação de 16/09/2026 (B5 e B35), conta nova, primeiro treino da vida:

- a primeira série do dia gravou, e NENHUMA conquista nasceu — o POST só
  avaliava o catálogo quando `supera_recorde` dizia sim, e estreia não é
  recorde. "Primeiro treino" ficou 1/1 sem desbloquear; 10 das 11 regras
  são assim, e "Semana completa" expira em duas semanas sem visita;
- ela só nasceu ao abrir /conquistas/, e nasceu MUDA: a página chamava
  `avaliar` sem `anunciar`, então a pessoa via a medalha na lista sem
  nunca ter visto "Conquista desbloqueada";
- o Progresso mostrava "Desbloqueadas 0" com a barra "Primeiro treino 1/1"
  CHEIA na mesma caixa — `resumo` não chama `avaliar` (decisão medida:
  43 consultas, crescendo com o histórico) e pintava 100 % de uma
  conquista que não existia.

Três correções, com o orçamento de consultas preservado:

1. o POST da série avalia o catálogo na PRIMEIRA série do dia — além do
   recorde. É um evento por dia de treino, e é o único momento em que
   "um dia de treino passa a existir" (`dias_treinados`, `ofensiva`,
   `semana-completa` e os treinos-N mudam AÍ). A segunda série em diante
   continua no custo de sempre (`workouts.test_recorde_na_hora`);
2. `ConquistasView` anuncia o que `avaliar` devolve — a mesma página que
   desbloqueia mostra o aviso;
3. `resumo` desbloqueia SÓ a regra que chegou a 100 %, com os dados que já
   reuniu — duas consultas, uma vez, em vez do catálogo inteiro a cada
   visita —, e anuncia quando recebe o `request`.
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

from achievements import services
from achievements.context_processors import CHAVE
from achievements.models import UserAchievement
from workouts import services as treino
from workouts.models import ExerciseLog, Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class _ComTreinoDeHoje(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="estreia@exemplo.com", weekdays=dias_incluindo_hoje(5))
        treino.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def _serie(self, op_id, peso="40"):
        return self.client.post(reverse("workouts:record_set"), {
            "exercise_id": self.item.exercise_id, "weight_kg": peso, "reps": "10",
            "op_id": op_id, "dia": self.hoje.isoformat(),
        })

    def _limpar_aviso(self):
        sessao = self.client.session
        sessao.pop(CHAVE, None)
        sessao.save()

    def _log(self, dias_atras, serie=1, peso="40"):
        return ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.item.exercise,
            date=self.hoje - timedelta(days=dias_atras), set_number=serie,
            weight_kg=Decimal(peso), reps=10,
        )


class APrimeiraSerieDoDiaAvaliaTests(_ComTreinoDeHoje):
    def test_a_primeira_serie_da_vida_desbloqueia_o_primeiro_treino_e_avisa(self):
        """Estreia não é recorde (`supera_recorde` exige histórico anterior), e
        era por isso que a conquista mais óbvia do app nunca nascia na hora."""
        resposta = self._serie("op-estreia")
        self.assertEqual(resposta.status_code, 302)
        conquista = UserAchievement.objects.get(user=self.pessoa, slug="primeiro-treino")
        self.assertIn(conquista.pk, self.client.session.get(CHAVE, []))
        html = self.client.get(resposta.url).content.decode()
        self.assertIn("Conquista desbloqueada", html)
        self.assertIn("Primeiro treino", html)

    def test_a_segunda_serie_do_dia_nao_avalia_de_novo(self):
        """A fila reenvia séries em rajada: só a PRIMEIRA do dia paga o catálogo."""
        self._serie("op-1")
        self._limpar_aviso()
        with CaptureQueriesContext(connection) as segunda:
            self._serie("op-2")
        self.assertNotIn(CHAVE, self.client.session)
        # Controle positivo do mesmo orçamento: a primeira paga o catálogo.
        outra = create_user(email="outra@exemplo.com", weekdays=dias_incluindo_hoje(5))
        treino.create_routine(outra)
        escolher_opcao_de_hoje(outra)
        self.client.force_login(outra)
        with CaptureQueriesContext(connection) as primeira:
            self._serie("op-3")
        self.assertGreater(len(primeira), len(segunda) + 20)

    def test_o_reenvio_da_fila_da_primeira_serie_nao_reavalia(self):
        """`criada=False` é reenvio reconhecido: não há dia novo para avaliar."""
        self._serie("op-1")
        self._limpar_aviso()
        with CaptureQueriesContext(connection) as reenvio:
            self._serie("op-1")
        self.assertNotIn(CHAVE, self.client.session)
        self.assertLess(len(reenvio), 20)

    def test_o_quinto_dia_de_treino_fecha_cinco_treinos_na_primeira_serie(self):
        for dias_atras in (2, 4, 6, 8):
            self._log(dias_atras)
        self._serie("op-quinto")
        slugs = set(UserAchievement.objects.filter(user=self.pessoa).values_list("slug", flat=True))
        self.assertIn("treinos-5", slugs)
        self.assertIn("primeiro-treino", slugs)


class APaginaDeConquistasAvisaTests(_ComTreinoDeHoje):
    def test_o_que_a_pagina_desbloqueia_ela_mesma_anuncia(self):
        """Conta antiga com histórico e sem avaliação: a página desbloqueia
        (retroatividade) e mostra "Conquista desbloqueada" na MESMA visita."""
        self._log(3)
        html = self.client.get(reverse("achievements:list")).content.decode()
        self.assertIn("Conquista desbloqueada", html)
        self.assertIn(CHAVE, self.client.session)


class OResumoNaoPintaCemPorCentoDeUmaConquistaTrancadaTests(_ComTreinoDeHoje):
    def test_a_regra_que_chegou_a_100_e_desbloqueada_no_resumo(self):
        """Toda regra a 100 % nasce — o fixture fecha "Primeiro treino" e
        "3 dias de ofensiva" ao mesmo tempo —, e `quantas` conta o que
        existe no banco DEPOIS, não antes."""
        self._log(3)
        quantas, recente, proxima = services.resumo(self.pessoa)
        ganhas = UserAchievement.objects.filter(user=self.pessoa)
        self.assertIn("primeiro-treino", set(ganhas.values_list("slug", flat=True)))
        self.assertEqual(quantas, ganhas.count())
        self.assertEqual(recente.pk, max(c.pk for c in ganhas))
        self.assertIsNotNone(proxima)
        self.assertLess(proxima["pct"], 100)

    def test_o_resumo_anuncia_quando_recebe_o_pedido(self):
        self._log(3)
        html = self.client.get(reverse("plans:history")).content.decode()
        self.assertIn("Conquista desbloqueada", html)
        desbloqueadas = re.search(r"<dt>Desbloqueadas</dt>\s*<dd class=\"num\">(\d+)</dd>", html)
        self.assertEqual(
            int(desbloqueadas.group(1)),
            UserAchievement.objects.filter(user=self.pessoa).count(),
        )
        self.assertNotIn('style="width: 100%"', html)

    def test_no_dia_a_dia_o_resumo_custa_o_mesmo_com_ou_sem_conquista(self):
        """A avaliação pontual só roda na visita em que algo fechou; depois
        dela o custo volta ao de quem não tem nada a 100 %."""
        self._log(3)
        services.resumo(self.pessoa)  # desbloqueia
        with CaptureQueriesContext(connection) as depois:
            services.resumo(self.pessoa)
        controle = create_user(email="controle@exemplo.com", weekdays=dias_incluindo_hoje(5))
        with CaptureQueriesContext(connection) as sem_nada:
            services.resumo(controle)
        self.assertEqual(len(depois), len(sem_nada))


class ContinuarVoltaParaOndeOAvisoApareceuTests(_ComTreinoDeHoje):
    """"Continuar" fecha o aviso e DEVOLVE A TELA. O parcial escreve
    `request.path` em `proximo`, e a view só conhecia três NOMES — todo
    caminho caía no padrão, a Home. Com o aviso nascendo na execução e no
    Progresso (B5/B35), "Continuar" no meio do treino jogava a pessoa para
    fora dele. A lista continua FECHADA: o caminho só vale se for o de um
    destino da lista."""

    def _continuar(self, proximo):
        return self.client.post(reverse("achievements:marcar_vistas"), {"proximo": proximo})

    def test_o_caminho_de_um_destino_da_lista_e_aceito(self):
        for nome in ("plans:history", "workouts:now", "achievements:list"):
            caminho = reverse(nome)
            self.assertEqual(self._continuar(caminho).url, caminho, nome)

    def test_caminho_de_fora_da_lista_cai_na_home(self):
        for estranho in ("https://exemplo.invalid/", "//exemplo.invalid", "/conta/perfil/", ""):
            self.assertEqual(self._continuar(estranho).url, reverse("plans:today"), estranho)
