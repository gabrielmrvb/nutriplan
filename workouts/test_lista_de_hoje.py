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
from workouts.tests import create_user, dias_incluindo_hoje, sem_scripts


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

    def _desenhado(self, html):
        """A página SEM os `<script>`.

        Os scripts saem porque o seletor do JavaScript e o marcador do HTML são
        a mesma string neste projeto — `registro__carga` aparece dentro de uma
        função que mexe no campo, e uma asserção de ausência casaria com ela.
        É a armadilha que o `CLAUDE.md` registra como recorrente, e ela pegou
        a primeira versão destes testes.

        A régua é a página inteira e não um recorte do cartão de hoje: a ação
        "Ver ficha" fica logo DEPOIS do `</section>` do cartão, e um recorte
        que parasse ali reprovaria uma tela correta.
        """
        return sem_scripts(html)

    def test_o_bloco_de_hoje_nao_lista_mais_os_exercicios(self):
        """DECISÃO 2: o paredão inicial sai.

        A lista sempre aberta duplicava a ficha — os mesmos exercícios aqui e
        de novo em "Seu programa" — e empurrava para baixo a única coisa que a
        tela precisa responder: o que fazer agora.
        """
        html = sem_scripts(self._html())

        self.assertNotIn('class="linha-ex-lista', html)

    def test_no_lugar_dela_ha_uma_acao_que_diz_o_que_abre(self):
        """"Ver ficha" pelado obriga a tocar para descobrir o tamanho.

        O rótulo carrega a letra do treino e a contagem real de exercícios.
        """
        bloco = self._desenhado(self._html())

        self.assertIn("Ver ficha do Treino %s" % self.sessao.label, bloco)
        self.assertIn(str(self.sessao.exercises.count()), bloco)
        self.assertIn(reverse("workouts:ficha", args=[self.sessao.pk]), bloco)

    def test_a_execucao_NAO_esta_na_tela_principal(self):
        """O CONTROLE DA RECOMPOSIÇÃO, agora sobre a tela inteira.

        Antes esta asserção valia só dentro da lista de hoje, porque a ficha da
        semana logo abaixo carregava a execução inteira de propósito. Com a
        ficha em rota própria, a regra passa a valer para a página toda — que é
        a versão forte da mesma ideia.
        """
        html = sem_scripts(self._html())

        self.assertNotIn("registro__carga", html)
        self.assertNotIn("registro__salvar", html)
        self.assertNotIn("exercise__musculos", html)
        self.assertNotIn("exercise__dica", html)

    def test_o_video_continua_alcancavel_pela_ficha(self):
        """O acesso ao vídeo não podia sumir junto com a lista.

        Ele saiu da tela principal e mora na ficha, que é onde a pergunta "como
        é o movimento?" é feita — na hora de conferir o treino, não na hora de
        decidir se treina.
        """
        item = self.sessao.exercises.first()

        html = self.client.get(
            reverse("workouts:ficha", args=[self.sessao.pk])
        ).content.decode()

        self.assertIn("data-ver", html)
        # Pelo ID do vídeo, e não pela URL inteira: o template escapa `&` como
        # `&amp;`, então comparar a URL crua acusa divergência que não existe.
        identificador = item.exercise.video_embed_url.split("/embed/")[1].split("?")[0]
        self.assertIn(identificador, html)
        self.assertIn(item.exercise.name, html)

    def test_o_progresso_de_hoje_continua_em_TEXTO_e_nao_so_em_cor(self):
        """Estado por cor sozinho não serve a quem não distingue verde.

        O progresso saiu da linha do exercício e ficou no cartão de hoje, que é
        onde ele responde a pergunta certa: quanto do treino já saiu.
        """
        item = self.sessao.exercises.first()
        for n in range(1, item.sets + 1):
            services.record_load(
                self.pessoa, item.exercise, Decimal("40"), set_number=n
            )

        bloco = self._desenhado(self._html())

        self.assertIn("exerc", bloco)
        self.assertIn("1", bloco)

    def test_o_botao_do_hero_leva_para_a_execucao(self):
        """A lista não executa, então tem de haver uma porta — e é uma só."""
        html = self._html()

        self.assertIn(reverse("workouts:now"), html)


