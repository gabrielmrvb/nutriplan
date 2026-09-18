# -*- coding: utf-8 -*-
"""A leitura do exercício: demonstração a um toque, em QUALQUER dia.

Fora da sessão de hoje não havia caminho até o vídeo: a linha da ficha de
outro dia era um `<div>` inerte, e `?exercicio=` fora do dia dá 404. A
decisão de 10/09/2026 fechou o REGISTRO fora do dia e levou junto o VER, sem
que isso tivesse sido decidido — nenhum parágrafo nem teste proibia ler o
exercício de sexta numa terça (pesquisa de 13/09/2026; decisão do dono).

A rota `workouts:exercicio` é GET puro, do PLANO ATIVO da própria pessoa
(IDOR fechado como a ficha), e não "de hoje". Ver não é executar: zero
formulário, zero campo de carga, zero cronômetro — a régua da ficha.
"""
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.tests import (
    create_user, dias_incluindo_hoje, dias_sem_hoje, escolher_opcao_de_hoje, sem_scripts,
)


class ALeituraDoExercicioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="leitura@exemplo.com", weekdays=dias_incluindo_hoje(4))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        plano = services.get_active_routine(self.pessoa)
        hoje = timezone.localdate().weekday()
        sessoes = list(plano.sessions.order_by("weekday"))
        self.de_hoje = next(s for s in sessoes if s.weekday == hoje)
        self.de_outro_dia = next(s for s in sessoes if s.weekday != hoje)
        # "Fazer" e a execução são da opção ESCOLHIDA de hoje (15/09/2026).
        escolher_opcao_de_hoje(self.pessoa)
        self.item_hoje = self.de_hoje.da_opcao(1)[0]
        self.item_outro = self.de_outro_dia.da_opcao(1)[0]

    def _url(self, item):
        return reverse("workouts:exercicio", args=[item.exercise_id])

    def _html(self, item):
        return sem_scripts(self.client.get(self._url(item)).content.decode())

    def test_a_rota_mostra_a_demonstracao_a_dica_e_os_musculos(self):
        html = self._html(self.item_outro)
        exercicio = self.item_outro.exercise
        identificador = exercicio.video_embed_url.split("/embed/")[1].split("?")[0]
        self.assertIn(identificador, html)
        self.assertIn("data-demo", html)
        self.assertIn(exercicio.cue, html)
        self.assertIn(exercicio.get_muscle_group_display(), html)
        self.assertIn("Na sua ficha", html)
        self.assertIn("%d × %s" % (self.item_outro.sets, self.item_outro.rep_range), html)

    def test_ver_nao_e_executar(self):
        """A régua da ficha, aplicada aqui: nada que se use DURANTE a série.

        Desde 17/09/2026 a leitura TEM formulários — "Trocar" e "Voltar ao
        original" de "outras formas" —, e eles não são execução: postam em
        `workouts:trocar`, nunca na série. A régua passa a ser POR DESTINO:
        todo `<form>` do `<main>` aponta para a troca, e nada de carga,
        passo ou descanso entra na página."""
        import re

        html = self._html(self.item_outro)
        # Medido dentro do <main>: a barra de cima tem o "Sair".
        principal = html.split("<main", 1)[1].split("</main>", 1)[0]
        destinos = set(re.findall(r'<form[^>]*action="([^"]+)"', principal))
        self.assertLessEqual(destinos, {reverse("workouts:trocar")}, destinos)
        self.assertNotIn(reverse("workouts:record_set"), principal)
        self.assertNotIn('name="weight_kg"', html)
        self.assertNotIn("data-passo", html)
        self.assertNotIn("data-descanso", html)
        self.assertEqual(html.count("<iframe"), 0)

    def test_exercicio_de_outra_conta_ou_fora_do_plano_da_404(self):
        outra = create_user(email="outra-leitura@exemplo.com", weekdays=dias_incluindo_hoje(4))
        services.create_routine(outra)
        self.client.force_login(outra)
        # Um exercício ATIVO que não está no plano de `outra` — o catálogo tem
        # mais exercícios do que uma semana usa.
        from workouts.models import Exercise

        no_plano = set(
            Exercise.objects.filter(sessions__session__plan__user=outra).values_list("pk", flat=True)
        )
        fora = Exercise.objects.filter(is_active=True).exclude(pk__in=no_plano).first()
        self.assertIsNotNone(fora, "o fixture precisa de um exercício ativo fora do plano")
        self.assertEqual(self.client.get(reverse("workouts:exercicio", args=[fora.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("workouts:exercicio", args=[999999])).status_code, 404)

    def test_a_ficha_de_OUTRO_dia_leva_a_leitura_e_nao_a_execucao(self):
        """A linha de outro dia é porta para a LEITURA, nunca para a execução.

        O exercício conferido é o que a ficha DESENHA — desde a ficha única
        (17/09/2026) a ficha de outro dia mostra a variação da próxima
        ocorrência da letra, que pode ser a opção 2; afirmar o primeiro item
        da opção 1 passava só nos dias do calendário em que as duas
        coincidiam (vermelho na sexta 18/09/2026, no `main`)."""
        import re

        from workouts.models import Exercise

        ficha = sem_scripts(self.client.get(
            reverse("workouts:ficha", args=[self.de_outro_dia.pk])
        ).content.decode())
        # `?de=ficha&sessao=`: a leitura volta para ESTA ficha (T1.14).
        portas = re.findall(r'class="ficha-item__ver"\s+href="([^"]+)"', ficha)
        self.assertTrue(portas, "a ficha de outro dia não tem linha nenhuma")
        primeira = portas[0]
        self.assertTrue(primeira.startswith("/treino/exercicio/"), primeira)
        self.assertIn("?de=ficha&amp;sessao=%d" % self.de_outro_dia.pk, primeira)
        exercicio = Exercise.objects.get(pk=int(re.search(r"exercicio/(\d+)/", primeira).group(1)))
        self.assertIn('aria-label="Ver %s"' % exercicio.name, ficha)
        self.assertNotIn("?exercicio=", ficha)

    def test_a_ficha_de_hoje_tem_as_duas_portas(self):
        ficha = sem_scripts(self.client.get(
            reverse("workouts:ficha", args=[self.de_hoje.pk])
        ).content.decode())
        self.assertIn('href="%s?de=ficha&amp;' % self._url(self.item_hoje), ficha)
        self.assertIn(
            'href="%s?exercicio=%d"' % (reverse("workouts:now"), self.item_hoje.exercise_id), ficha
        )
        self.assertIn('aria-label="Fazer %s"' % self.item_hoje.exercise.name, ficha)

    def test_a_execucao_liga_o_titulo_a_leitura(self):
        html = sem_scripts(self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item_hoje.exercise_id)
        ).content.decode())
        titulo = html.split('class="agora__nome"', 1)[1].split("</h1>", 1)[0]
        # `?de=agora`: a leitura volta para a execução (T1.14).
        self.assertIn('href="%s?de=agora"' % self._url(self.item_hoje), titulo)

    def test_so_o_exercicio_de_hoje_oferece_executar(self):
        self.assertIn("?exercicio=%d" % self.item_hoje.exercise_id, self._html(self.item_hoje))
        html_outro = self._html(self.item_outro)
        if self.item_outro.exercise_id != self.item_hoje.exercise_id and not any(
            i.exercise_id == self.item_outro.exercise_id for i in self.de_hoje.exercises.all()
        ):
            self.assertNotIn("?exercicio=", html_outro)

    def test_o_historico_do_exercicio_aparece_por_sessao_e_para_em_doze(self):
        """"Como fui neste exercício?" — as últimas doze datas, uma linha cada:
        data, carga e as reps de cada série. A décima terceira fica de fora:
        UMA consulta, limitada, e a tela não vira relatório."""
        from datetime import timedelta
        from decimal import Decimal

        from workouts.models import ExerciseLog

        for dias_atras in range(1, 14):
            for serie, reps in ((1, 10), (2, 10), (3, 9)):
                ExerciseLog.objects.create(
                    user=self.pessoa, exercise=self.item_outro.exercise,
                    date=timezone.localdate() - timedelta(days=dias_atras),
                    set_number=serie, weight_kg=Decimal("60"), reps=reps,
                )
        html = self._html(self.item_outro)
        bloco = html.split('class="data-list historico"', 1)[1].split("</dl>", 1)[0]
        self.assertEqual(bloco.count("<dt class=\"num\">"), 12)
        self.assertIn("60 × 10, 10, 9", " ".join(bloco.split()))
        ontem = (timezone.localdate() - timedelta(days=1)).strftime("%d/%m")
        decima_terceira = (timezone.localdate() - timedelta(days=13)).strftime("%d/%m")
        self.assertIn(ontem, bloco)
        self.assertNotIn(decima_terceira, bloco)

    def test_sem_historico_a_leitura_diz_isso_sem_tabela_vazia(self):
        html = self._html(self.item_outro)
        self.assertNotIn('class="data-list historico"', html)
        self.assertIn("Ainda sem série registrada", html)

    def test_o_custo_e_fixo(self):
        url = self._url(self.item_outro)
        self.client.get(url)
        with CaptureQueriesContext(connection) as consultas:
            self.client.get(url)
        self.assertLessEqual(len(consultas), CONSULTAS_DA_LEITURA)

    def test_quem_nao_tem_ficha_recebe_404_e_nao_500(self):
        sem = create_user(email="sem-ficha@exemplo.com", weekdays=dias_sem_hoje(0))
        self.client.force_login(sem)
        self.assertEqual(self.client.get(self._url(self.item_outro)).status_code, 404)


