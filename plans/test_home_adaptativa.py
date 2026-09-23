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
from accounts.tests import ETAPA2, ETAPA3, STEP1, step_url

#: Os marcadores de cada bloco da Home, ancorados na CLASSE e não no texto.
#: Texto visível muda com a cópia; classe é contrato de estrutura. E ancorar no
#: texto aqui seria pior que o normal: "Hidratação" e "Corrida" aparecem também
#: no mapa de áreas, em toda página do app.
#:
#: A LISTA ENCOLHEU EM 22/09/2026, e não por descuido: as refeições e o painel
#: de calorias saíram para `plans:alimentacao`, e a água deixou de ser uma
#: seção de meia tela para virar uma CÉLULA do painel. O que a Hoje tem hoje
#: são três blocos — o AGORA, o painel do dia e a ofensiva —, e é isso que a
#: tela orquestradora é.
SECOES = {
    "agora": 'class="card agora-card',
    "painel": 'class="painel"',
    "agua": 'id="hidratacao"',
    "ofensiva": 'class="ofensiva ',
}

#: Os cartões que TODA pessoa tem, declare ela o que declarar. Corrida e
#: Progresso são os dois opcionais (ver `plans.views.CARTOES_DECLARADOS`).
CARTOES_DE_TODOS = ("Alimentação", "Treino", "Hidratação")


def cartoes(html):
    """Os rótulos dos cartões do painel, na ordem em que a tela os escreve.

    O rótulo vem DEPOIS do `</svg>` do ícone: recortar `painel__rotulo">` até
    `</h3>` cru traria o SVG inteiro junto, e a comparação passaria a medir
    desenho.
    """
    painel = html.split('class="painel"', 1)[1]
    return [
        bloco.split("</svg>", 1)[1].split("</h3>", 1)[0].strip()
        for bloco in painel.split('class="painel__rotulo">')[1:]
    ]


