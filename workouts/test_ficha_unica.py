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
from django.utils import timezone

from accounts.models import DuracaoTreino, TrainingDay
from config import relogio
from plans.tests import create_complete_user
from workouts import services
from workouts.models import EscolhaDeTreino, EventoDeProduto, ExerciseLog, TrainingPlan, VersaoDoTreino
from workouts.tests import sem_scripts

SEGUNDA = date(2026, 9, 14)


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
    """abc2 em cinco dias: A B C A B · C A B C A · B C A B C — a letra A cai
    nas posições 0, 3, 6, 9, 12…; a ocorrência é `p // 3`."""

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

    def _opcao(self, dia):
        sessao = services.sessao_do_dia(self.plan, dia, self.linhas)
        return sessao.label, services.variacao_do_dia(self.plan, dia, sessao, self.linhas)

    def test_a_primeira_ocorrencia_faz_a_um_a_segunda_a_dois_e_a_terceira_a_um(self):
        letras = [self._opcao(SEGUNDA + timedelta(days=k)) for k in range(0, 21) if (SEGUNDA + timedelta(days=k)).weekday() < 5]
        so_a = [opcao for letra, opcao in letras if letra == "A"]
        self.assertEqual(so_a, [1, 2, 1, 2, 1], letras)
        so_b = [opcao for letra, opcao in letras if letra == "B"]
        self.assertEqual(so_b, [1, 2, 1, 2, 1], letras)

    def test_a_letra_que_cai_duas_vezes_na_semana_varia_dentro_da_semana(self):
        """Segunda A (posição 0) e quinta A (posição 3): opções 1 e 2 na
        mesma semana — é o que a pessoa pedia ao escolher, sem tocar."""
        self.assertEqual(self._opcao(SEGUNDA), ("A", 1))
        self.assertEqual(self._opcao(SEGUNDA + timedelta(days=3)), ("A", 2))

    def test_a_escolha_gravada_do_dia_vence_a_variacao(self):
        """A primeira série pinou a opção 1 numa quinta em que a variação
        diria 2: o dia fica como começou."""
        quinta = SEGUNDA + timedelta(days=3)
        sessao = services.sessao_do_dia(self.plan, quinta, self.linhas)
        services.registrar_escolha(self.user, sessao, 1, dia=quinta)
        self.assertEqual(services.opcao_do_dia(self.user, sessao, quinta, self.linhas), 1)
        self.assertEqual(services.variacao_do_dia(self.plan, quinta, sessao, self.linhas), 2)

    def test_a_execucao_abre_a_variacao_do_dia_e_a_primeira_serie_a_grava(self):
        quinta = SEGUNDA + timedelta(days=3)
        self.relogio.desligar()
        self.relogio = _congelar(quinta)
        self.addCleanup(self.relogio.desligar)
        estado = services.estado_do_treino(self.user, dia=quinta)
        self.assertEqual(estado.sessao.label, "A")
        self.assertEqual(estado.opcao, 2)
        self.client.force_login(self.user)
        item = estado.itens[0]
        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": item.exercise_id, "weight_kg": "40", "reps": "8",
            "op_id": "op-var", "dia": quinta.isoformat(),
            "sessao": estado.sessao.pk, "opcao": estado.opcao, "versao": estado.versao,
        })
        escolha = EscolhaDeTreino.objects.get(user=self.user, date=quinta)
        self.assertEqual((escolha.session_id, escolha.opcao), (estado.sessao.pk, 2))

    def test_o_plano_preso_ao_dia_da_semana_conta_as_ocorrencias_pelo_calendario(self):
        """Plano de antes da rotação (`inicio_do_ciclo` em branco): a letra A
        cai na segunda e na quinta de toda semana — 1ª ocorrência (segunda)
        opção 1, 2ª (quinta) opção 2, 3ª (a segunda seguinte) opção 1 de
        novo. É a mesma conta do ciclo, só que pelo calendário das linhas."""
        TrainingPlan.objects.filter(pk=self.plan.pk).update(inicio_do_ciclo=None)
        self.plan.inicio_do_ciclo = None
        esperado = {0: 1, 3: 2, 7: 1, 10: 2}
        for atras, opcao in esperado.items():
            dia = SEGUNDA + timedelta(days=atras)
            sessao = services.sessao_do_dia(self.plan, dia, self.linhas)
            self.assertEqual(sessao.label, "A")
            self.assertEqual(services.variacao_do_dia(self.plan, dia, sessao, self.linhas), opcao, dia)

    def test_com_a_letra_uma_vez_por_semana_as_semanas_alternam(self):
        """Três dias em ABC, sem rotação: A só cai na segunda — semana 1 opção
        1, semana 2 opção 2, semana 3 opção 1."""
        user = _pessoa("tres-dias@exemplo.com", dias=3)
        plan = services.create_routine(user)
        TrainingPlan.objects.filter(pk=plan.pk).update(inicio_do_ciclo=None)
        plan.inicio_do_ciclo = None
        linhas = list(plan.sessions.prefetch_related("exercises__exercise"))
        segunda = services.sessao_do_dia(plan, SEGUNDA, linhas)
        if len(segunda.opcoes) < 2:
            self.skipTest("a letra A de três dias saiu com uma opção só neste catálogo")
        self.assertEqual(
            [services.variacao_do_dia(plan, SEGUNDA + timedelta(days=7 * k), segunda, linhas) for k in range(3)],
            [1, 2, 1],
        )

    def test_a_recomendacao_pela_opcao_menos_usada_nao_existe_mais(self):
        self.assertFalse(hasattr(services, "opcao_recomendada"))

    def test_a_prescricao_de_hoje_e_da_variacao(self):
        """`prescricao_de_hoje` e `series_de_hoje` sem escolha gravada leem
        a opção da variação — um exercício que só está na outra opção não
        está prescrito hoje."""
        quinta = SEGUNDA + timedelta(days=3)
        sessao = services.sessao_do_dia(self.plan, quinta, self.linhas)
        so_na_1 = [i for i in sessao.da_opcao(1) if i.exercise_id not in {j.exercise_id for j in sessao.da_opcao(2)}]
        na_2 = sessao.da_opcao(2)[0]
        self.assertTrue(so_na_1)
        self.assertIsNone(services.prescricao_de_hoje(self.user, so_na_1[0].exercise_id, quinta))
        self.assertEqual(services.prescricao_de_hoje(self.user, na_2.exercise_id, quinta), na_2.sets)
        self.assertEqual(services.series_de_hoje(self.user, na_2.exercise, quinta), (0, na_2.sets))


class ATelaNaoFalaDeOpcaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = _congelar(SEGUNDA + timedelta(days=3))  # quinta: A, segunda ocorrência
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("tela-unica@exemplo.com")
        from plans import services as plan_services

        plan_services.create_plan(self.user)
        self.plan = services.create_routine(self.user)
        self.client.force_login(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))
        self.hoje = services.sessao_do_dia(self.plan, SEGUNDA + timedelta(days=3), self.linhas)

    def test_a_ficha_de_hoje_e_uma_lista_so_da_variacao_do_dia(self):
        html = sem_scripts(self.client.get(reverse("workouts:ficha", args=[self.hoje.pk])).content.decode())
        self.assertEqual(html.count('class="card opcao'), 1)
        self.assertNotIn("Opção 1", html)
        self.assertNotIn("Opção 2", html)
        self.assertNotIn("Recomendada hoje", html)
        self.assertNotIn("Começar esta opção", html)
        self.assertNotIn("versões disponíveis", html)
        # A lista é a da opção 2 (segunda ocorrência de A): um exercício que
        # só está na 1 não aparece.
        so_na_1 = [i for i in self.hoje.da_opcao(1) if i.exercise_id not in {j.exercise_id for j in self.hoje.da_opcao(2)}]
        self.assertNotIn(so_na_1[0].exercise.name, html)
        self.assertIn(self.hoje.da_opcao(2)[0].exercise.name, html)

    def _ficha_de(self, letra_no_dia):
        """Abre a ficha da letra que cai em `letra_no_dia` e devolve (sessão,
        html, resposta) — a sessão vestida daquele dia é a mesma linha (pk
        da letra) que a URL da ficha aponta."""
        sessao = services.sessao_do_dia(self.plan, letra_no_dia, self.linhas)
        resposta = self.client.get(reverse("workouts:ficha", args=[sessao.pk]))
        return sessao, sem_scripts(resposta.content.decode()), resposta

    @staticmethod
    def _so_na(sessao, opcao):
        outra = next(k for k in sessao.opcoes if k != opcao)
        de_fora = {j.exercise_id for j in sessao.da_opcao(outra)}
        return [i for i in sessao.da_opcao(opcao) if i.exercise_id not in de_fora]

    def test_a_ficha_de_outro_dia_mostra_a_variacao_da_proxima_ocorrencia(self):
        """Quarta 16/09 (C, posição 2, bloco 0). A ficha de A, que não é
        hoje, representa a PRÓXIMA vez que A cai — quinta 17/09, posição 3
        → ocorrência 1 → opção 2. Usar "hoje" na conta dava à ficha de A a
        variação de quarta (opção 1): a lista mudava conforme o dia em que
        a pessoa a abria (revisão adversarial de 17/09). Sabotagem medida:
        com `hoje_data` no lugar da data da ficha este teste fica vermelho;
        quinta × sexta (posições 3 e 4) caem no MESMO bloco e não medem."""
        self.relogio.desligar()
        self.relogio = _congelar(SEGUNDA + timedelta(days=2))
        self.addCleanup(self.relogio.desligar)
        quinta = SEGUNDA + timedelta(days=3)
        a, html, resposta = self._ficha_de(quinta)
        self.assertEqual(a.label, "A")
        self.assertFalse(resposta.context["sessao"].eh_hoje)
        self.assertEqual(services.variacao_do_dia(self.plan, quinta, a, self.linhas), 2)
        self.assertEqual(services.variacao_do_dia(self.plan, SEGUNDA + timedelta(days=2), a, self.linhas), 1)
        so_na_1, so_na_2 = self._so_na(a, 1), self._so_na(a, 2)
        self.assertTrue(so_na_1 and so_na_2, "as duas versões precisam diferir para o teste medir")
        self.assertIn(so_na_2[0].exercise.name, html)
        self.assertNotIn(so_na_1[0].exercise.name, html)

    def test_na_segunda_semana_a_ficha_de_outro_dia_segue_a_rotacao(self):
        """Segunda 21/09 é C (posição 5, bloco 1 → opção 2). A ficha de A
        representa terça 22/09 (posição 6, bloco 2 → opção 1) — e não a
        variação de hoje. É a rotação contínua chegando à ficha de outro
        dia: a letra de segunda deixou de ser A, e a de A mudou de versão."""
        self.relogio.desligar()
        self.relogio = _congelar(SEGUNDA + timedelta(days=7))
        self.addCleanup(self.relogio.desligar)
        terca = SEGUNDA + timedelta(days=8)
        a, html, resposta = self._ficha_de(terca)
        self.assertEqual(a.label, "A")
        self.assertFalse(resposta.context["sessao"].eh_hoje)
        self.assertEqual(services.variacao_do_dia(self.plan, terca, a, self.linhas), 1)
        self.assertEqual(services.variacao_do_dia(self.plan, SEGUNDA + timedelta(days=7), a, self.linhas), 2)
        so_na_1, so_na_2 = self._so_na(a, 1), self._so_na(a, 2)
        self.assertIn(so_na_1[0].exercise.name, html)
        self.assertNotIn(so_na_2[0].exercise.name, html)

    # ---- os LINKS da ficha de outro dia, por paridade do bloco ----------
    #
    # `test_a_ficha_de_OUTRO_dia_leva_a_leitura_e_nao_a_execucao`
    # (`test_exercicio_leitura.py`) assumia que a ficha de outro dia mostra a
    # opção 1 e caiu ao rodar noutro dia (fatiamento do PR #33, 18/09/2026);
    # a asserção de lá virou tolerante — "todo link é de leitura e da
    # sessão". O que ela deixou de medir está AQUI, com a data escrita: em
    # cada ramo da paridade, os links de leitura são EXATAMENTE os
    # exercícios da variação que a próxima ocorrência vai usar. Sabotagem
    # medida: `variacao_do_dia` devolvendo sempre 1 derruba o ramo ímpar;
    # sempre 2 derruba o ramo par — cada ramo fica vermelho sozinho.

    @staticmethod
    def _links_de_leitura(html):
        return {int(pk) for pk in re.findall(r"/treino/exercicio/(\d+)/\?de=ficha&amp;", html)}

    def _os_links_sao_da_opcao(self, hoje, dia_da_ficha, opcao):
        self.relogio.desligar()
        self.relogio = _congelar(hoje)
        self.addCleanup(self.relogio.desligar)
        a, html, resposta = self._ficha_de(dia_da_ficha)
        self.assertEqual(a.label, "A")
        self.assertFalse(resposta.context["sessao"].eh_hoje)
        self.assertEqual(services.variacao_do_dia(self.plan, dia_da_ficha, a, self.linhas), opcao)
        outra = next(k for k in a.opcoes if k != opcao)
        so_na_outra = {i.exercise_id for i in self._so_na(a, outra)}
        self.assertTrue(so_na_outra, "as duas versões precisam diferir para o teste medir")
        lidos = self._links_de_leitura(html)
        self.assertEqual(lidos, {i.exercise_id for i in a.da_opcao(opcao)})
        self.assertFalse(lidos & so_na_outra, "nenhum link é de exercício exclusivo da outra versão")
        self.assertNotIn("?exercicio=", html, "a ficha de outro dia não executa")

    def test_no_bloco_impar_os_links_de_leitura_sao_da_opcao_2(self):
        """Quarta 16/09 (posição 2, bloco 0): a ficha de A é quinta 17/09,
        posição 3, bloco 1 → opção 2."""
        self._os_links_sao_da_opcao(SEGUNDA + timedelta(days=2), SEGUNDA + timedelta(days=3), 2)

    def test_no_bloco_par_os_links_de_leitura_sao_da_opcao_1(self):
        """Segunda 21/09 (posição 5, bloco 1): a ficha de A é terça 22/09,
        posição 6, bloco 2 → opção 1."""
        self._os_links_sao_da_opcao(SEGUNDA + timedelta(days=7), SEGUNDA + timedelta(days=8), 1)

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