#: Consultas da leitura, medidas em 13/09/2026 ao nascer (sessão, usuário,
#: perfil, plano, exercício, sessões da semana com itens, contagem de hoje,
#: e o histórico limitado a doze datas — DATAS_DO_HISTORICO, subiu de oito
#: em 16/09/2026 com o gráfico por exercício).
#: Teto: só sobe com medição escrita.
#: 9 em 15/09/2026: mais UMA, a escolha do dia (`escolha_do_dia`) — "Fazer
#: este exercício" só existe se ele está na OPÇÃO do dia, senão o link daria
#: 404 na execução. (`opcao_recomendada` só é consultada sem escolha gravada,
#: e o teste grava a escolha antes.) Constante com o histórico.
#: 11 em 17/09/2026 ("outras formas"): mais DUAS — as trocas da pessoa
#: (`aplicar_trocas`) e as alternativas do mesmo padrão (`alternativas_de`).
#: A consulta do perfil (equipamento) não entra: vem do `dispatch`; e as
#: linhas da semana passaram a vir SEM o exercício (`prefetch("exercises")`),
#: que a leitura não lia — `aplicar_trocas` busca o exercício só das linhas
#: trocadas. Constante com o histórico.
CONSULTAS_DA_LEITURA = 11


class OsDiasDaLeituraSaoOsDaSemanaTests(TestCase):
    """"Quando" lista CADA dia da semana em que a letra cai — e não o mesmo
    dia duas vezes.

    Achado na prova em produção de 18/09/2026 (casa com halteres / peso do
    corpo): a leitura de um exercício da letra A dizia "Quinta-feira (A),
    Quinta-feira (A)". As cópias vestidas de `sessoes_da_semana`
    (`copy.copy`) compartilham as MESMAS linhas pré-carregadas, e a view
    gravava `item.session = sessao` na linha compartilhada: a última
    ocorrência vencia e a segunda-feira sumia da lista.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        from datetime import date
        from unittest import mock

        from accounts.models import DuracaoTreino, TrainingDay
        from plans.tests import create_complete_user

        # Quinta 17/09/2026: em abc2 de segunda a sexta a letra A cai na
        # segunda (posição 0) e na quinta (posição 3).
        self.relogio = mock.patch("django.utils.timezone.localdate", return_value=date(2026, 9, 17))
        self.relogio.start()
        self.addCleanup(self.relogio.stop)
        self.pessoa = create_complete_user(
            email="dias-da-leitura@exemplo.com", experiencia="intermediario",
            split_preference="two", split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO,
        )
        TrainingDay.objects.filter(user=self.pessoa).delete()
        for d in range(5):
            TrainingDay.objects.create(user=self.pessoa, weekday=d, duration_min=60)
        self.plano = services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def test_a_letra_que_cai_duas_vezes_lista_os_dois_dias(self):
        linhas = list(self.plano.sessions.prefetch_related("exercises__exercise"))
        a = next(s for s in linhas if s.label == "A")
        item = a.da_opcao(1)[0]
        resposta = self.client.get(reverse("workouts:exercicio", args=[item.exercise_id]))
        self.assertEqual(resposta.status_code, 200)
        dias = resposta.context["dias"]
        self.assertEqual(dias, ["Segunda-feira (A)", "Quinta-feira (A)"])
        self.assertEqual(len(dias), len(set(dias)), "o mesmo dia listado duas vezes")
        html = sem_scripts(resposta.content.decode())
        self.assertIn("Segunda-feira (A), Quinta-feira (A)", html)
