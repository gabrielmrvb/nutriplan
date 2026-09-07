# -*- coding: utf-8 -*-
"""A lista de hoje é o PLANO; a execução tem tela própria.

A tela de treino renderizava, para cada exercício de hoje, o cartão completo:
sanfona, botão de vídeo, chips de músculo, dica e formulário de carga. Oito
exercícios davam oito cópias da experiência de execução numa tela cuja
pergunta é outra — "o que eu vou fazer hoje?" —, e nenhuma das oito unidades
pesava mais que as outras.

Quem executa é `workouts:now`, que já resolve exercício da vez, série da vez,
carga e descanso no servidor, e é para onde o botão do hero leva.

Estes testes guardam a separação. Sem eles, a próxima pessoa que quiser
"mostrar mais informação na lista" traz a execução de volta e a tela volta a
ter quatro mil pixels.
"""
import re
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.tests import create_user, dias_incluindo_hoje


class ALinhaDeHojeSubstituiOCartaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Sem o catálogo, `create_routine` estoura por falta de divisão e o
        # teste reprova por fixture em vez de por composição.
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(
            email="lista-de-hoje@exemplo.com", weekdays=dias_incluindo_hoje(5)
        )
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.plano = services.get_active_routine(self.pessoa)
        hoje = timezone.localdate().weekday()
        self.sessao = next(
            s for s in self.plano.sessions.all() if s.weekday == hoje
        )

    def _html(self):
        return self.client.get(reverse("workouts:routine")).content.decode()

    def _lista_de_hoje(self, html):
        """Só a lista de hoje — a ficha da semana vem depois dela."""
        return html.split('class="linha-ex-lista', 1)[1].split("</ol>", 1)[0]

    def test_cada_exercicio_de_hoje_e_uma_linha(self):
        html = self._html()

        linhas = re.findall(r'class="linha-ex[ "]', html)

        self.assertEqual(len(linhas), self.sessao.exercises.count())

    def test_a_linha_diz_ordem_nome_grupo_e_prescricao(self):
        """Ela responde "o que eu vou fazer", e nada além disso. Se um dia
        precisar de mais, a pergunta provavelmente é de execução — e execução
        tem tela."""
        lista = self._lista_de_hoje(self._html())
        item = self.sessao.exercises.first()

        self.assertIn("linha-ex__ordem", lista)
        self.assertIn(item.exercise.name, lista)
        self.assertIn(item.exercise.get_muscle_group_display(), lista)
        self.assertIn(str(item.sets), lista)

    def test_a_execucao_NAO_esta_na_lista_de_hoje(self):
        """O CONTROLE DA RECOMPOSIÇÃO.

        Formulário de carga, chips de músculo e dica são execução, e execução
        mora em `workouts:now`. Se qualquer um voltar para cá, a tela volta a
        ser oito cópias da mesma experiência.
        """
        lista = self._lista_de_hoje(self._html())

        self.assertNotIn("registro__carga", lista)
        self.assertNotIn("registro__salvar", lista)
        self.assertNotIn("exercise__musculos", lista)
        self.assertNotIn("exercise__dica", lista)
        self.assertNotIn("<details", lista)

    def test_o_toque_na_linha_abre_o_video_daquele_exercicio(self):
        """A única pergunta que a lista não responde por escrito é "como é o
        movimento?" — e o drawer já existe para isso."""
        lista = self._lista_de_hoje(self._html())
        item = self.sessao.exercises.first()

        self.assertIn("data-ver", lista)
        # Pelo ID do vídeo, e não pela URL inteira: o template escapa `&` como
        # `&amp;`, então comparar a URL crua acusa divergência que não existe.
        identificador = item.exercise.video_embed_url.split("/embed/")[1].split("?")[0]
        self.assertIn(identificador, lista)
        self.assertIn(item.exercise.name, lista)

    def test_a_linha_concluida_diz_isso_em_TEXTO_e_nao_so_em_cor(self):
        """Estado por cor sozinho não serve a quem não distingue verde de
        cinza. A prescrição troca para "N de M séries" no mesmo momento em que
        o número vira tique."""
        item = self.sessao.exercises.first()
        for n in range(1, item.sets + 1):
            services.record_load(
                self.pessoa, item.exercise, Decimal("40"), set_number=n
            )

        lista = self._lista_de_hoje(self._html())

        self.assertIn("linha-ex--feito", lista)
        self.assertIn("%d de %d séries" % (item.sets, item.sets), lista)

    def test_o_botao_do_hero_leva_para_a_execucao(self):
        """A lista não executa, então tem de haver uma porta — e é uma só."""
        html = self._html()

        self.assertIn(reverse("workouts:now"), html)


class AFichaDaSemanaContinuaSendoSanfonaTests(TestCase):
    """A recomposição valeu para HOJE, e só para hoje.

    A ficha da semana responde outra pergunta — "o que tem na terça?" — e ali
    o cartão completo continua certo: ele nasce fechado, então não custa
    altura, e quem abre quer justamente o detalhe.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(
            email="ficha-da-semana@exemplo.com", weekdays=dias_incluindo_hoje(5)
        )
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def test_os_outros_dias_continuam_com_o_cartao_completo(self):
        html = self.client.get(reverse("workouts:routine")).content.decode()
        semana = html.split('<details class="card ficha"', 1)[1]

        self.assertIn('<summary class="exercise__head"', semana)
        self.assertIn("registro__carga", semana)
        self.assertIn("exercise__musculos", semana)
