# -*- coding: utf-8 -*-
"""Ficha ÚNICA por letra: a variação entre as ocorrências é do ciclo, não da
pessoa (decisão do dono, 17/09/2026).

O motor continua montando as duas opções equivalentes de cada letra
(`workouts/opcoes.py`); o que muda é quem escolhe. Até 17/09 a ficha
mostrava "Opção 1 / Opção 2", recomendava a menos usada e pedia um toque.
Agora `services.variacao_do_dia` diz a opção pela POSIÇÃO no ciclo — na
rotação contínua, a primeira ocorrência de A faz a 1, a segunda a 2, a
terceira a 1 de novo (`p // n` ocorrências desde a posição zero) —, e a
pessoa vê uma ficha só, sem número de opção em lugar nenhum. A primeira
série do dia grava a variação (`EscolhaDeTreino`, registro INTERNO): o dia
gravado fica pinado, a ficha não muda no meio do treino.

O histórico e a contabilidade são por letra + exercício: "opção" nunca
aparece numa conta que a pessoa veja. `volume_da_semana` continua o pior
caso por ocorrência — é o teto do motor, não uma promessa da tela.

A versão rápida saiu do seletor da ficha e virou ação discreta no painel
("Menos tempo hoje?"), com `EventoDeProduto` por uso — o dado que decide em
30 dias se ela fica.
"""
import re
from datetime import date, timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from accounts.models import DuracaoTreino, TrainingDay
from config import relogio
from plans.tests import create_complete_user
from workouts import services
from workouts.models import EscolhaDeTreino, EventoDeProduto, VersaoDoTreino
from workouts.test_sequencia import fazer
from workouts.tests import sem_scripts

SEGUNDA = date(2026, 9, 14)
QUINTA = SEGUNDA + timedelta(days=3)


def _congelar(dia):
    """Hoje é `dia` — a DATA e o RELÓGIO (`config/relogio.py`), não só
    `localdate`. Congelar só `localdate` deixava `created_at` do plano
    nascer no dia da suíte: `test_com_a_letra_uma_vez_por_semana` ficava
    vermelho com a suíte numa segunda 21/09 (o plano nascia na semana
    SEGUINTE à de `SEGUNDA` e as semanas saíam [1, 1, 2]) — medido em
    18/09/2026 com `NUTRIPLAN_DATA_DA_SUITE=2026-09-21`."""
    return relogio.Relogio(dia).ligar()


def _pessoa(email, dias=5):
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference="two",
        split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


