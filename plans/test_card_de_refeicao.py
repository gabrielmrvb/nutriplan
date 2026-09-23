# -*- coding: utf-8 -*-
"""O card de refeição, o topo e a porção — a reforma de 23/09/2026.

A auditoria daquele dia disse o que o cardápio era: "horário, nome, alvo e um
link *Ver opções*; fechado, um retângulo vazio. Aberto, cada opção é UMA LINHA
seguida de um REGISTRAR A gigante". E o que decide uma escolha de comida — do
que é feita, quanto rende, quanto demora, como se faz — estava no banco e fora
da tela.

Estes testes prendem as três propriedades que a reforma criou:

1. o ESTADO da refeição vem do servidor numa palavra e a tela desenha três
   coisas diferentes a partir dele (feita, da vez, futura);
2. o TOPO conta o dia antes da primeira refeição, e o consumo depois dela;
3. a PORÇÃO recalcula o que a tela mostra E o que o histórico grava, com a
   conta do lado do servidor e uma lista fechada de valores.
"""
import re
from datetime import datetime, time
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from plans import services
from plans.models import MealLog, MealStatus
from plans.porcoes import passos_do_preparo
from plans.tests import create_complete_user


def _card(html, slot_pk):
    """O pedaço do HTML que é o card DAQUELE horário, e só ele.

    Duas armadilhas, as duas vividas ao escrever este arquivo:

    - fatiar por um número fixo de caracteres vaza para o card SEGUINTE, e a
      asserção "a refeição feita não tem card de receita" encontrou o card de
      baixo, que tem;
    - fatiar o ÚLTIMO card até o fim do documento vaza para o PAINEL DA
      DIREITA, que mostra a receita da refeição da vez com os mesmos números.
      A sabotagem "a linha da refeição fechada perde o alvo" passou verde por
      causa disso: o "710 kcal" que a asserção achava era o da outra coluna.

    Por isso o recorte começa na seção das refeições e termina nela.
    """
    secao = html.split('class="refeicoes', 1)[1]
    secao = secao.split("</section>", 1)[0]
    inicio = secao.index('id="slot-%d"' % slot_pk)
    proximo = secao.find('<article class="meal', inicio)
    return secao[inicio:proximo] if proximo != -1 else secao[inicio:]


def _as(hora, minuto=0):
    """Um instante de HOJE, na hora local, para congelar o relógio da tela."""
    return timezone.make_aware(
        datetime.combine(timezone.localdate(), time(hora, minuto))
    )