class BaseDaHome(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def pessoa(self, email="home@exemplo.com", interesses=(), principal=""):
        """Nasce do wizard: a Home exige plano, e plano nasce do onboarding."""
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        self.client.force_login(user)
        for etapa, dados in ((1, STEP1), (2, ETAPA2)):
            self.client.post(step_url(etapa), dados)
        self.client.post(
            step_url(3),
            {
                **ETAPA3,
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
    def test_os_blocos_continuam_todos_la_para_cada_um_dos_cinco(self):
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

    def test_os_tres_cartoes_do_dia_valem_para_todo_mundo(self):
        """Interesse ORGANIZA e não restringe, e este é o teste literal disso.

        Alimentação, Treino e Hidratação são o dia de qualquer pessoa — todo
        mundo come, treina (ou descansa, que é o plano) e bebe água. Nenhum
        dos três pode sumir por a pessoa ter declarado outra coisa, nem
        aparecer só para quem declarou.
        """
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.pessoa(
                    email="tres-%s@exemplo.com" % pilar.value,
                    interesses=(pilar.value,),
                    principal=pilar.value,
                )
                rotulos = cartoes(self.home())
                for rotulo in CARTOES_DE_TODOS:
                    self.assertIn(rotulo, rotulos, pilar.value)

    def test_corrida_e_progresso_entram_com_a_area_declarada(self):
        """Os dois opcionais, e o CONTROLE POSITIVO do de cima.

        Sem este teste, um painel que sempre mostrasse os cinco cartões
        passaria em tudo que está acima — e cobraria de quem não corre um
        cartão "Nenhuma ainda" em meia tela de celular.
        """
        self.pessoa("so-dieta@exemplo.com", ("dieta",), "dieta")
        rotulos = cartoes(self.home())
        self.assertNotIn("Corrida", rotulos)
        self.assertNotIn("Progresso", rotulos)

        self.pessoa("corre@exemplo.com", ("dieta", "corrida"), "dieta")
        self.assertIn("Corrida", cartoes(self.home()))

        self.pessoa("pesa@exemplo.com", ("dieta", "progresso"), "dieta")
        self.assertIn("Progresso", cartoes(self.home()))

    def test_quem_nao_declarou_ve_a_home_de_sempre(self):
        """Sem declaração, sem personalização — e "sem" é literal: nenhum selo,
        nenhum cartão de área, nada."""
        self.pessoa("legado@exemplo.com")

        html = self.home()

        self.assertNotIn("sua área", html)
        self.assertNotIn("is-prioritario", html)

    def test_a_home_neutra_e_a_ordem_canonica(self):
        """Controle mais forte que o de cima: a ORDEM de quem não declarou tem
        de ser a canônica, e não uma ordem nova que por acaso começa igual.

        A canônica é a de `accounts.models.Pilar`, e é ela que o painel segue
        quando ninguém escolheu nada. O que este teste guarda não é a lista em
        si: é que a Home de quem NÃO declarou prioridade não tenha
        personalização nenhuma.
        """
        self.pessoa("legado2@exemplo.com")

        html = self.home()
        posicoes = self.posicoes(html)

        self.assertEqual(list(CARTOES_DE_TODOS), cartoes(html))
        self.assertEqual(
            [n for n, _ in sorted(posicoes.items(), key=lambda par: par[1])],
            ["agora", "painel", "agua", "ofensiva"],
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

    def test_o_painel_inteiro_nasce_depois_do_agora(self):
        """Inclusive o cartão da área principal, que é o primeiro do painel.

        O destaque da preferência é a POSIÇÃO DENTRO da grade, e nunca a
        grade inteira passando na frente do que tem hora marcada.
        """
        self.pessoa("depois@exemplo.com", ("corrida",), "corrida")

        html = self.home()

        self.assertLess(html.index(SECOES["agora"]), html.index(SECOES["painel"]))
        self.assertEqual("Corrida", cartoes(html)[0])


class AAreaPrincipalSobeTests(BaseDaHome):
    """A área principal é o PRIMEIRO CARTÃO do painel — e só isso.

    Até 22/09/2026 a promoção movia SEÇÕES: a hidratação subia para cima das
    refeições, e treino, corrida e progresso ganhavam um cartão extra de meia
    tela. Com a Hoje orquestradora as cinco áreas já estão na mesma grade,
    com o mesmo peso visual, e promover é reordenar. É menos código e é uma
    promessa mais honesta: a área preferida aparece antes, não maior.
    """

    def test_a_area_principal_e_o_primeiro_cartao(self):
        """Varrido pelos cinco pilares: o que a pessoa elegeu abre o painel."""
        rotulo_de = {
            "dieta": "Alimentação",
            "treino": "Treino",
            "hidratacao": "Hidratação",
            "corrida": "Corrida",
            "progresso": "Progresso",
        }
        for pilar in Pilar:
            with self.subTest(pilar=pilar.value):
                self.pessoa(
                    email="primeiro-%s@exemplo.com" % pilar.value,
                    interesses=(pilar.value,),
                    principal=pilar.value,
                )
                self.assertEqual(rotulo_de[pilar.value], cartoes(self.home())[0])

    def test_controle_positivo_sem_declaracao_a_ordem_e_a_canonica(self):
        """Sem ele, um painel que sempre começasse por Alimentação passaria no
        de cima para o pilar `dieta` e ninguém veria."""
        self.pessoa("canonica@exemplo.com")

        self.assertEqual("Alimentação", cartoes(self.home())[0])

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

    def test_cada_cartao_leva_a_porta_da_sua_area(self):
        """O painel não é um resumo passivo: cada cartão tem a ação do dia.

        Sem isto, a Home voltaria a ser a tela que a auditoria mediu — o
        treino do dia como um travessão numa linha de 12px, sem porta.
        """
        # O prefixo, e não a rota exata: o cartão de Treino num dia de treino
        # aponta para a FICHA de hoje (`/treino/ficha/<pk>/`), e num dia de
        # descanso para a semana — as duas são a porta certa, e exigir uma
        # delas faria o teste depender do dia em que a suíte roda.
        portas = {
            "treino": reverse("workouts:routine"),
            "corrida": reverse("workouts:corridas"),
            "dieta": reverse("plans:alimentacao"),
        }
        for pilar, porta in portas.items():
            with self.subTest(pilar=pilar):
                self.pessoa(
                    email="porta-%s@exemplo.com" % pilar,
                    interesses=(pilar,),
                    principal=pilar,
                )
                html = self.home()
                # Recorta o PRIMEIRO cartão (o da área principal) e procura a
                # porta lá dentro: `href` solto passaria pelo mapa de áreas,
                # que escreve as cinco rotas em toda página do app.
                primeiro = html.split('class="painel__cartao', 1)[1]
                primeiro = primeiro.split("</section>", 1)[0]
                self.assertIn('href="%s' % porta, primeiro)


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
        # A regra mora junto do painel desde 22/09/2026: o cartao promovido
        # e uma celula da grade, e a marca dele e um fio de dentro.
        regra = re.search(r"\n\.painel__cartao\.is-prioritario \{[^}]*\}", css)

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

        self.assertNotIn("is-prioritario", html)
        self.assertNotIn("sua área", html)
        # E a ordem continua a canônica: inferir a área mexeria nela sem selo
        # nenhum, e o teste acima não veria.
        self.assertEqual(list(CARTOES_DE_TODOS), cartoes(html))


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

        # A etapa 1 do wizard grava o peso de HOJE, e com ele `convidar_a_pesar`
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


class OCartaoDaAreaTemAAcaoDoDiaTests(BaseDaHome):
    """A prioridade tem de MUDAR a Home de verdade (item 4 da missão de UX,
    22/09/2026): o cartão da área principal trazia um fato e um link de
    rodapé — e a pessoa lia a tela como "igual à de todo mundo".

    Com o painel, TODO cartão traz o fato do dia e a porta da área, e o da
    área principal ganha a posição e o selo. Estes testes medem o CONTEÚDO de
    cada célula: o número que responde a pergunta daquela área, e não um
    rótulo com um traço.
    """

    def _cartao(self, html, rotulo):
        """O corpo da célula daquela área.

        O rótulo é procurado no `<h3>`, e não no cartão inteiro: os nomes das
        áreas aparecem no texto de outros cartões (e o mapa de áreas escreve
        os cinco em toda página do app), e um recorte ingênuo devolveria o
        cartão errado com aparência de acerto.
        """
        for bloco in html.split('class="painel__cartao')[1:]:
            corpo = bloco.split("</section>", 1)[0]
            if rotulo in corpo.split("</h3>", 1)[0]:
                return corpo
        self.fail("cartão %s não está no painel" % rotulo)

    def test_treino_mostra_a_sessao_de_hoje_e_quantas_series_faltam(self):
        self.pessoa("acao-treino@exemplo.com", ("treino",), "treino")

        cartao = self._cartao(self.home(), "Treino")

        # a fixture treina seg/qua/sex e a suíte vive numa quarta: hoje tem treino
        self.assertRegex(cartao, r"<p class=\"painel__valor num\">\d+")
        self.assertIn("séries", cartao)
        self.assertRegex(cartao, r"\d+ exercícios?")
        self.assertIn('href="%s' % reverse("workouts:routine"), cartao)

    def test_no_dia_sem_treino_o_cartao_diz_descanso_e_qual_e_o_proximo(self):
        """"Descanso" sozinho deixa a pessoa sem saber quando volta — e era
        assim que a Home falava de treino: um travessão numa linha de 12px."""
        from datetime import time
        from workouts.models import TrainingSession

        user = self.pessoa("descanso@exemplo.com", ("treino",), "treino")
        TrainingSession.objects.filter(plan__user=user).delete()
        user.training_days.all().delete()
        from accounts.models import TrainingDay
        # amanhã, e só amanhã: o cartão tem de saber dizer "amanhã, A"
        TrainingDay.objects.create(
            user=user,
            weekday=(timezone.localdate() + timedelta(days=1)).weekday(),
            start_time=time(19, 0),
            duration_min=60,
        )
        from workouts import services as treino_services
        treino_services.sync_active_routine(user)

        cartao = self._cartao(self.home(), "Treino")

        self.assertIn("Descanso", cartao)
        self.assertIn("amanhã", cartao)

    def test_corrida_mostra_a_ultima_e_a_porta(self):
        self.pessoa("acao-corrida@exemplo.com", ("corrida",), "corrida")

        cartao = self._cartao(self.home(), "Corrida")

        self.assertIn("Nenhuma ainda", cartao)
        self.assertIn('href="%s"' % reverse("workouts:corridas"), cartao)
        self.assertIn("Registrar corrida", cartao)

    def test_progresso_leva_a_faixa_de_pesagem_quando_ela_esta_pedindo(self):
        """E leva à curva quando não está: oferecer "registrar peso" a quem
        acabou de se pesar é pedir um número que o app já tem."""
        user = self.pessoa("acao-progresso@exemplo.com", ("progresso",), "progresso")

        cartao = self._cartao(self.home(), "Progresso")
        # a etapa 1 do wizard grava o peso de hoje — não há convite
        self.assertIn('href="%s"' % reverse("plans:history"), cartao)
        self.assertIn("Ver progresso", cartao)

        WeightEntry.objects.filter(user=user).update(
            date=timezone.localdate() - timedelta(days=10)
        )
        cartao = self._cartao(self.home(), "Progresso")
        self.assertIn('href="#pesar"', cartao)
        self.assertIn("Registrar peso", cartao)
