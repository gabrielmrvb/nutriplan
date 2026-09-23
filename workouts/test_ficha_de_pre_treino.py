# -*- coding: utf-8 -*-
"""A FICHA VIRA TELA DE PRÉ-TREINO (22/09/2026).

Auditada pelo dono, logado, em desktop e a 390 px: a ficha era "número,
nome, 4 × 6-10 Costas, Fazer" — uma lista de texto. O que faltava, e o que
este arquivo prende:

1. **com quanto começar.** A carga da última vez só existia na execução, e
   para saber com quanto começar a pessoa abria os nove exercícios um a um.
   Agora cada card diz "40 kg × 6" (ou "primeira vez"), sem consulta a mais
   — sai do balde `anterior` que `load_history` já trazia;
2. **o que é o movimento.** A miniatura do catálogo, a mesma da execução;
3. **quanto falta.** O estado por exercício (4/4, 2/4, "Fazer") e uma barra
   de progresso de verdade no topo;
4. **"outras formas" era um rótulo verde com cara de link** — e não era um.
   Virou "trocar", com ícone, verbo e porta própria;
5. **começar o treino pedia dois toques com dois nomes** ("Começar treino"
   no painel, "Começar pelo primeiro" aqui). Um CTA, o mesmo texto, preso
   ao rodapé no celular; "Continuar treino (2/9)" quando já há série;
6. **o cabeçalho dizia tudo duas vezes** ("8 exercícios · 28 séries · ~65
   min" no título E dentro do cartão);
7. **"Por que essa ficha"**, o diferencial do app sobre um caderno, estava
   atrás de um `<details>` na OUTRA tela.
"""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.tests import create_user, escolher_opcao_de_hoje

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")


class AFichaDePreTreinoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(
            email="pre-treino@exemplo.com", weekdays=(timezone.localdate().weekday(),)
        )
        services.sync_active_routine(self.user)
        escolher_opcao_de_hoje(self.user)
        self.client.force_login(self.user)
        self.plano = services.get_active_routine(self.user)
        self.sessao = services.sessao_do_dia(self.plano, timezone.localdate())
        self.itens = services.estado_do_treino(self.user).itens

    def _html(self):
        return self.client.get(reverse("workouts:ficha", args=[self.sessao.pk])).content.decode()

    def _ontem(self, item, peso="42.5", reps=6):
        ontem = timezone.localdate() - timedelta(days=7)
        services.record_load(self.user, item.exercise, Decimal(peso), set_number=1, reps=reps, day=ontem)

    # ---------------------------------------------------- o que o card diz

    def test_cada_card_traz_a_miniatura_do_movimento(self):
        html = self._html()
        com_foto = [i for i in self.itens if i.exercise.frames]
        self.assertTrue(com_foto, "o catálogo de teste não tem foto nenhuma")
        self.assertIn(com_foto[0].exercise.frames[0], html)
        self.assertIn("ficha-item__foto", html)

    def test_o_card_diz_series_reps_descanso_musculo_e_equipamento(self):
        item = self.itens[0]
        html = self._html()
        self.assertIn("ficha-item__dose", html)
        self.assertIn(item.rep_range, html)
        self.assertIn(item.rest_display, html)
        self.assertIn(item.exercise.get_muscle_group_display(), html)
        self.assertIn(item.exercise.get_equipment_display().lower(), html)

    def test_o_card_diz_a_ultima_carga_sem_abrir_o_exercicio(self):
        """Era o motivo de abrir os nove exercícios um a um."""
        item = self.itens[0]
        self._ontem(item, "42.5", 6)
        html = self._html()
        self.assertIn("ficha-item__ultima", html)
        self.assertIn("42,5", html)
        self.assertIn(">6<", html)

    def test_sem_historico_o_card_diz_primeira_vez(self):
        self.assertIn("primeira vez", self._html())

    def test_a_ultima_carga_nao_custa_consulta_nenhuma(self):
        """Ela sai do balde que `load_history` já trazia. O teto da ficha é
        de `plans/test_stress` (17); aqui o que se mede é a DIFERENÇA: com
        histórico em três exercícios, a mesma tela custa o mesmo."""
        sem_historico = self._contar()
        for item in self.itens[:3]:
            self._ontem(item)
        self.assertEqual(self._contar(), sem_historico)

    def _contar(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))
        return len(ctx)

    # ---------------------------------------------------- estado e progresso

    def test_o_estado_de_cada_exercicio_aparece_na_lista(self):
        item = self.itens[0]
        services.record_load(self.user, item.exercise, Decimal("40"), set_number=1, reps=8)
        html = self._html()
        self.assertIn("ficha-item--andamento", html)
        self.assertIn("1/%d" % item.sets, html)

    def test_o_exercicio_fechado_marca_o_card_inteiro(self):
        item = self.itens[0]
        for n in range(1, item.sets + 1):
            services.record_load(self.user, item.exercise, Decimal("40"), set_number=n, reps=8)
        self.assertIn("ficha-item--feito", self._html())

    def test_o_progresso_e_uma_barra_e_um_texto(self):
        html = self._html()
        self.assertIn("ficha__barra", html)
        self.assertIn("progress__fill", html)
        self.assertIn("com série registrada hoje", html)

    # ------------------------------------------------------------ as ações

    def test_outras_formas_virou_trocar_com_verbo_e_porta_propria(self):
        html = self._html()
        # O rótulo verde dentro do link do nome — com cara de link, sem ser
        # um — não existe mais; o que existe é uma ação com verbo. A frase
        # "2 outras formas" continua, mas só no `aria-label` do botão, que é
        # onde ela informa em vez de confundir.
        self.assertNotIn("ficha-item__formas", html)
        self.assertIn("ficha-item__trocar", html)
        self.assertIn(">trocar<", html)
        self.assertIn("#outras-formas", html)

    def test_um_CTA_com_o_mesmo_texto_do_painel(self):
        html = self._html()
        self.assertIn("Começar treino", html)
        self.assertNotIn("Começar pelo primeiro", html)
        painel = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertIn("Começar treino", painel)

    def test_com_serie_hoje_o_CTA_continua_e_conta(self):
        item = self.itens[0]
        services.record_load(self.user, item.exercise, Decimal("40"), set_number=1, reps=8)
        html = self._html()
        self.assertIn("Continuar treino (1/%d)" % len(self.itens), html)
        self.assertIn(reverse("workouts:encerrar"), html)

    def test_o_CTA_fica_preso_ao_rodape_no_celular(self):
        bloco = CSS[CSS.index(".ficha__acoes {"):]
        bloco = bloco[: bloco.index("}")]
        self.assertIn("position: fixed", bloco)
        self.assertIn("var(--tabbar-h)", bloco, "ele não pode cobrir a barra de abas")

    # -------------------------------------------------- cabeçalho e o porquê

    def test_o_cabecalho_diz_os_numeros_uma_vez_so(self):
        """"8 exercícios · 28 séries · ~65 min" aparecia no título E dentro
        do cartão da ficha, a dois dedos de distância."""
        html = self._html()
        self.assertNotIn("opcao__meta", html)
        self.assertNotIn("opcao__equipamentos", html)
        self.assertEqual(html.count("~%d min" % self.sessao.minutos_da_opcao(1)), 1)

    def test_o_cabecalho_lista_o_equipamento_necessario(self):
        html = self._html()
        self.assertIn("ficha__equipamentos", html)
        equipamentos = {i.exercise.get_equipment_display().lower() for i in self.itens}
        for nome in equipamentos:
            self.assertIn(nome, html)

    def test_por_que_essa_ficha_explica_a_montagem(self):
        html = self._html()
        self.assertIn("Por que essa ficha", html)
        self.assertIn("Séries desta sessão, por músculo", html)
        self.assertIn(self.plano.get_split_display(), html)
        self.assertIn("detalhes-do-programa", html, "o resto continua no painel")

    def test_o_selo_principal_explica_o_que_significa(self):
        html = self._html()
        self.assertIn("ficha-item__papel", html)
        self.assertIn("abre o grupo", html)

    # ----------------------------------------------------------- o desktop

    def test_o_desktop_tem_duas_colunas_so_nesta_tela(self):
        html = self._html()
        self.assertIn("ficha-layout", html)
        self.assertIn('class="tela-ficha"', html)
        self.assertIn(".tela-ficha { --max:", CSS)
        self.assertIn(".split.ficha-layout {", CSS)
        # E o resto do app continua em uma coluna.
        self.assertIn("/* Uma coluna, em toda largura de tela.", CSS)

    def test_a_ficha_continua_sem_video_sem_cronometro_e_sem_campo_de_carga(self):
        """A régua de 10/09/2026: a ficha é preparação, a execução é a
        tela de quem já escolheu. A miniatura é uma FOTO, não um player."""
        html = self._html()
        for proibido in ("<iframe", "data-clipe", "data-drawer", 'name="weight_kg"', "data-descanso", "data-demo"):
            self.assertNotIn(proibido, html, proibido)