class CardDeRefeicaoTests(TestCase):
    """Cada refeição mostra as DUAS opções como duas receitas — e o estado
    dela decide se elas nascem abertas."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        cls.user = create_complete_user(email="card@exemplo.com")
        cls.plan = services.create_plan(cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def _tela(self, hora=8):
        with mock.patch("plans.views.relogio", return_value=_as(hora)):
            return self.client.get(reverse("plans:alimentacao")).content.decode()

    def test_a_refeicao_da_vez_nasce_aberta_com_as_duas_receitas(self):
        """O toque deixou de ser para DESCOBRIR e passou a ser para
        APROFUNDAR: as duas opções estão na tela, com ilustração, caloria, os
        três macros, o tempo e os ingredientes."""
        html = self._tela(hora=8)
        primeiro = self.plan.slots.order_by("order").first()

        self.assertIn('class="meal meal--agora"', html)
        # As duas receitas do dia, cada uma num card com ação própria.
        self.assertEqual(html.count('<article class="receita'), 2 * 5)
        self.assertIn("receita--sugerida", html)
        self.assertIn("Comi esta", html)
        # O rótulo interno A/B não chega na tela.
        # Com os sinais de tag: "Registrar A" casa com o `aria-label`
        # novo ("Registrar Arroz com lentilha...").
        self.assertNotIn(">Registrar A<", html)
        self.assertNotIn(">Registrar B<", html)
        # E o card da vez NÃO está dentro do `<details>` das futuras.
        pedaco = _card(html, primeiro.pk)
        self.assertNotIn('<details class="meal__futuro">', pedaco)

    def test_a_refeicao_futura_e_uma_linha_com_hora_nome_e_alvo(self):
        """Item 11: as outras colapsadas em uma linha cada. O cabeçalho de
        duas linhas some junto — ele mora DENTRO do resumo."""
        html = self._tela(hora=8)
        ultimo = self.plan.slots.order_by("order").last()
        pedaco = _card(html, ultimo.pk)

        self.assertIn('<details class="meal__futuro">', pedaco)
        self.assertIn('<summary class="meal__linha">', pedaco)
        self.assertIn("%d kcal" % ultimo.target_kcal, pedaco)
        self.assertIn(ultimo.time.strftime("%H:%M"), pedaco)
        # O cabeçalho separado não é desenhado para ela.
        self.assertNotIn('class="meal__head"', pedaco)

    def test_a_refeicao_registrada_mostra_o_que_foi_comido_e_o_desfazer(self):
        """Feita é um terceiro desenho: o resultado e a saída, sem as duas
        opções — oferecer "Comi esta" embaixo de um registro que já existe é
        oferecer uma ação que só pode dar errado."""
        slot = self.plan.slots.order_by("order").first()
        opcao = slot.options.order_by("rank").first()
        self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]),
            {"status": MealStatus.DONE, "option": opcao.pk},
        )
        html = self._tela(hora=9)
        pedaco = _card(html, slot.pk)

        self.assertIn('class="meal meal--resolvida"', html)
        self.assertIn(opcao.template.name, pedaco)
        self.assertIn("desfazer", pedaco)
        self.assertNotIn('<article class="receita', pedaco)

    def test_o_card_leva_os_ingredientes_com_a_porcao(self):
        """"Queijo minas com banana — quanto queijo, quantas bananas?" era a
        pergunta da auditoria, e a resposta já estava no banco."""
        html = self._tela(hora=8)
        slot = self.plan.slots.order_by("order").first()
        opcao = slot.options.order_by("rank").first()
        primeiro_item = opcao.ingredient_list()[0]

        self.assertIn('class="receita__itens"', html)
        # O nome do alimento aparece em MINÚSCULA e sem a palavra de preparo
        # ("Peito de frango grelhado" -> "peito de frango"), então a régua é o
        # começo do nome, que é o que sobrevive às duas transformações.
        raiz = primeiro_item["food"].name.split()[0].lower()
        self.assertIn(raiz, html.lower())

    def test_o_card_abre_a_receita_por_um_link_de_verdade(self):
        """Sem JavaScript o link navega; com ele vira folha ou painel. O que
        este teste prende é que ele EXISTE como link."""
        with mock.patch("plans.views.relogio", return_value=_as(8)):
            resposta = self.client.get(reverse("plans:alimentacao"))
        html = resposta.content.decode()
        slot = resposta.context["slots"][0]

        # A régua é o LINK do card, e o que ele aponta: o horário daquele card
        # e uma opção DAQUELE horário. Não se fixa QUAL opção — o rodízio
        # escolhe duas das quatro do repertório, e prender a escolha aqui
        # mediria o rodízio, não o link. (A primeira versão deste teste fazia
        # isso e reprovou na suíte inteira, onde os pks são outros e o rodízio
        # sorteia outro par.)
        #
        # E o recorte é o CARD: a mesma URL aparece no painel da direita — os
        # chips de porção e "trocar por outra receita" —, e uma busca na
        # página inteira passava mesmo com o link do card apontando para `#`.
        pedaco = _card(html, slot.pk)
        links = re.findall(r'href="/refeicao/(\d+)/receita/(\d+)/"', pedaco)
        self.assertTrue(links, "o card não tem link para a receita")
        do_horario = set(slot.options.values_list("pk", flat=True))
        for slot_pk, opcao_pk in links:
            self.assertEqual(int(slot_pk), slot.pk)
            self.assertIn(int(opcao_pk), do_horario)
        self.assertIn("Ver a receita", pedaco)


class OTopoContaODiaTests(TestCase):
    """Antes da primeira refeição o topo mostra a META e o plano; depois
    dela, o consumo. Não é estado vazio com texto de consolo: é outra
    pergunta, respondida."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        cls.user = create_complete_user(email="topo@exemplo.com")
        cls.plan = services.create_plan(cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def _contexto(self, hora=8):
        with mock.patch("plans.views.relogio", return_value=_as(hora)):
            return self.client.get(reverse("plans:alimentacao"))

    def test_sem_nenhuma_marcacao_o_topo_esta_no_modo_plano(self):
        resposta = self._contexto()
        html = resposta.content.decode()

        self.assertEqual(resposta.context["topo"]["modo"], "plano")
        self.assertIn("a sua meta", html)
        self.assertIn("o seu dia em", html)
        # A legenda dos macros diz o ALVO, e não três zeros com a barra cheia
        # atrás: a barra desenha a DIVISÃO do dia, e antes da primeira
        # refeição só a divisão existe.
        self.assertIn("%d" % self.plan.protein_g, html)
        # A âncora é a MARCA da legenda, e não o texto "0 /": aquele casava
        # com qualquer "0 /" da página (há um dentro de um `viewBox`), que é
        # a armadilha que este repositório documenta — a asserção passa por
        # outro lugar da tela.
        self.assertIn('<span class="hero-macros__meta num">g</span>', html)
        self.assertNotIn('<span class="hero-macros__meta num">/', html)

    def test_depois_da_primeira_refeicao_o_topo_conta_o_consumo(self):
        slot = self.plan.slots.order_by("order").first()
        opcao = slot.options.order_by("rank").first()
        self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]),
            {"status": MealStatus.DONE, "option": opcao.pk},
        )
        resposta = self._contexto(hora=9)
        html = resposta.content.decode()

        self.assertEqual(resposta.context["topo"]["modo"], "dia")
        self.assertIn("1 de 5", html)
        self.assertIn("faltam", html)

    def test_a_proteina_no_rumo_compara_fracoes_e_nao_um_limiar_de_relogio(self):
        """A régua é a fração de proteína comida contra a fração de CALORIA
        comida: dizer "no rumo" por um limiar absoluto seria inventar um
        horário que o plano de cada pessoa não tem."""
        self.assertIsNone(self._contexto().context["topo"]["proteina"])

        slot = self.plan.slots.order_by("order").first()
        opcao = slot.options.order_by("rank").first()
        self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]),
            {"status": MealStatus.DONE, "option": opcao.pk},
        )
        self.assertIn(
            self._contexto(hora=9).context["topo"]["proteina"], ("no_rumo", "atras")
        )