class AVariacaoEDoCicloTests(TestCase):
    """A OPÇÃO da letra (1/2) alterna com as VEZES que a letra já foi FEITA —
    presença, não posição no calendário (24/09/2026). A primeira vez que A é
    feita usa a opção 1, a segunda a 2, a terceira a 1: a mesma sequência do
    antigo ciclo quando nada é pulado, agora ancorada no que aconteceu."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("variacao@exemplo.com")
        self.plan = services.create_routine(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def _sessao(self, letra):
        return next(s for s in self.linhas if s.label == letra)

    def _variacao(self, letra, dia=None):
        return services.variacao_do_dia(
            self.plan, dia or SEGUNDA, self._sessao(letra), self.linhas, user=self.user
        )

    def _duas_opcoes(self, letra):
        sessao = self._sessao(letra)
        if len(sessao.opcoes) < 2:
            self.skipTest("a letra %s saiu com uma opção só neste catálogo" % letra)
        return sessao.opcoes

    def test_sem_historico_a_variacao_e_a_primeira_opcao(self):
        o = self._duas_opcoes("A")
        self.assertEqual(self._variacao("A"), o[0])

    def test_a_opcao_avanca_a_cada_vez_que_a_letra_e_feita(self):
        o = self._duas_opcoes("A")
        self.assertEqual(self._variacao("A"), o[0])            # 0 feitas de A
        fazer(self.user, self.plan, "A", SEGUNDA - timedelta(days=7))
        self.assertEqual(self._variacao("A"), o[1])            # 1 feita
        fazer(self.user, self.plan, "A", SEGUNDA - timedelta(days=6))
        self.assertEqual(self._variacao("A"), o[0])            # 2 feitas -> volta

    def test_a_variacao_da_letra_nao_depende_do_dia_do_calendario(self):
        """Presença, não posição: a variação de A é a mesma em qualquer dia
        que A caia, para a mesma contagem de feitas."""
        o = self._duas_opcoes("A")
        fazer(self.user, self.plan, "A", SEGUNDA - timedelta(days=7))  # 1 feita
        self.assertEqual(self._variacao("A", SEGUNDA), o[1])
        self.assertEqual(self._variacao("A", SEGUNDA + timedelta(days=3)), o[1])

    def test_a_escolha_gravada_do_dia_vence_a_variacao(self):
        """A primeira série pinou a opção; o dia fica como começou."""
        sessao = services.sessao_do_dia(self.plan, SEGUNDA, self.linhas, user=self.user)
        outra = sessao.opcoes[-1]
        services.registrar_escolha(self.user, sessao, outra, dia=SEGUNDA)
        self.assertEqual(services.opcao_do_dia(self.user, sessao, SEGUNDA, self.linhas), outra)

    def test_com_uma_opcao_so_a_variacao_e_ela(self):
        from types import SimpleNamespace
        # `opcoes` é property; com uma opção só a variação sai antes de olhar
        # plano/sequência, então uma sessão de mentira com opcoes=[1] basta.
        falsa = SimpleNamespace(opcoes=[1], label="A", plan=self.plan)
        self.assertEqual(
            services.variacao_do_dia(self.plan, SEGUNDA, falsa, self.linhas, user=self.user), 1
        )

    def test_a_recomendacao_pela_opcao_menos_usada_nao_existe_mais(self):
        self.assertFalse(hasattr(services, "opcao_recomendada"))

    def test_a_execucao_abre_a_variacao_e_a_primeira_serie_a_grava(self):
        """Fez A ontem (1 feita); hoje o recomendado é B, e a execução abre B
        na variação por presença (contagem de B), gravada pela 1ª série."""
        fazer(self.user, self.plan, "A", SEGUNDA - timedelta(days=1))
        estado = services.estado_do_treino(self.user, dia=SEGUNDA)
        self.assertEqual(estado.sessao.label, "B")
        esperada = services.variacao_do_dia(self.plan, SEGUNDA, estado.sessao, self.linhas, user=self.user)
        self.assertEqual(estado.opcao, esperada)
        self.client.force_login(self.user)
        item = estado.itens[0]
        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": item.exercise_id, "weight_kg": "40", "reps": "8",
            "op_id": "op-var", "dia": SEGUNDA.isoformat(),
            "sessao": estado.sessao.pk, "opcao": estado.opcao, "versao": estado.versao,
        })
        escolha = EscolhaDeTreino.objects.get(user=self.user, date=SEGUNDA)
        self.assertEqual((escolha.session_id, escolha.opcao), (estado.sessao.pk, esperada))

    def test_a_prescricao_de_hoje_e_da_variacao(self):
        """`prescricao_de_hoje` e `series_de_hoje` sem escolha gravada leem a
        opção da variação — um exercício que só está na outra opção não está
        prescrito hoje. Hoje (sem histórico) é A na primeira opção."""
        self._duas_opcoes("A")
        sessao = services.sessao_do_dia(self.plan, SEGUNDA, self.linhas, user=self.user)
        self.assertEqual(sessao.label, "A")
        opcao_hoje = services.variacao_do_dia(self.plan, SEGUNDA, sessao, self.linhas, user=self.user)
        outra = next(k for k in sessao.opcoes if k != opcao_hoje)
        de_fora = {j.exercise_id for j in sessao.da_opcao(outra)}
        so_na_hoje = [i for i in sessao.da_opcao(opcao_hoje) if i.exercise_id not in de_fora]
        so_na_outra = [i for i in sessao.da_opcao(outra) if i.exercise_id not in {j.exercise_id for j in sessao.da_opcao(opcao_hoje)}]
        self.assertTrue(so_na_hoje and so_na_outra)
        self.assertEqual(services.prescricao_de_hoje(self.user, so_na_hoje[0].exercise_id, SEGUNDA), so_na_hoje[0].sets)
        self.assertIsNone(services.prescricao_de_hoje(self.user, so_na_outra[0].exercise_id, SEGUNDA))
        self.assertEqual(services.series_de_hoje(self.user, so_na_hoje[0].exercise, SEGUNDA), (0, so_na_hoje[0].sets))


class ATelaNaoFalaDeOpcaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(QUINTA)
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("tela-unica@exemplo.com")
        from plans import services as plan_services

        plan_services.create_plan(self.user)
        self.plan = services.create_routine(self.user)
        self.client.force_login(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))
        # Presença: A, B, C feitos seg/ter/qua -> hoje (quinta) recomenda A (a
        # letra após C), e é a 2ª vez de A -> 2ª variação. C também foi feita 1×.
        fazer(self.user, self.plan, "A", SEGUNDA)
        fazer(self.user, self.plan, "B", SEGUNDA + timedelta(days=1))
        fazer(self.user, self.plan, "C", SEGUNDA + timedelta(days=2))
        self.hoje = services.sessao_do_dia(self.plan, QUINTA, self.linhas, user=self.user)

    def _ficha(self, sessao):
        resposta = self.client.get(reverse("workouts:ficha", args=[sessao.pk]))
        return sem_scripts(resposta.content.decode()), resposta

    def _variacao(self, sessao):
        return services.variacao_do_dia(self.plan, QUINTA, sessao, self.linhas, user=self.user)

    @staticmethod
    def _so_na(sessao, opcao):
        outra = next(k for k in sessao.opcoes if k != opcao)
        de_fora = {j.exercise_id for j in sessao.da_opcao(outra)}
        return [i for i in sessao.da_opcao(opcao) if i.exercise_id not in de_fora]

    def test_o_recomendado_hoje_e_a_letra_apos_a_ultima_feita(self):
        self.assertEqual(self.hoje.label, "A")

    def test_a_ficha_de_hoje_e_uma_lista_so_da_variacao_do_dia(self):
        html, _ = self._ficha(self.hoje)
        self.assertEqual(html.count('class="card opcao'), 1)
        for texto in ("Opção 1", "Opção 2", "Recomendada hoje", "Começar esta opção", "versões disponíveis"):
            self.assertNotIn(texto, html)
        if len(self.hoje.opcoes) > 1:
            opcao_hoje = self._variacao(self.hoje)  # 2ª vez de A -> 2ª variação
            so_hoje = self._so_na(self.hoje, opcao_hoje)
            outra = next(k for k in self.hoje.opcoes if k != opcao_hoje)
            so_outra = self._so_na(self.hoje, outra)
            if so_hoje:
                self.assertIn(so_hoje[0].exercise.name, html)
            if so_outra:
                self.assertNotIn(so_outra[0].exercise.name, html)

    def test_a_ficha_de_outra_letra_mostra_a_variacao_da_proxima_ocorrencia(self):
        """A ficha de C (não é hoje) mostra a variação da PRÓXIMA vez que C
        cai — opcoes[contagem(C) % n]. C foi feita 1×, então é a 2ª variação;
        e a lista não traz exercício exclusivo da outra versão. Sabotagem: com
        a variação fixa em 1 o exercício exclusivo da 2 some da lista."""
        linha_c = next(s for s in self.linhas if s.label == "C")
        if len(linha_c.opcoes) < 2:
            self.skipTest("a letra C saiu com uma opção só neste catálogo")
        html, resposta = self._ficha(linha_c)
        self.assertFalse(resposta.context["sessao"].eh_hoje)
        esperada = self._variacao(linha_c)
        self.assertEqual(esperada, linha_c.opcoes[1])  # contagem(C)=1
        outra = next(k for k in linha_c.opcoes if k != esperada)
        so_outra = self._so_na(linha_c, outra)
        if so_outra:
            self.assertNotIn(so_outra[0].exercise.name, html)
        self.assertNotIn("?exercicio=", html, "a ficha de outra letra não executa")

    def test_os_links_da_ficha_de_outra_letra_sao_leitura_da_variacao(self):
        """Na ficha de outra letra os links são de LEITURA (?de=ficha), e são
        exatamente os exercícios da variação da próxima ocorrência — nenhum
        exclusivo da outra versão, e nenhum link de execução."""
        linha_c = next(s for s in self.linhas if s.label == "C")
        if len(linha_c.opcoes) < 2:
            self.skipTest("a letra C saiu com uma opção só neste catálogo")
        html, _ = self._ficha(linha_c)
        esperada = self._variacao(linha_c)
        lidos = {int(pk) for pk in re.findall(r"/treino/exercicio/(\d+)/\?de=ficha&amp;", html)}
        self.assertEqual(lidos, {i.exercise_id for i in linha_c.da_opcao(esperada)})
        outra = next(k for k in linha_c.opcoes if k != esperada)
        so_outra = {i.exercise_id for i in self._so_na(linha_c, outra)}
        self.assertFalse(lidos & so_outra, "nenhum link é de exercício exclusivo da outra versão")
        self.assertNotIn("?exercicio=", html, "a ficha de outra letra não executa")

    def test_a_execucao_nao_imprime_opcao_nem_convida_a_trocar(self):
        html = sem_scripts(self.client.get(reverse("workouts:now")).content.decode())
        self.assertNotIn("Opção 2", html)
        self.assertNotIn("Opção 1", html)
        self.assertNotIn("agora__opcao-aviso", html)
        self.assertNotIn("trocar de opção", html)

    def test_o_painel_nao_anuncia_versoes(self):
        html = sem_scripts(self.client.get(reverse("workouts:routine")).content.decode())
        self.assertNotIn("versões disponíveis", html)
        self.assertNotIn("recomendada: opção", html)
        self.assertNotIn("hoje__opcao", html)

    def test_a_rota_de_escolher_nao_existe(self):
        with self.assertRaises(NoReverseMatch):
            reverse("workouts:escolher", args=[self.hoje.pk])


class AVersaoRapidaNoPainelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA)
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("rapida@exemplo.com")
        from plans import services as plan_services

        plan_services.create_plan(self.user)
        self.plan = services.create_routine(self.user)
        self.client.force_login(self.user)

    def test_o_painel_oferece_menos_tempo_hoje_em_dia_de_treino(self):
        html = sem_scripts(self.client.get(reverse("workouts:routine")).content.decode())
        self.assertIn("Menos tempo hoje?", html)
        self.assertIn(reverse("workouts:rapida_hoje"), html)

    def test_a_ficha_nao_tem_mais_o_seletor_de_versao(self):
        sessao = services.sessao_do_dia(self.plan, SEGUNDA)
        html = sem_scripts(self.client.get(reverse("workouts:ficha", args=[sessao.pk])).content.decode())
        self.assertNotIn("?versao=", html)
        self.assertNotIn('class="versoes"', html)

    def test_pedir_menos_tempo_pina_a_rapida_e_grava_um_evento_por_dia(self):
        resposta = self.client.post(reverse("workouts:rapida_hoje"))
        self.assertEqual(resposta.status_code, 302)
        escolha = EscolhaDeTreino.objects.get(user=self.user, date=SEGUNDA)
        self.assertEqual(escolha.versao, VersaoDoTreino.RAPIDO)
        self.assertEqual(EventoDeProduto.objects.filter(user=self.user, nome="versao_rapida").count(), 1)
        # Segundo toque no mesmo dia: nem duplica o evento nem quebra.
        self.client.post(reverse("workouts:rapida_hoje"))
        self.assertEqual(EventoDeProduto.objects.filter(user=self.user, nome="versao_rapida").count(), 1)
        estado = services.estado_do_treino(self.user)
        self.assertTrue(estado.rapida)
        html = sem_scripts(self.client.get(reverse("workouts:routine")).content.decode())
        self.assertIn("Treino completo", html)

    def test_o_evento_e_unico_por_pessoa_nome_e_dia_no_banco(self):
        """A contagem é de adoção, não de toques: o banco recusa o segundo
        registro do mesmo dia — `get_or_create` na view é a leitura disso."""
        from django.db import IntegrityError, transaction

        EventoDeProduto.objects.create(user=self.user, nome="versao_rapida", date=SEGUNDA)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EventoDeProduto.objects.create(user=self.user, nome="versao_rapida", date=SEGUNDA)

    def test_voltar_ao_completo(self):
        self.client.post(reverse("workouts:rapida_hoje"))
        self.client.post(reverse("workouts:rapida_hoje"), {"completo": "1"})
        self.assertEqual(EscolhaDeTreino.objects.get(user=self.user, date=SEGUNDA).versao, VersaoDoTreino.COMPLETO)

    def test_get_na_acao_volta_ao_painel(self):
        resposta = self.client.get(reverse("workouts:rapida_hoje"))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], reverse("workouts:routine"))

    def test_a_contagem_de_usos_e_dos_ultimos_trinta_dias_por_uso_e_por_pessoa(self):
        """O dado que decide a rápida em 30 dias: usos (pessoa × dia) e
        pessoas distintas, na janela — hoje e os 29 dias anteriores (30
        corridos): o uso de 29 dias atrás conta, o de 30 fica de fora; dois
        toques no mesmo dia são UM uso (a constraint garante). A linha no
        `medir_progressao` (T2.4, PR #13) chama esta função."""
        outra = _pessoa("rapida-2@exemplo.com")
        EventoDeProduto.objects.create(user=self.user, nome=EventoDeProduto.VERSAO_RAPIDA, date=SEGUNDA - timedelta(days=30))
        EventoDeProduto.objects.create(user=self.user, nome=EventoDeProduto.VERSAO_RAPIDA, date=SEGUNDA - timedelta(days=29))
        EventoDeProduto.objects.create(user=outra, nome=EventoDeProduto.VERSAO_RAPIDA, date=SEGUNDA - timedelta(days=1))
        self.client.post(reverse("workouts:rapida_hoje"))
        self.client.post(reverse("workouts:rapida_hoje"))
        self.assertEqual(services.usos_recentes(EventoDeProduto.VERSAO_RAPIDA), (3, 2))
        self.assertEqual(services.usos_recentes(EventoDeProduto.VERSAO_RAPIDA, dias=2), (2, 2))  # hoje e ontem
        self.assertEqual(services.usos_recentes(EventoDeProduto.VERSAO_RAPIDA, dias=1), (1, 1))  # só hoje
        self.assertEqual(services.usos_recentes("outro_evento"), (0, 0))
