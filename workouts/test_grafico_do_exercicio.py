# -*- coding: utf-8 -*-
"""A tela do exercício mostra a carga máxima das últimas doze sessões como curva.

BENCHMARK-2026-09 (b): gráfico de progressão por exercício é padrão em Hevy,
Strong, Fitbod e Strava. Aqui é uma polilinha SVG por template — o mesmo
padrão da curva de peso (`plans/views._curva_de_peso`), generalizado em
`workouts/curva.py` —, com cor por token e sem biblioteca.

SÓ carga máxima. Volume por sessão ficou de fora por duas decisões escritas
(`progresso.py`, `historico_do_exercicio`); a divergência com o benchmark
está registrada na spec como "recomendo rever".
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import curva, services
from workouts.models import Exercise, ExerciseLog
from workouts.tests import create_user, dias_incluindo_hoje


class ACurvaTests(TestCase):
    def test_menos_de_dois_pontos_nao_e_curva(self):
        self.assertIsNone(curva.curva([]))
        self.assertIsNone(curva.curva([Decimal("60")]))

    def test_a_escala_e_a_do_periodo_e_o_tempo_corre_para_a_direita(self):
        c = curva.curva([Decimal("50"), Decimal("60"), Decimal("55")], largura=200, altura=100)
        pontos = [tuple(float(v) for v in p.split(",")) for p in c["pontos"].split()]
        self.assertEqual([p[0] for p in pontos], [0.0, 100.0, 200.0])
        self.assertEqual(pontos[1][1], 0.0)     # o maior no topo
        self.assertEqual(pontos[0][1], 100.0)   # o menor embaixo
        self.assertEqual(c["ultimo"], pontos[-1])

    def test_faixa_estreita_tem_piso(self):
        c = curva.curva([Decimal("60"), Decimal("60.1")], largura=100, altura=100, piso=0.4)
        pontos = [tuple(float(v) for v in p.split(",")) for p in c["pontos"].split()]
        self.assertGreater(pontos[0][1] - pontos[1][1], 0)
        self.assertLess(pontos[0][1] - pontos[1][1], 100)  # 0,1 kg não vira montanha


class ATelaDoExercicioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="curva@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        # `sem_carga` é propriedade (deriva de `equipment`), não campo — não dá
        # para filtrar por ela no banco. Excluir `bodyweight` tem o mesmo efeito.
        self.exercicio = Exercise.objects.filter(is_active=True).exclude(equipment="bodyweight").first()

    def _sessoes(self, n, base=50):
        for i in range(n):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.exercicio, date=self.hoje - timedelta(days=(n - i) * 3),
                set_number=1, weight_kg=Decimal(base + i), reps=10,
            )

    def _tela(self):
        return self.client.get(reverse("workouts:exercicio", args=[self.exercicio.pk])).content.decode()

    def test_doze_sessoes_e_nao_oito(self):
        self._sessoes(14)
        self.assertEqual(len(services.historico_do_exercicio(self.pessoa, self.exercicio)), 12)

    def test_com_duas_ou_mais_sessoes_ha_curva_com_rotulo_acessivel(self):
        self._sessoes(3)
        html = self._tela()
        self.assertIn('class="curva__grafico"', html)
        self.assertIn('role="img"', html)
        self.assertIn("Carga máxima", html)
        self.assertIn("52 kg", html)  # a última no rótulo
        self.assertIn('class="curva__ponto"', html)
        # O app é pt-BR e o template localiza número solto (`{{ }}` sozinho
        # vira "300,0"); `cx`/`cy` são atributo SVG, não texto de tela, e
        # vírgula decimal ali quebra a posição do ponto — pegou na primeira
        # versão. `float()` só aceita ponto.
        cx = html.split('class="curva__ponto" cx="', 1)[1].split('"', 1)[0]
        cy = html.split('cy="', 1)[1].split('"', 1)[0]
        float(cx)
        float(cy)

    def test_com_uma_sessao_nao_ha_curva(self):
        self._sessoes(1)
        self.assertNotIn('class="curva__grafico"', self._tela())

    def test_exercicio_sem_carga_nao_tem_curva(self):
        self.exercicio = Exercise.objects.filter(is_active=True, equipment="bodyweight").first()
        if self.exercicio is None:
            self.skipTest("catálogo sem exercício sem carga")
        for i in range(3):
            # Peso do corpo grava ZERO, não nulo — a coluna é NOT NULL
            # (`progresso.py`, docstring de `progressao_de_carga`).
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.exercicio,
                date=self.hoje - timedelta(days=3 * (i + 1)),
                set_number=1, weight_kg=Decimal("0"), reps=30,
            )
        self.assertNotIn('class="curva__grafico"', self._tela())

    def test_a_curva_desenha_do_mais_antigo_para_o_mais_novo(self):
        """Sabotagem (a): trocar `reversed(historico)` por `historico` continua
        passando o teste unitário da curva (ele é puro), mas desenha o tempo de
        trás para frente — a sessão de HOJE cairia na esquerda do gráfico.

        Com uma série crescente, o ÚLTIMO ponto (maior x) tem de carregar o
        MAIOR valor — e como o SVG inverte o eixo Y, isso é o `y` mais baixo
        (mais para cima na tela) entre todos os pontos.
        """
        self._sessoes(4)  # cargas 50, 51, 52, 53 — cronologicamente crescentes
        html = self._tela()
        pontos_svg = html.split('class="curva__grafico"', 1)[1].split('points="', 1)[1].split('"', 1)[0]
        pontos = [tuple(float(v) for v in p.split(",")) for p in pontos_svg.split()]
        self.assertEqual(pontos[-1][1], min(p[1] for p in pontos))

    def test_a_cor_vem_de_token(self):
        from django.conf import settings
        css = (settings.BASE_DIR / "static/css/app.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.curva--carga \.curva__grafico\s*\{[^}]*color:\s*var\(--")

    def test_a_figure_nao_herda_a_margem_padrao_do_navegador(self):
        """`<figure>` é o primeiro elemento com esse nome no app, e o
        navegador aplica `margin: 1em 40px` por padrão quando ninguém zera —
        dentro do card isso comia 80px de largura e o SVG (`width: 100%`)
        desenhava 230px num card de 390px, achatando a curva de carga. A
        régua é a mesma classe `.curva--carga` que já dá a cor: sem ela
        reaparecer aqui com `margin`, o navegador reimpõe o padrão."""
        from django.conf import settings
        css = (settings.BASE_DIR / "static/css/app.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.curva--carga\s*\{[^}]*margin")