class APorcaoRecalculaTests(TestCase):
    """½, 1 ou 1½ — a conta é do servidor, e o número que a tela mostra é o
    mesmo que vai para o histórico."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        cls.user = create_complete_user(email="porcao@exemplo.com")
        cls.plan = services.create_plan(cls.user)
        cls.slot = cls.plan.slots.order_by("order").first()
        cls.opcao = cls.slot.options.order_by("rank").first()

    def setUp(self):
        self.client.force_login(self.user)

    def _receita(self, **params):
        url = reverse("plans:receita", args=[self.slot.pk, self.opcao.pk])
        return self.client.get(url, params)

    def test_meia_porcao_divide_o_kcal_os_macros_e_as_quantidades(self):
        inteira = self._receita().context["receita"]
        metade = self._receita(porcao="0.5").context["receita"]

        self.assertEqual(metade["kcal"], inteira["kcal"] / 2)
        self.assertEqual(metade["protein_g"], inteira["protein_g"] / 2)
        self.assertEqual(metade["carb_g"], inteira["carb_g"] / 2)
        self.assertEqual(metade["fat_g"], inteira["fat_g"] / 2)
        for um, meio in zip(inteira["itens"], metade["itens"]):
            self.assertEqual(meio["quantity"], um["quantity"] / 2)

    def test_a_porcao_escala_ate_o_item_que_o_motor_nao_escala(self):
        """`scale_factor` e `porcao` respondem perguntas diferentes: o motor
        não parte um ovo para fechar a caloria (1,37 ovo não existe), mas meio
        prato TEM meio ovo — e se o ovo não acompanhasse, o kcal da tela
        deixaria de ser o kcal do que foi comido."""
        fixos = [
            item
            for item in self.opcao.template.items.all()
            if not item.scalable
        ]
        if not fixos:  # pragma: no cover - depende do catálogo
            self.skipTest("nenhum item não escalável nesta receita")
        metade = self._receita(porcao="0.5").context["receita"]
        por_alimento = {i["food"].pk: i["quantity"] for i in metade["itens"]}
        for item in fixos:
            self.assertEqual(
                por_alimento[item.food.pk], item.quantity_g * Decimal("0.5")
            )

    def test_porcao_forjada_cai_na_inteira(self):
        """A lista é FECHADA do lado do servidor porque este número
        multiplica o kcal que entra no histórico: um `porcao=99` forjado
        escreveria um dia de 280 mil calorias."""
        for forjada in ("99", "-1", "abc", "", "0", "1e9"):
            with self.subTest(porcao=forjada):
                r = self._receita(porcao=forjada).context["receita"]
                self.assertEqual(r["porcao"], Decimal("1"))

    def test_o_registro_grava_a_fracao_e_os_macros_dela(self):
        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {
                "status": MealStatus.DONE,
                "option": self.opcao.pk,
                "porcao": "0.5",
            },
        )
        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.porcao, Decimal("0.5"))
        # O campo guarda duas casas: a metade de 513,63 é 256,815 e entra
        # como 256,82. Comparar sem quantizar mediria o arredondamento do
        # banco, e não a conta.
        casas = Decimal("0.01")
        self.assertEqual(log.kcal, (self.opcao.kcal / 2).quantize(casas))
        self.assertEqual(log.protein_g, (self.opcao.protein_g / 2).quantize(casas))

    def test_registro_forjado_grava_a_porcao_inteira(self):
        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": self.opcao.pk, "porcao": "99"},
        )
        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.porcao, Decimal("1"))
        self.assertEqual(log.kcal, self.opcao.kcal)

    def test_pulei_nao_tem_porcao(self):
        """"Pulei" não tem metade, e "comi outra coisa" traz os macros do que
        a pessoa descreveu — a fração é de quem comeu a receita."""
        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.SKIPPED, "porcao": "0.5"},
        )
        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.porcao, Decimal("1"))
        self.assertEqual(log.kcal, Decimal("0"))


class AReceitaEUmaTelaTests(TestCase):
    """Ela tem endereço próprio, é a mesma seção que a folha e o painel
    recortam, e o filtro por plano ativo do próprio usuário fecha o IDOR."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        cls.user = create_complete_user(email="receita@exemplo.com")
        cls.plan = services.create_plan(cls.user)
        cls.slot = cls.plan.slots.order_by("order").first()
        cls.opcao = cls.slot.options.order_by("rank").first()

        cls.outra_pessoa = create_complete_user(email="outra@exemplo.com")
        cls.outro_plano = services.create_plan(cls.outra_pessoa)

    def setUp(self):
        self.client.force_login(self.user)

    def test_a_receita_traz_ingredientes_preparo_macros_e_a_troca(self):
        html = self.client.get(
            reverse("plans:receita", args=[self.slot.pk, self.opcao.pk])
        ).content.decode()

        self.assertIn('<section id="receita"', html)
        self.assertIn("O que vai", html)
        self.assertIn("Como faz", html)
        self.assertIn("Trocar por outra receita", html)
        self.assertIn("Porção", html)
        self.assertIn(self.opcao.template.name, html)

    def test_a_receita_de_outra_pessoa_nao_abre(self):
        alheia = self.outro_plano.slots.order_by("order").first()
        resposta = self.client.get(
            reverse(
                "plans:receita",
                args=[alheia.pk, alheia.options.order_by("rank").first().pk],
            )
        )
        self.assertEqual(resposta.status_code, 404)

    def test_a_opcao_tem_de_pertencer_ao_horario_pedido(self):
        """O par `(slot, option)` é conferido: um id de opção válido colado
        noutro horário devolve 404, e não a receita de outro momento do dia."""
        outro_horario = self.plan.slots.order_by("order").last()
        resposta = self.client.get(
            reverse("plans:receita", args=[outro_horario.pk, self.opcao.pk])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_refeicao_ja_registrada_nao_oferece_registrar_de_novo(self):
        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": self.opcao.pk},
        )
        html = self.client.get(
            reverse("plans:receita", args=[self.slot.pk, self.opcao.pk])
        ).content.decode()
        self.assertIn("Você registrou esta refeição", html)
        self.assertNotIn(">Comi esta<", html)


