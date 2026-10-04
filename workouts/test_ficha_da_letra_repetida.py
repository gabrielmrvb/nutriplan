# -*- coding: utf-8 -*-
"""A ficha da letra que cai HOJE mostra o andamento de hoje — mesmo quando a
linha dela nasceu noutro dia da semana.

Com a rotação contínua (17/09/2026) a sessão de hoje é a linha da LETRA da
posição, vestindo o dia; a linha guarda o `weekday` da primeira semana. Na
quinta-feira 17/09 a suíte inteira reprovou no CI em `main` (verde na
quarta): `anexar_historico` decidia "é hoje?" por `session.weekday ==
hoje.weekday()`, e a ficha de A (linha de segunda) aberta na quinta zerava o
balde "hoje" — a série registrada sumia do "1/4" do item, enquanto o
cabeçalho dizia "com série registrada hoje". Na quarta as linhas
coincidiam com os dias e ninguém viu.

O teste não depende do calendário: hoje é ESCOLHIDA uma letra cuja linha
nasceu noutro dia da semana — num plano de sete dias com três letras isso
sempre existe.

ATÉ 04/10/2026 o fixture movia `inicio_do_ciclo` até a linha mudar. Desde a
sequência por presença (24/09/2026) a letra de hoje não sai mais da posição
no ciclo, e sim da última FEITA: sem histórico é sempre A, cuja linha é a de
segunda. De terça a domingo o laço parava na primeira volta por acaso; na
segunda nenhuma volta servia e o `setUp` reprovava os dois testes — a
noturna, que roda na data real, via isso toda segunda. A escolha do dia
("Fazer outro treino") chega à ficha pelo mesmo `sessao_do_dia` que a
recomendação.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import Measure
from workouts.tests import create_user, dias_incluindo_hoje


class AFichaDaLetraRepetidaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="letra@exemplo.com", weekdays=dias_incluindo_hoje(7))
        self.plano = services.create_routine(self.pessoa)
        self.hoje = timezone.localdate()
        # A linha de cada letra é a primeira dela na ordem.
        canonica = {}
        for linha in sorted(self.plano.sessions.all(), key=lambda s: s.order):
            canonica.setdefault(linha.label, linha)
        letra = next(
            rotulo for rotulo, linha in canonica.items()
            if linha.weekday != self.hoje.weekday()
        )
        services.registrar_escolha_de_letra(self.pessoa, self.plano, letra)
        self.sessao = services.sessao_do_dia(self.plano, self.hoje, user=self.pessoa)
        self.linha = self.plano.sessions.get(pk=self.sessao.pk)
        self.client.force_login(self.pessoa)
        self.item = next(
            i for i in self.sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def test_a_serie_de_hoje_aparece_no_item_da_ficha(self):
        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": self.item.exercise_id, "weight_kg": "60", "reps": "10",
            "op_id": "op-letra", "dia": self.hoje.isoformat(),
        })
        ficha = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))
        self.assertEqual(ficha.status_code, 200)
        self.assertContains(ficha, "com série registrada hoje")
        self.assertContains(ficha, "1/%d" % self.item.sets)

    def test_o_controle_a_linha_de_hoje_e_de_outro_dia(self):
        """Controle: o fixture pôs hoje numa linha cujo `weekday` NÃO é hoje —
        senão o teste passaria pelo caminho antigo, por coincidência."""
        self.assertNotEqual(self.linha.weekday, self.hoje.weekday())
        self.assertTrue(services.ciclo_roda(self.plano))
