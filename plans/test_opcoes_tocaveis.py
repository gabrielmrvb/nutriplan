"""A opção do cardápio é uma RECEITA, e a ação dela está à vista.

O DEFEITO ORIGINAL (12/09/2026). Cada opção era um `<details>`: a linha visível
trazia letra, nome, calorias, proteína e tempo, e o botão que REGISTRA a
refeição morava dentro do corpo colapsado. Quem abria a tela via duas linhas de
informação e nenhuma ação — para marcar o almoço era preciso primeiro descobrir
que a linha abria.

A CORREÇÃO daquele dia foi de posição: o formulário saiu de dentro do corpo e
virou irmão do `<details>`.

O QUE MUDOU EM 23/09/2026. A auditoria mediu o resultado daquela correção e
achou o problema seguinte: "aberto, cada opção é UMA LINHA de texto seguida de
um REGISTRAR A gigante — cinco botões empilhados por refeição". A opção deixou
de ser uma linha com sanfona e virou um CARD DE RECEITA: ilustração, nome,
caloria, os três macros, tempo de preparo e os ingredientes com a porção. O
`<details>` de consulta sumiu junto — o que ele guardava está na tela, e o que
não cabia (o modo de preparo) virou uma TELA com endereço próprio.

AS PROPRIEDADES DESTE ARQUIVO NÃO MUDARAM, e é por isso que ele continua
existindo com os mesmos nomes de teste: a ação não fica atrás de uma
descoberta, o botão diz o que registra, os números continuam na tela, as ações
secundárias continuam secundárias, só a primeira opção é primária, e tudo que
não é a refeição da vez nasce recolhido.
"""
import re
from datetime import datetime, time
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import MealLog, MealStatus, NutritionPlan
from .test_saldo_sem_registro import com_plano


def cards_de_receita(html):
    """Só o que está DENTRO dos cards de receita.

    A asserção que importa é sobre POSIÇÃO — o que está à vista e o que está
    atrás de um toque —, e uma busca na página inteira não distingue um do
    outro.
    """
    return "\n".join(
        re.findall(r'<article class="receita.*?</article>', html, re.S)
    )


class ARegistrarNaoMoraMaisDentroDaSanfonaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = com_plano()
        self.client.force_login(self.pessoa)
        self.html = self.client.get(reverse("plans:alimentacao")).content.decode("utf-8")

    def test_a_tela_tem_opcoes_para_medir(self):
        """Controle positivo: sem opção na tela, tudo abaixo passaria vazio."""
        self.assertIn('<article class="receita', self.html)

    def test_o_botao_de_registrar_esta_no_card_da_opcao(self):
        """A ação e a opção que ela registra são um PAR, e a proximidade é o
        que diz isso. Antes o botão era irmão do `<details>`; hoje ele mora
        dentro do card da receita a que pertence."""
        self.assertIn("Comi esta", self.html)
        self.assertIn('class="receita__acao"', cards_de_receita(self.html))

    def test_o_botao_diz_qual_opcao_registra(self):
        """"Comi esta" dito por escrito, com o nome da receita e do horário.

        Eram "Registrar A" e "Registrar B" — e a letra é nome INTERNO: ela
        existe para o rodízio, que é do servidor. O que distingue os dois
        botões na tela é o card em que cada um está; o que os distingue para
        quem usa leitor de tela é o `aria-label`, que nomeia a receita.
        """
        rotulos = re.findall(r'aria-label="Registrar ([^"]+)"', self.html)
        self.assertTrue(rotulos, "nenhum botão nomeia a opção que registra")
        # A âncora leva os sinais de tag: `Registrar A` casa com
        # "Registrar Arroz com lentilha e couve em Almoço", que é o
        # `aria-label` NOVO. Medir a ausência do rótulo velho com um
        # prefixo do rótulo novo é a armadilha que este repositório
        # documenta — a asserção passa (ou falha) por outro lugar da tela.
        self.assertNotIn(">Registrar A<", self.html)
        self.assertNotIn(">Registrar B<", self.html)
        for rotulo in rotulos:
            self.assertIn(" em ", rotulo, rotulo)

    def test_o_card_mostra_os_ingredientes(self):
        """O que a sanfona guardava está na tela: os ingredientes com a
        porção, numa linha."""
        self.assertIn("receita__itens", cards_de_receita(self.html))

    def test_a_linha_visivel_preserva_os_numeros(self):
        for marca in ("receita__kcal", "receita__nome", "receita__macros"):
            with self.subTest(marca=marca):
                self.assertIn(marca, self.html)

    def test_o_tempo_de_preparo_continua_na_linha(self):
        self.assertIn("min", self.html)

    def test_as_acoes_secundarias_continuam_secundarias(self):
        """"Pulei" e "Comi outra coisa" não podem virar botão primário.

        Desde 23/09/2026 elas são MAIS secundárias que antes: eram dois
        botões de 48px com o mesmo peso do registrar, e viraram uma linha
        discreta no rodapé do card (`btn-link`, a mesma língua de "desfazer").
        """
        self.assertIn("Pulei", self.html)
        self.assertIn("Comi outra coisa", self.html)
        self.assertIn('class="meal__secundarias"', self.html)
        self.assertIn('value="skipped" class="btn-link"', self.html)
        self.assertNotIn('value="skipped" class="btn btn--primary"', self.html)