class OPreparoViraPassosTests(TestCase):
    """O catálogo guarda uma frase corrida; na cozinha, com uma mão ocupada,
    é uma lista que se lê."""

    def test_a_frase_corrida_vira_acoes(self):
        passos = passos_do_preparo(
            "Hidrate o cuscuz, leve à cuscuzeira e sirva com o ovo cozido e o "
            "tomate, regados com o azeite"
        )
        self.assertEqual(len(passos), 3)
        self.assertTrue(passos[0].startswith("Hidrate"))
        self.assertTrue(passos[1].startswith("Leve"))
        # Vírgula solta NÃO corta: "com o ovo cozido e o tomate, regados com o
        # azeite" é um passo só, e cortar ali daria um passo sem verbo.
        self.assertIn("azeite", passos[2])

    def test_frase_de_uma_acao_continua_um_passo(self):
        passos = passos_do_preparo("Bata o leite com a banana no liquidificador")
        self.assertEqual(len(passos), 1)

    def test_sem_instrucao_nao_inventa_passo(self):
        self.assertEqual(passos_do_preparo(""), [])
        self.assertEqual(passos_do_preparo(None), [])

    def test_o_catalogo_inteiro_vira_passos(self):
        """Controle positivo da régua: com o catálogo real, nenhuma receita
        fica sem passo, e a maioria tem mais de um. A primeira versão desta
        função devolvia UM passo para as 54 — um `\\b` virou um byte de
        backspace no arquivo e o corte nunca disparava."""
        call_command("seed_catalog", verbosity=0)
        from catalog.models import MealTemplate

        contagem = [
            len(passos_do_preparo(t.instructions))
            for t in MealTemplate.objects.all()
        ]
        self.assertTrue(contagem)
        self.assertTrue(all(n >= 1 for n in contagem))
        self.assertGreater(
            sum(1 for n in contagem if n > 1), len(contagem) // 2,
            "mais da metade das receitas tem mais de uma ação",
        )


