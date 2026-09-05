# -*- coding: utf-8 -*-
"""A Home organiza pela área que a pessoa escolheu — e só organiza.

Três promessas, e elas se contradizem se alguém errar uma:

**Ordem, nunca visibilidade.** Nenhuma seção sai da página por não ser a área
principal. Esconder o que não foi marcado é a simplificação que transformaria
personalização em prisão, e é a mesma que `NenhumPilarFicaEscondidoTests` já
proíbe nas rotas.

**Urgência vence preferência.** O cartão AGORA é o primeiro bloco da tela e
nada o move. Refeição vencida e treino em andamento têm hora marcada, e a hora
passa; a área preferida continua verdadeira amanhã.

**Sem declaração, sem personalização.** Quem nunca respondeu vê a Home de
antes desta campanha. Uso não é intenção declarada — é o que a migration 0024
pagou para aprender, e o que esta tela não pode desfazer inferindo área de
histórico, peso, treino, água ou frequência.
"""
import re
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from accounts.models import (
    CAMPO_DO_PILAR,
    Pilar,
    Profile,
    User,
    WeightEntry,
)
from plans.models import HydrationLog
from accounts.tests import STEP1, STEP2, STEP3, STEP4, STEP5, step_url

#: Os marcadores de cada seção da Home, ancorados na CLASSE e não no texto.
#: Texto visível muda com a cópia; classe é contrato de estrutura. E ancorar no
#: texto aqui seria pior que o normal: "Hidratação" e "Corrida" aparecem também
#: no mapa de áreas, em toda página do app.
SECOES = {
    "agora": 'class="card agora-card',
    "refeicoes": 'class="refeicoes',
    "agua": 'id="hidratacao"',
    "ofensiva": 'class="ofensiva ',
    "painel": 'class="card today-hero"',
}