class OContratoDoFormularioNaoMudouTests(TestCase):
    """O botão mudou de lugar; o que ele envia não pode ter mudado.

    A fila offline e a view leem `status` e `option`. Mover o formulário e
    renomear um campo por descuido quebraria a marcação em silêncio — a tela
    continuaria bonita e nada seria gravado.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = com_plano()
        self.client.force_login(self.pessoa)
        self.plano = NutritionPlan.objects.filter(
            user=self.pessoa, is_active=True).first()
        self.slot = self.plano.slots.first()
        self.opcao = self.slot.options.first()

    def test_o_formulario_envia_status_e_opcao(self):
        """Os DOIS campos que a view e a fila offline leem.

        O valor de `option` não é fixado num pk: a tela desenha as duas opções
        do dia, escolhidas por `rodizio`, e `options.first()` pode não ser uma
        delas. O que o contrato exige é o par de campos, e que o id enviado
        pertença ao horário — as duas coisas medidas aqui.
        """
        html = self.client.get(reverse("plans:alimentacao")).content.decode("utf-8")

        self.assertIn('name="status" value="done"', html)
        enviados = {int(pk) for pk in re.findall(
            r'name="option" value="(\d+)"', html)}
        self.assertTrue(enviados, "nenhum formulário manda a opção")
        do_horario = set(self.slot.options.values_list("pk", flat=True))
        self.assertTrue(enviados & do_horario)

    def test_registrar_grava_a_refeicao(self):
        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": self.opcao.pk},
        )

        log = MealLog.objects.get(user=self.pessoa, slot=self.slot,
                                  date=timezone.localdate())
        self.assertEqual(log.status, MealStatus.DONE)
        self.assertEqual(log.chosen_option_id, self.opcao.pk)


class ToqueRepetidoNaoDuplicaRegistroTests(TestCase):
    """Dedo nervoso não pode produzir duas refeições.

    A garantia é do SERVIDOR e é estrutural: `log_meal` usa `update_or_create`
    com chave (pessoa, slot, dia), então o segundo envio reescreve a mesma
    linha. Não é um debounce no JavaScript — debounce falha com a rede lenta,
    que é exatamente quando o dedo bate de novo.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = com_plano()
        self.client.force_login(self.pessoa)
        plano = NutritionPlan.objects.filter(user=self.pessoa, is_active=True).first()
        self.slot = plano.slots.first()
        self.opcoes = list(self.slot.options.all()[:2])

    def _marcar(self, opcao):
        return self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": opcao.pk},
        )

    def test_dois_toques_iguais_gravam_uma_refeicao(self):
        self._marcar(self.opcoes[0])
        self._marcar(self.opcoes[0])

        self.assertEqual(
            MealLog.objects.filter(user=self.pessoa, slot=self.slot,
                                   date=timezone.localdate()).count(),
            1,
        )

    def test_trocar_de_opcao_reescreve_em_vez_de_somar(self):
        """Tocou A, mudou de ideia, tocou B: sobra B, e uma linha só."""
        self._marcar(self.opcoes[0])
        self._marcar(self.opcoes[1])

        logs = MealLog.objects.filter(user=self.pessoa, slot=self.slot,
                                      date=timezone.localdate())
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().chosen_option_id, self.opcoes[1].pk)

    def test_uma_refeicao_registrada_nao_contamina_a_outra(self):
        """Isolamento entre horários: marcar o café não marca o almoço."""
        plano = NutritionPlan.objects.filter(user=self.pessoa, is_active=True).first()
        outro = plano.slots.exclude(pk=self.slot.pk).first()

        self._marcar(self.opcoes[0])

        self.assertFalse(
            MealLog.objects.filter(user=self.pessoa, slot=outro,
                                   date=timezone.localdate()).exists()
        )