class AFichaCompletaContinuaExistindoTests(TestCase):
    """O detalhe da ficha não pode sumir — mas ele não precisa estar AQUI.

    ESTA GUARDA FOI RE-MIRADA, E O MOTIVO IMPORTA.

    Ela nasceu de uma reversão: em 09/09/2026 alguém trocou o cartão completo
    da semana pela linha compacta de hoje, mirando o tamanho da página, e
    aquilo APAGOU registro de série, carga, repetições, descanso, progressão e
    histórico. Vinte e um testes reprovaram e estavam certos. A guarda passou a
    exigir que o cartão completo estivesse dentro da sanfona da tela.

    O que ela protege é o DETALHE EXISTIR e ser alcançável. O "dentro da
    sanfona" era o único jeito de isso ser verdade enquanto não havia outro
    lugar para ele. Agora há: `workouts:ficha` é uma página por sessão, e ela
    carrega tudo o que a sanfona carregava.

    Então a asserção muda de endereço, não de assunto — e ganha a metade que
    faltava: a tela principal NÃO pode pré-montar os formulários, que é o
    paredão que a auditoria mediu em 259 kB e 141 botões.
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

    def _uma_sessao(self):
        from workouts.models import TrainingPlan

        plano = TrainingPlan.objects.filter(user=self.pessoa, is_active=True).first()
        return plano.sessions.first()

    def test_a_ficha_da_sessao_carrega_o_cartao_completo(self):
        """O detalhe continua inteiro — na página dele."""
        sessao = self._uma_sessao()

        html = self.client.get(
            reverse("workouts:ficha", args=[sessao.pk])
        ).content.decode()

        self.assertIn('<summary class="exercise__head"', html)
        self.assertIn("registro__carga", html)
        self.assertIn("exercise__musculos", html)

    def test_a_tela_principal_nao_pre_monta_os_formularios(self):
        """A outra metade: o paredão não pode voltar.

        Sem esta asserção, alguém devolveria o cartão completo à tela principal
        e o teste acima continuaria verde — ele só olha para a ficha.
        """
        from workouts.tests import sem_scripts as _sem

        html = _sem(self.client.get(reverse("workouts:routine")).content.decode())

        self.assertNotIn('<summary class="exercise__head"', html)
        self.assertNotIn("registro__carga", html)

    def test_a_ficha_tem_o_drawer_que_os_botoes_dela_abrem(self):
        """A REGRESSÃO QUE ESTA MISSÃO CRIOU E ESTE TESTE PEGA.

        O cartão do exercício traz um botão `data-clipe`, e quem o abre é o
        `<dialog data-drawer>`. O drawer morava dentro de `routine.html` porque
        a tela de treino era o único lugar que desenhava cartão; quando os
        cartões mudaram para a ficha, a página nasceu com nove botões de vídeo
        e nenhum drawer. Medido antes da correção: `data-clipe: 9`,
        `data-drawer: 0` — botões mortos, e nenhum teste existente pegou porque
        todos liam a tela antiga.

        A régua é a RELAÇÃO entre os dois, e não a presença de cada um: uma
        página sem botão nenhum não precisa de drawer, e é isso que a condição
        abaixo diz.
        """
        sessao = self._uma_sessao()

        html = self.client.get(
            reverse("workouts:ficha", args=[sessao.pk])
        ).content.decode()

        self.assertGreater(html.count("data-clipe"), 0, "a ficha ficou sem vídeo")
        # `class="drawer"` e não `<dialog`: o script do próprio drawer discute
        # `<dialog>` em cinco comentários, e eles viajam no HTML. Contar a tag
        # devolvia 6. É a armadilha que o `CLAUDE.md` registra — o seletor e o
        # texto procurado são a mesma string.
        self.assertEqual(html.count('class="drawer"'), 1)
        self.assertIn("data-drawer", html)

    def test_um_drawer_por_pagina_e_nao_dois(self):
        """A extração para parcial não podia duplicar o diálogo.

        Dois `<dialog>` na mesma página seriam dois focos presos disputando o
        mesmo toque — e o `CLAUDE.md` registra "um drawer por página" como
        decisão desde que o convite de instalação pagou por ela.
        """
        for rota in (
            reverse("workouts:routine"),
            reverse("workouts:ficha", args=[self._uma_sessao().pk]),
        ):
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                self.assertEqual(html.count('class="drawer"'), 1)

    def test_a_tela_principal_leva_para_todas_as_fichas(self):
        """Alcançável, e não só existente.

        Um detalhe que existe numa rota que ninguém alcança foi removido na
        prática. A lista da semana tem de linkar cada sessão — inclusive a de
        hoje, que antes era omitida.
        """
        from workouts.models import TrainingPlan

        plano = TrainingPlan.objects.filter(user=self.pessoa, is_active=True).first()
        html = self.client.get(reverse("workouts:routine")).content.decode()

        for sessao in plano.sessions.all():
            with self.subTest(sessao=sessao.label):
                self.assertIn(
                    reverse("workouts:ficha", args=[sessao.pk]), html
                )