class BaseDaHome(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def pessoa(self, email="home@exemplo.com", interesses=(), principal=""):
        """Nasce do wizard: a Home exige plano, e plano nasce do onboarding."""
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        self.client.force_login(user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)
        self.client.post(
            step_url(6),
            {
                "interesses": list(interesses) or ["dieta"],
                "prioridade": principal or "dieta",
            },
        )
        if not interesses:
            # O legado: terminou o onboarding antes de a pergunta existir. É o
            # estado que a migration 0024 deixou, e não um perfil pela metade.
            Profile.objects.filter(user=user).update(
                prioridade="", **{campo: False for campo in CAMPO_DO_PILAR.values()}
            )
        return user

    def home(self):
        resposta = self.client.get(reverse("plans:today"))
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode()

    def posicoes(self, html):
        """Onde cada seção começa, em caracteres. Ausente vira `None`."""
        return {
            nome: (html.index(marca) if marca in html else None)
            for nome, marca in SECOES.items()
        }


class NadaSomeDaHomeTests(BaseDaHome):
    def test_as_secoes_continuam_todas_la_para_cada_um_dos_cinco(self):
        """A promessa central da campanha, varrida pelos cinco pilares."""
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.pessoa(
                    email="tudo-%s@exemplo.com" % pilar.value,
                    interesses=(pilar.value,),
                    principal=pilar.value,
                )
                posicoes = self.posicoes(self.home())
                for nome, onde in posicoes.items():
                    self.assertIsNotNone(onde, "%s sumiu com prioridade %s" % (nome, pilar))

    def test_quem_nao_declarou_ve_a_home_de_sempre(self):
        """Sem declaração, sem personalização — e "sem" é literal: nenhum selo,
        nenhum cartão de área, nada."""
        self.pessoa("legado@exemplo.com")

        html = self.home()

        self.assertNotIn("sua área", html)
        self.assertNotIn("area-promovida", html)
        self.assertNotIn("is-prioritario", html)

    def test_a_home_neutra_e_a_mesma_de_antes_da_campanha(self):
        """Controle mais forte que o de cima: a ORDEM das seções de quem não
        declarou tem de ser a canônica, e não uma ordem nova que por acaso
        começa igual."""
        self.pessoa("legado2@exemplo.com")

        posicoes = self.posicoes(self.home())

        self.assertEqual(
            [n for n, _ in sorted(posicoes.items(), key=lambda par: par[1])],
            ["agora", "refeicoes", "agua", "ofensiva", "painel"],
        )


class AUrgenciaVenceAPreferenciaTests(BaseDaHome):
    def test_o_agora_e_o_primeiro_bloco_com_qualquer_prioridade(self):
        """A regra que impede a personalização de virar desatenção."""
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.pessoa(
                    email="urgencia-%s@exemplo.com" % pilar.value,
                    interesses=(pilar.value,),
                    principal=pilar.value,
                )
                posicoes = self.posicoes(self.home())
                primeiro = min(posicoes.values())
                self.assertEqual(
                    posicoes["agora"], primeiro,
                    "a prioridade %s passou na frente do AGORA" % pilar,
                )

    def test_a_area_promovida_nasce_depois_do_agora(self):
        self.pessoa("depois@exemplo.com", ("corrida",), "corrida")

        html = self.home()

        self.assertLess(html.index(SECOES["agora"]), html.index("area-promovida"))


class AAreaPrincipalSobeTests(BaseDaHome):
    def test_hidratacao_sobe_para_cima_das_refeicoes(self):
        self.pessoa("agua@exemplo.com", ("hidratacao", "dieta"), "hidratacao")

        posicoes = self.posicoes(self.home())

        self.assertLess(posicoes["agua"], posicoes["refeicoes"])

    def test_controle_positivo_sem_hidratacao_a_agua_fica_embaixo(self):
        """Sem ele, uma tela que sempre pusesse a água em cima passaria."""
        self.pessoa("agua-nao@exemplo.com", ("dieta",), "dieta")

        posicoes = self.posicoes(self.home())

        self.assertGreater(posicoes["agua"], posicoes["refeicoes"])

    def test_o_cartao_de_agua_aparece_UMA_vez(self):
        """O `id` é âncora de link e o cartão tem formulário: emitir duas vezes
        produziria `id` ambíguo e dois formulários com os mesmos nomes."""
        for principal in ("hidratacao", "dieta"):
            with self.subTest(principal=principal):
                self.pessoa(
                    email="uma-vez-%s@exemplo.com" % principal,
                    interesses=(principal,),
                    principal=principal,
                )
                html = self.home()
                self.assertEqual(html.count('id="hidratacao"'), 1)

    def test_treino_corrida_e_progresso_ganham_o_cartao_da_area(self):
        """Os três não têm seção própria na Home — o cartão é a porta deles."""
        portas = {
            "treino": reverse("workouts:routine"),
            "corrida": reverse("workouts:corridas"),
            "progresso": reverse("plans:history"),
        }
        for pilar, porta in portas.items():
            with self.subTest(pilar=pilar):
                self.pessoa(
                    email="porta-%s@exemplo.com" % pilar,
                    interesses=(pilar,),
                    principal=pilar,
                )
                html = self.home()
                # Recorta pela ABERTURA da seção, e não pela string
                # `area-promovida` crua: ela também é o prefixo de
                # `.area-promovida__fato`, e o recorte ingênuo terminava
                # ANTES do link. Foi este teste que pegou.
                promovido = html.split('class="card area-promovida', 1)[1]
                promovido = promovido.split("</section>", 1)[0]
                self.assertIn('href="%s"' % porta, promovido)

    def test_dieta_nao_ganha_cartao_porque_ja_esta_em_cima(self):
        """Promover a dieta seria mover um bloco para onde ele já está. O que
        ela ganha é o selo — e sem ele quem escolheu Alimentação veria a tela
        de quem não escolheu nada."""
        self.pessoa("dieta@exemplo.com", ("dieta",), "dieta")

        html = self.home()

        self.assertNotIn("area-promovida", html)
        self.assertIn("is-prioritario", html)
        self.assertIn("sua área", html)


class OSeloApareceUmaVezSoTests(BaseDaHome):
    def test_um_selo_por_tela_em_cada_pilar(self):
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.pessoa(
                    email="selo-%s@exemplo.com" % pilar.value,
                    interesses=(pilar.value,),
                    principal=pilar.value,
                )
                html = self.home()
                self.assertEqual(html.count(">sua área<"), 1, pilar.value)

    def test_a_marca_de_prioridade_e_escrita_pelo_servidor_e_nao_por_has(self):
        """`:has()` estrutural já derrubou a navegação uma vez: o navegador
        descarta a regra inteira quando não suporta."""
        css = (
            __import__("pathlib").Path(__file__).resolve().parent.parent
            / "static" / "css" / "app.css"
        ).read_text(encoding="utf-8")
        regra = re.search(r"\n\.is-prioritario \{[^}]*\}", css)

        self.assertIsNotNone(regra, "a regra da promoção sumiu do CSS")
        self.assertNotIn(":has(", regra.group(0))


class ANenhumaInferenciaTests(BaseDaHome):
    def test_historico_cheio_nao_produz_area_promovida(self):
        """O teste que fecha a porta da heurística.

        Esta pessoa tem plano, refeições marcadas e água registrada — uso de
        sobra. Se algum dia alguém "melhorar" a Home inferindo a área pelo que
        a pessoa mais usa, este teste fica vermelho.
        """
        self.pessoa("usa-muito@exemplo.com")
        self.client.post(reverse("plans:log_hydration"), {"ml": 500})

        html = self.home()

        self.assertNotIn("area-promovida", html)
        self.assertNotIn("is-prioritario", html)


class OCTADoProgressoLevaAAlgumLugarTests(BaseDaHome):
    """O botão do cartão AGORA para o pilar Progresso apontava para o vazio.

    `plans/agora.py` devolve `url="#pesar"`, e não existia `id="pesar"` em
    lugar nenhum do projeto — a faixa de pesagem tinha só a CLASSE. Para quem
    declarou Progresso como área principal, o botão "Registrar peso" — que é a
    ação principal do dia inteiro, porque o ramo fica de pé até a pessoa se
    pesar — não rolava, não abria e não navegava. Só acrescentava `#pesar` à
    barra de endereço.

    O teste que existia prendia a STRING (`assertEqual(acao.url, "#pesar")`) e
    nunca conferia que o destino existisse: ele TRAVAVA o defeito. Foi uma
    revisão adversarial independente que encontrou.
    """

    def dia_de_pesagem(self, user):
        """Um dia sem refeição vencida e com a semana sem pesagem.

        As refeições do plano são marcadas como feitas para tirar a urgência do
        caminho — não para escondê-la: urgência vence preferência, e é por isso
        que só com o dia limpo o ramo do Progresso chega ao topo.
        """
        from plans.models import MealLog, MealStatus
        from plans.services import get_active_plan

        # A primeira visita é o que CRIA o plano — `PlanRequiredMixin` monta na
        # hora. Sem ela `get_active_plan` devolve `None`, e o teste morreria
        # montando o cenário em vez de medindo o que veio medir.
        self.client.get(reverse("plans:today"))
        plano = get_active_plan(user)
        self.assertIsNotNone(plano)

        # O passo 2 do wizard grava o peso de HOJE, e com ele `convidar_a_pesar`
        # é falso — a faixa nem renderiza. A pesagem é EMPURRADA para trás, e
        # não apagada: sem nenhum peso o perfil fica incompleto e a Home
        # redireciona para o wizard, que foi o que este teste fez na primeira
        # tentativa (302 em vez de 200).
        WeightEntry.objects.filter(user=user).update(
            date=timezone.localdate() - timedelta(days=10)
        )
        hoje = timezone.localdate()
        for slot in plano.slots.all():
            MealLog.objects.update_or_create(
                user=user, slot=slot, date=hoje,
                defaults={"status": MealStatus.DONE},
            )

    def test_a_ancora_do_cta_existe_na_pagina(self):
        user = self.pessoa("pesar@exemplo.com", ("progresso",), "progresso")
        self.dia_de_pesagem(user)

        html = self.home()

        self.assertIn('id="pesar"', html)

    def test_quando_o_topo_pede_o_peso_a_faixa_ja_chega_aberta(self):
        """Rolar até um `<details>` fechado ainda não mostra o campo — metade
        do conserto seria conserto nenhum."""
        user = self.pessoa("pesar2@exemplo.com", ("progresso",), "progresso")
        self.dia_de_pesagem(user)
        HydrationLog.objects.update_or_create(
            user=user, date=timezone.localdate(), defaults={"ml": 10000}
        )

        html = self.home()
        faixa = html.split('id="pesar"', 1)[1].split(">", 1)[0]

        # O cartão do topo tem de estar PEDINDO o peso — sem isso o teste
        # provaria só que a faixa abre sozinha, que não é o contrato.
        self.assertIn("agora-card--pesagem", html)
        self.assertIn("open", faixa)

    def test_sem_o_pedido_no_topo_a_faixa_continua_fechada(self):
        """Controle positivo do de cima: se ela abrisse sempre, o teste
        anterior passaria sem que o conserto existisse."""
        user = self.pessoa("pesar3@exemplo.com", ("dieta",), "dieta")
        self.dia_de_pesagem(user)

        html = self.home()

        self.assertNotIn("agora-card--pesagem", html)
        if 'id="pesar"' in html:
            faixa = html.split('id="pesar"', 1)[1].split(">", 1)[0]
            self.assertNotIn("open", faixa)