class AOpcaoAEASugestaoEABEAAlternativaTests(TestCase):
    """Dois botões verdes iguais não são hierarquia — são um empate.

    Medido na captura de 12/09/2026 a 390px: o cartão da refeição atual
    trazia "Registrar A" e "Registrar B" como dois `btn--primary` de largura
    inteira, um debaixo do outro, e mais nada verde na tela competia com
    eles. A missão mestre (§7) pede que o verde marque estado positivo e
    ação principal, "não pintar tudo".

    `rodizio` já ordena as opções, e a primeira da projeção É a sugestão do
    dia. O botão dela continua primário; o da segunda vira `btn--ghost`:
    mesma largura, mesmo alvo de 44px, mesma ação, peso diferente. Quem quer
    a segunda toca nela; quem só quer marcar toca no verde.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = com_plano()
        self.client.force_login(self.pessoa)
        # Meio-dia e meia, sempre: só assim existe uma refeição "de agora"
        # (`meal--agora`) para medir. Lendo a hora da máquina, de madrugada
        # não há vencida nenhuma — o `pre-push` de 15/09/2026 às 00h15 pegou,
        # com `IndexError` no `split('meal--agora')`.
        meio_dia = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(12, 30))
        )
        with mock.patch("plans.views.relogio", return_value=meio_dia):
            self.html = self.client.get(reverse("plans:alimentacao")).content.decode("utf-8")

    def _cartao_da_vez(self):
        """O card da refeição de agora, do começo dele ao começo do próximo.

        Cortar em `</article>` não serve mais: os cards de receita TAMBÉM são
        `<article>`, e o primeiro fechamento agora é o da primeira receita.
        """
        inicio = self.html.index("meal--agora")
        proximo = self.html.find('<article class="meal', inicio)
        return self.html[inicio:proximo] if proximo != -1 else self.html[inicio:]

    def _acoes(self, bloco):
        return re.findall(r'<form[^>]*class="receita__acao"(.*?)</form>', bloco, re.S)

    def test_na_refeicao_atual_so_a_primeira_opcao_e_primaria(self):
        acoes = self._acoes(self._cartao_da_vez())
        self.assertGreaterEqual(len(acoes), 2, "a refeição atual precisa de duas opções para medir")
        self.assertIn("btn--primary", acoes[0])
        self.assertNotIn("btn--primary", acoes[1])
        self.assertIn("btn--ghost", acoes[1])

    def test_as_duas_continuam_registrando_a_mesma_coisa(self):
        """Peso visual diferente, contrato igual: as duas mandam `status=done`
        e a própria opção."""
        for acao in self._acoes(self._cartao_da_vez())[:2]:
            self.assertIn('name="status" value="done"', acao)
            self.assertIn('name="option"', acao)
            self.assertIn("btn--block", acao)


class ARefeicaoFuturaFicaEmSegundoPlanoTests(TestCase):
    """§7: a ação da vez aberta; o resto do dia recolhido.

    Medido a 390px em 12/09/2026: cinco refeições sem registro renderizavam
    dez botões de registrar e dez ações secundárias — ~2.100px de formulário
    para um dia em que só uma refeição é a vez. Em 23/09/2026 a conta ficou
    maior (cada opção virou um card de receita), e por isso a régua ficou
    mais estrita: o que não é a vez é UMA LINHA.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = com_plano()
        self.client.force_login(self.pessoa)
        # Meio-dia e meia, sempre: o café já venceu, o almoço é a vez e o
        # resto do dia é futuro. Lendo a hora da máquina, este teste
        # reprovava depois da última refeição do plano — o `pre-push` de
        # 14/09/2026 às 20h44 pegou, com "precisa de pelo menos uma refeição
        # futura para medir".
        meio_dia = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(12, 30))
        )
        with mock.patch("plans.views.relogio", return_value=meio_dia):
            self.html = self.client.get(reverse("plans:alimentacao")).content.decode("utf-8")

    def _artigos(self):
        """Cada card de refeição: (estado, corpo).

        O corte é no COMEÇO do próximo card, e não no primeiro `</article>`:
        desde 23/09/2026 as opções também são `<article>`, e o fechamento que
        aparece primeiro é o da primeira receita.
        """
        marcas = [
            (m.group(1), m.start())
            for m in re.finditer(r'<article class="meal meal--([a-z]+)"', self.html)
        ]
        blocos = []
        for i, (estado, inicio) in enumerate(marcas):
            fim = marcas[i + 1][1] if i + 1 < len(marcas) else len(self.html)
            blocos.append((estado, self.html[inicio:fim]))
        return blocos

    def test_a_futura_guarda_as_opcoes_num_details_fechado(self):
        futuras = [corpo for estado, corpo in self._artigos() if estado == "futura"]
        self.assertTrue(futuras, "precisa de pelo menos uma refeição futura para medir")
        for corpo in futuras:
            self.assertIn('<details class="meal__futuro">', corpo)
            self.assertNotIn('<details class="meal__futuro" open', corpo)
            self.assertIn('<summary class="meal__linha">', corpo)

    def test_a_refeicao_da_vez_continua_aberta(self):
        """Controle positivo: o `<details>` é de todas MENOS a da vez. A de
        agora mostra as opções sem toque nenhum."""
        abertas = [corpo for estado, corpo in self._artigos() if estado == "agora"]
        self.assertTrue(abertas, "precisa de uma refeição de agora")
        for corpo in abertas:
            self.assertNotIn("meal__futuro", corpo)
            self.assertIn("receita__acao", corpo)

    def test_a_vencida_fica_em_uma_linha_com_o_convite_a_registrar(self):
        """Home compacta (decisão do dono, 20/09/2026). Até então a VENCIDA
        também nascia aberta, por ser "ação em aberto": medido na auditoria,
        um primeiro uso às 15 h dava uma Home de 3 757 px com quatro
        refeições abertas × quatro botões cada; um fixture às 18 h, 3 530 px.
        Só a refeição da vez fica aberta; a vencida vira uma linha com o
        convite a registrar, e as opções continuam ali, atrás do toque.

        A reforma de 23/09/2026 quase desfez isto — a primeira versão abria
        `agora` E `pendente`, com o argumento de que as duas são ação em
        aberto. Com cards de receita no lugar das linhas, isso teria posto
        DOIS cardápios abertos na tela às 15h. Este teste é o que segurou.
        """
        vencidas = [corpo for estado, corpo in self._artigos() if estado == "pendente"]
        self.assertTrue(vencidas, "meio-dia e meia: o café da manhã já venceu")
        for corpo in vencidas:
            self.assertIn('<details class="meal__futuro">', corpo)
            self.assertNotIn('<details class="meal__futuro" open', corpo)
            self.assertIn("Não registrada · registrar", corpo)
            self.assertIn("receita__acao", corpo)

    def test_fora_da_vez_toda_acao_nasce_atras_do_toque(self):
        """A conta que a auditoria mediu: quantas ações nascem visíveis. Em
        toda refeição que não é a da vez, o `<details class="meal__futuro">`
        abre ANTES da primeira ação — nenhum botão de registrar fora dele."""
        medidas = 0
        for estado, corpo in self._artigos():
            if estado in ("agora", "resolvida") or "receita__acao" not in corpo:
                continue
            medidas += 1
            self.assertLess(
                corpo.index('<details class="meal__futuro">'),
                corpo.index("receita__acao"),
                corpo[:200],
            )
        self.assertGreaterEqual(medidas, 2, "meio-dia e meia: uma vencida e pelo menos uma futura")
