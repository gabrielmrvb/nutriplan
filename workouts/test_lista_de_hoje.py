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

        # OS MARCADORES ACOMPANHARAM A MUDANÇA. `registro__salvar`,
        # `exercise__musculos` e `exercise__dica` saíram do CSS e do
        # repositório junto com o cartão; procurá-los aqui seria asserção de
        # ausência sobre string que não existe em lugar nenhum — verde para
        # sempre, medindo nada. Os quatro abaixo são emitidos pela execução,
        # e é isso que os torna uma prova de separação.
        self.assertNotIn("registro__carga", html)
        self.assertNotIn('name="weight_kg"', html)
        self.assertNotIn("data-passo", html)
        self.assertNotIn("data-descanso", html)

    def test_o_video_continua_alcancavel_a_PARTIR_da_ficha(self):
        """O acesso ao vídeo não podia sumir junto com a lista.

        ELE MUDOU DE TELA DUAS VEZES. Saiu da principal para a ficha, e da
        ficha para a EXECUÇÃO — que é onde a pergunta "como é o movimento?" é
        feita de verdade: com o aparelho na frente, não na hora de decidir se
        treina.

        A régua é o CAMINHO, e não o endereço: a ficha precisa oferecer a porta
        de cada exercício, e a porta precisa entregar o vídeo daquele exercício.
        Testar só a existência da página de execução deixaria a ficha livre para
        perder os links, que foi exatamente o defeito de 09/09/2026 — nove
        botões de vídeo apontando para uma gaveta que a página não tinha.
        """
        item = self.sessao.exercises.select_related("exercise").first()
        porta = "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id)

        ficha = self.client.get(
            reverse("workouts:ficha", args=[self.sessao.pk])
        ).content.decode()
        self.assertIn(porta, ficha)
        self.assertIn(item.exercise.name, ficha)

        execucao = self.client.get(porta).content.decode()
        # Pelo ID do vídeo, e não pela URL inteira: o template escapa `&` como
        # `&amp;`, então comparar a URL crua acusa divergência que não existe.
        identificador = item.exercise.video_embed_url.split("/embed/")[1].split("?")[0]
        self.assertIn(identificador, execucao)

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

    def test_o_botao_do_hero_leva_para_a_ficha(self):
        """A lista não executa, então tem de haver uma porta — e é uma só.

        A PORTA MUDOU DE DESTINO. Ela apontava para `/treino/agora/`, que
        escolhia sozinha o primeiro pendente; hoje abre a ficha do dia, e é
        dela que se escolhe o exercício. O painel deixou de ter qualquer link
        direto para a execução: quem chega ali ainda não decidiu o que fazer.
        """
        html = self._html()

        self.assertIn(reverse("workouts:ficha", args=[self.sessao.pk]), html)
        self.assertNotIn(reverse("workouts:now"), sem_scripts(html))


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
        """A sessão de HOJE, e a precisão passou a importar.

        Ela devolvia `sessions.first()`, qualquer uma — servia enquanto a ficha
        era só leitura. A execução recusa exercício que não é do treino de hoje
        (`ExercicioForaDaSessao` -> 404), então pedir a execução de um exercício
        de terça numa quinta deixaria este arquivo vermelho por regra de
        segurança, e não por composição de tela.
        """
        from workouts.models import TrainingPlan

        plano = TrainingPlan.objects.filter(user=self.pessoa, is_active=True).first()
        hoje = timezone.localdate().weekday()
        return plano.sessions.get(weekday=hoje)

    def test_o_detalhe_completo_continua_inteiro_NA_EXECUCAO(self):
        """O detalhe continua inteiro — uma página adiante.

        ELE MUDOU DE ENDEREÇO PELA SEGUNDA VEZ, e a asserção acompanha. Era o
        `<summary class="exercise__head">` da tela principal; virou o mesmo
        cartão dentro da ficha; e agora é a tela de execução, que mostra UM
        exercício por vez em vez de trinta abertos ao mesmo tempo.

        O que este teste guarda não mudou desde a reversão de 09/09/2026: o
        registro de série, a carga, as repetições, o descanso e o histórico
        precisam existir e ser alcançáveis. O que não pode voltar é a tentativa
        de mostrar tudo isso trinta vezes numa tela de planejamento.
        """
        sessao = self._uma_sessao()
        item = sessao.exercises.first()

        # A ficha não executa; ela oferece a porta.
        ficha = self.client.get(
            reverse("workouts:ficha", args=[sessao.pk])
        ).content.decode()
        self.assertIn("ficha-item__nome", ficha)

        execucao = self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id)
        ).content.decode()

        self.assertIn("registro__carga", execucao)
        self.assertIn('name="weight_kg"', execucao)
        self.assertIn('name="reps"', execucao)
        self.assertIn("data-descanso", execucao)

    def test_a_tela_principal_nao_pre_monta_os_formularios(self):
        """A outra metade: o paredão não pode voltar.

        Sem esta asserção, alguém devolveria a execução à tela principal e o
        teste acima continuaria verde — ele só olha para a execução.

        E ela vem com CONTROLE POSITIVO, porque asserção de ausência é o lugar
        onde este repositório mais erra: se `registro__carga` for renomeado, o
        `assertNotIn` fica verde para sempre. A execução tem de trazê-lo.
        """
        from workouts.tests import sem_scripts as _sem

        sessao = self._uma_sessao()
        painel = _sem(self.client.get(reverse("workouts:routine")).content.decode())

        self.assertNotIn("registro__carga", painel)
        self.assertNotIn("ficha-item__nome", painel)
        self.assertNotIn("<iframe", painel)

        execucao = self.client.get(reverse("workouts:now")).content.decode()
        self.assertIn(
            "registro__carga",
            execucao,
            "o marcador mudou de nome — a asserção de ausência acima parou de "
            "medir alguma coisa",
        )

    def test_a_ficha_nao_tem_botao_de_video_NEM_gaveta(self):
        """A RELAÇÃO CONTINUA SENDO A RÉGUA, e ela é satisfeita do outro lado.

        A versão anterior deste teste guardava a regressão de 09/09/2026: o
        cartão do exercício trazia um botão `data-clipe`, quem o abria era o
        `<dialog data-drawer>`, e quando os cartões mudaram para a ficha a
        página nasceu com nove botões e nenhuma gaveta. Medido: `data-clipe: 9`,
        `data-drawer: 0` — botões mortos, e nenhum teste pegou porque todos
        liam a tela antiga.

        A régua nunca foi "tem gaveta": era "botão que abre precisa de gaveta
        que abre". A ficha deixou de ter botão — o vídeo mudou para a execução,
        onde nasce inline e não precisa de diálogo nenhum —, então a relação é
        satisfeita com ZERO dos dois. É a versão forte da mesma frase, e é por
        isso que ela é medida nas duas pontas.
        """
        sessao = self._uma_sessao()

        html = self.client.get(
            reverse("workouts:ficha", args=[sessao.pk])
        ).content.decode()

        self.assertEqual(html.count("data-clipe"), 0)
        self.assertEqual(html.count("data-drawer"), 0)
        self.assertEqual(html.count('class="drawer"'), 0)
        self.assertEqual(html.count("<iframe"), 0)

        # A OUTRA PONTA: a demonstração existe, e existe onde se treina.
        item = sessao.exercises.first()
        execucao = self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id)
        ).content.decode()
        self.assertEqual(execucao.count("<iframe"), 1)

    def test_no_maximo_um_player_por_tela_do_treino(self):
        """Dois players na mesma tela seriam duas conexões e dois áudios.

        Era "um `<dialog class="drawer">` por página", e o motivo continua
        valendo palavra por palavra: dois diálogos seriam dois focos presos
        disputando o mesmo toque. O diálogo saiu, e o invariante ficou mais
        simples de dizer e mais fácil de conferir — o painel e a ficha não
        montam player nenhum, e a execução monta exatamente um, do exercício
        que está aberto.
        """
        sessao = self._uma_sessao()
        esperado = {
            reverse("workouts:routine"): 0,
            reverse("workouts:ficha", args=[sessao.pk]): 0,
            reverse("workouts:now"): 1,
        }
        for rota, quantos in esperado.items():
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                self.assertEqual(html.count("<iframe"), quantos)

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
