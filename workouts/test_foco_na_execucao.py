# -*- coding: utf-8 -*-
"""Concluir e desfazer devolvem ao exercício EM FOCO — não ao primeiro pendente.

`estado_do_treino` documenta que a pessoa ESCOLHE por onde começar (a ficha
oferece cada exercício como porta), e `ConcluirSerieView` descartava a
escolha: os três ramos terminavam em `redirect("workouts:now")`, sem
`?exercicio=`, e a tela voltava a abrir sozinha o primeiro pendente. Quem
começou pelo décimo exercício era levado ao primeiro depois de cada série.
Offline a fila deixa a pessoa onde está (`fila.js`) — o caminho degradado
era melhor que o normal. Achado da pesquisa de 13/09/2026.

O formulário passa a levar `exercicio` (o que está EM FOCO — não
`exercise_id`, que no desfazer pode ser outro exercício), e a view devolve a
ele enquanto houver série pendente. O campo viaja no corpo como qualquer
outro, então a fila offline o reenvia sem mudança de contrato; item antigo
sem o campo cai no redirect sem parâmetro, nunca em 404.

E a saída da tela ganha duas portas que faltavam: "Depois: X" vira link e o
cabeçalho ganha "← Ficha".
"""
import re
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts


class OFocoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="foco@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        # A execução abre a opção ESCOLHIDA de hoje (15/09/2026): a 1, e os
        # itens são os dela.
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.itens = sorted(sessao.da_opcao(1), key=lambda i: (i.order, i.pk))
        self.assertGreaterEqual(len(self.itens), 3, "o fixture precisa de três exercícios")
        self.terceiro = self.itens[2]

    def _post(self, **campos):
        corpo = {
            "exercise_id": self.terceiro.exercise_id,
            "weight_kg": "40",
            "reps": "10",
            "op_id": "op-%d" % ExerciseLog.objects.count(),
            "dia": self.hoje.isoformat(),
        }
        corpo.update(campos)
        return self.client.post(reverse("workouts:record_set"), corpo)

    def _url(self, item):
        # `#registro` (U7, 16/09/2026): a página seguinte abre com o bloco de
        # registro em foco, e não no topo — a pessoa descia de novo até a
        # carga a cada série. Alvo com `tabindex="-1"`, então o foco de
        # teclado e de leitor de tela cai nele (`test_o_alvo_do_fragmento`).
        return "%s?exercicio=%d#registro" % (reverse("workouts:now"), item.exercise_id)

    def test_o_alvo_do_fragmento_e_o_bloco_de_registro_e_recebe_foco(self):
        html = self.client.get(self._url(self.terceiro).split("#")[0]).content.decode()
        self.assertRegex(html, r'<div class="agora__registro"[^>]*id="registro"')
        self.assertRegex(html, r'<div class="agora__registro"[^>]*tabindex="-1"')

    def test_concluir_uma_serie_do_terceiro_devolve_ao_terceiro(self):
        resposta = self._post(exercicio=self.terceiro.exercise_id)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], self._url(self.terceiro))

    def test_fechar_a_ultima_serie_devolve_sem_parametro(self):
        """Sem série pendente no exercício, o parâmetro sobraria: a tela abre
        sozinha o próximo pendente, que é o comportamento de sempre."""
        for n in range(1, self.terceiro.sets):
            self._post(exercicio=self.terceiro.exercise_id, op_id="op-fim-%d" % n)
        resposta = self._post(exercicio=self.terceiro.exercise_id, op_id="op-fim-ultima")
        self.assertEqual(resposta["Location"], reverse("workouts:now"))

    def test_desfazer_serie_de_outro_exercicio_volta_ao_foco(self):
        """`exercise_id` do desfazer é o exercício que RECEBEU a última série;
        o foco é outro campo, e é ele que manda."""
        primeiro = self.itens[0]
        self._post(exercise_id=primeiro.exercise_id, exercicio=primeiro.exercise_id)
        resposta = self._post(
            exercise_id=primeiro.exercise_id, exercicio=self.terceiro.exercise_id,
            acao="desfazer", op_id="op-desfazer",
        )
        self.assertEqual(resposta["Location"], self._url(self.terceiro))
        self.assertEqual(ExerciseLog.objects.count(), 0)

    def test_foco_ausente_ou_ilegivel_cai_no_redirect_sem_parametro(self):
        """Item antigo da fila não tem o campo; um POST forjado pode ter lixo.
        Nenhum dos dois pode virar 404 no POST — a série foi gravada."""
        for foco in (None, "abc", "-1", "999999"):
            with self.subTest(foco=foco):
                extra = {} if foco is None else {"exercicio": foco}
                resposta = self._post(op_id="op-%s" % foco, **extra)
                self.assertEqual(resposta.status_code, 302)
                self.assertEqual(resposta["Location"], reverse("workouts:now"))

    def test_o_formulario_leva_o_foco_e_a_tela_oferece_as_duas_portas(self):
        html = sem_scripts(self.client.get(self._url(self.terceiro)).content.decode())
        # O hidden vale o exercício em foco, nos DOIS formulários.
        self.assertIn(
            '<input type="hidden" name="exercicio" value="%d">' % self.terceiro.exercise_id,
            html,
        )
        # "Depois" é um link para o próximo exercício.
        proximo = self.itens[3] if len(self.itens) > 3 else None
        if proximo is not None:
            self.assertRegex(
                html, r'<a class="agora__proximo-link"[^>]*href="[^"]*\?exercicio=%d"' % proximo.exercise_id
            )
        # "← Ficha" no cabeçalho, apontando para a sessão de hoje.
        sessao_url = reverse("workouts:ficha", args=[self.terceiro.session_id])
        cabecalho = html.split('class="page-head agora__head"', 1)[1].split("</div>", 1)[0]
        self.assertIn('href="%s"' % sessao_url, cabecalho)
        self.assertIn("Ficha", cabecalho)


class AExecucaoNasceEmFerroTests(TestCase):
    """`:root.modo-foco` na execução — escrito pelo SERVIDOR (CORTE, 16/09/2026).

    O contrato dizia desde a Mesa & Ferro que a execução nasce em Ferro por
    decisão de produto (luz baixa de academia) e que a classe é escrita pelo
    servidor; nenhuma view a escrevia — só a vitrine, por parâmetro. O
    gatilho existe no CSS (`config/test_ferro.py`) e é medido em contraste;
    este teste é quem prova que a tela o USA. O painel e a ficha continuam
    no regime do aparelho: a classe é da execução, não da área.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="ferro@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def _body(self, url):
        html = self.client.get(url).content.decode()
        return re.search(r"<html[^>]*>", html).group(0)

    def test_a_execucao_escreve_modo_foco_no_body(self):
        self.assertIn("modo-foco", self._body(reverse("workouts:now")))

    def test_o_painel_e_a_ficha_seguem_o_aparelho(self):
        self.assertNotIn("modo-foco", self._body(reverse("workouts:routine")))
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.assertNotIn("modo-foco", self._body(reverse("workouts:ficha", args=[sessao.pk])))