class OPainelDaDireitaTests(TestCase):
    """A coluna da direita deixou de ser um vazio de 1.500px.

    Medido a 1280px em 23/09/2026: três cartões recolhidos no alto e nada
    embaixo, enquanto a esquerda rolava cinco refeições. Ela passa a abrir com
    a receita da refeição da vez e com a semana já contada.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        cls.user = create_complete_user(email="painel@exemplo.com")
        cls.plan = services.create_plan(cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def _tela(self, hora=8):
        with mock.patch("plans.views.relogio", return_value=_as(hora)):
            return self.client.get(reverse("plans:alimentacao"))

    def test_o_painel_nasce_com_a_receita_da_refeicao_da_vez(self):
        resposta = self._tela()
        painel = resposta.context["receita_do_painel"]
        slot_da_vez = next(
            s for s in resposta.context["slots"] if s.estado in ("agora", "pendente")
        )

        self.assertIsNotNone(painel)
        self.assertEqual(painel["slot"].pk, slot_da_vez.pk)
        self.assertEqual(painel["opcao"].pk, slot_da_vez.opcoes_do_dia[0].pk)
        self.assertIn('data-painel-receita', resposta.content.decode())

    def test_o_painel_mostra_o_preparo_e_a_troca(self):
        """É a MESMA seção que a folha do celular recorta — um markup, três
        lugares. Se a parcial parar de ser incluída aqui, o desktop volta a
        ter uma coluna vazia e nada mais reprova."""
        html = self._tela().content.decode()
        depois_do_aside = html.split('<aside class="split__aside', 1)[1]
        self.assertIn('<section id="receita"', depois_do_aside)
        self.assertIn("Como faz", depois_do_aside)
        self.assertIn("Trocar por outra receita", depois_do_aside)

    def test_a_previa_das_compras_traz_tres_itens_e_o_total(self):
        compras = self._tela().context["compras"]

        self.assertGreater(compras["total"], 3)
        self.assertEqual(len(compras["primeiros"]), 3)
        self.assertEqual(compras["restantes"], compras["total"] - 3)
        for item in compras["primeiros"]:
            self.assertTrue(item["nome"])
            self.assertTrue(item["display"])

    def test_a_previa_das_compras_nao_paga_a_conta_duas_vezes(self):
        """Ela custa SEIS consultas (`shopping_list` projeta os sete dias) e
        por isso vive em cache de processo por (plano, semana). A segunda
        visita não pode pagar de novo — era 24 consultas na tela, e é 18."""
        from django.core.cache import cache
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        cache.clear()
        self._tela()  # aquece
        with CaptureQueriesContext(connection) as ctx:
            self._tela()
        self.assertLessEqual(len(ctx.captured_queries), 18, len(ctx.captured_queries))

    def test_com_o_dia_inteiro_resolvido_o_painel_continua_respondendo(self):
        """Sem refeição em aberto ele mostra a primeira do dia, em vez de
        sumir e devolver a coluna vazia."""
        for slot in self.plan.slots.all():
            self.client.post(
                reverse("plans:mark_meal", args=[slot.pk]),
                {"status": MealStatus.SKIPPED},
            )
        painel = self._tela(hora=22).context["receita_do_painel"]
        self.assertIsNotNone(painel)

    def test_o_painel_prefere_a_refeicao_da_vez_a_vencida(self):
        """Às 10h, com o café das 7h vencido e o lanche das 10h37 aberto na
        esquerda, o painel tem de falar do LANCHE. A primeira versão pegava a
        primeira "em aberto" e respondia sobre o café — a coluna de consulta
        falando de outra refeição que não a que está na tela."""
        resposta = self._tela(hora=11)
        estados = {s.pk: s.estado for s in resposta.context["slots"]}
        painel = resposta.context["receita_do_painel"]

        self.assertIn("pendente", estados.values(), "o fixture precisa de uma vencida")
        self.assertEqual(estados[painel["slot"].pk], "agora")
