# -*- coding: utf-8 -*-
"""O acabamento da Home (23/09/2026): o que ele PROMETE, e o que não inventa.

A campanha levou a tela Hoje ao nível de um mockup de referência — cabeçalho
com o dia, herói de três colunas que registra, grade de cinco cartões em
linhas de três, tira de sete pontos e linhas de tendência. Este arquivo prende
as propriedades que sobrevivem a qualquer redesenho seguinte, e nenhuma delas
é sobre a aparência:

**Gráfico não é enfeite.** Uma linha só existe com três pontos de dado real —
três pesagens, três semanas em que houve corrida. Abaixo disso o espaço não
fica vazio nem recebe um desenho: ele diz o que destrava a linha.

**A semana é UMA leitura.** A faixa da ofensiva e o cartão de Treino desenham
os mesmos sete dias, calculados uma vez. Duas contas separadas discordariam na
virada da meia-noite.

**O herói registra, e registra o que diz.** "Comi esta" aponta para a primeira
opção da projeção do dia — a mesma que a tela de Alimentação marca como
recomendada —, e não existe quando não há refeição pendente.

**Nada é inventado.** Sem declaração não há selo de área; sem histórico não há
número; sem receita não há sprite de ilustração na página.
"""
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone, translation

from accounts.models import CAMPO_DO_PILAR, Pilar, WeightEntry
from workouts.models import Corrida

from . import sparkline, streaks
from .models import MealLog, MealStatus
from .test_saldo_sem_registro import com_plano
from .views import larguras_do_desktop, semanas_com_km


def _campos_do_heroi(html):
    """Os campos escondidos do formulário de "Comi esta", como o navegador os
    enviaria. Um campo que sair do template sai daqui junto."""
    heroi = html.split('class="agora__acoes"', 1)[1].split("</form>", 1)[0]
    campos = dict(
        re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', heroi)
    )
    campos.pop("csrfmiddlewaretoken", None)
    return campos


def _as(hora, minuto=0):
    """Um instante de HOJE, na hora local — o relógio da tela, congelado."""
    return timezone.make_aware(
        datetime.combine(timezone.localdate(), time(hora, minuto))
    )


class ALinhaFinaSoExisteComDadoTests(SimpleTestCase):
    """`plans/sparkline.py` é puro, e a régua dele é de produto."""

    def test_menos_de_tres_pontos_nao_viram_linha(self):
        """Dois pontos são SEMPRE uma reta: ela desenharia tendência onde não
        há. `None` e não uma linha vazia — o template pergunta `{% if %}`, e
        um objeto que existe sem desenhar nada é como se produz um retângulo
        vazio na tela."""
        self.assertIsNone(sparkline.desenhar([]))
        self.assertIsNone(sparkline.desenhar([81.0]))
        self.assertIsNone(sparkline.desenhar([81.0, 80.5]))
        self.assertIsNotNone(sparkline.desenhar([81.0, 80.5, 80.1]))

    def test_o_maior_valor_fica_no_topo(self):
        """`y` cresce para baixo no SVG. Sem a inversão a curva de peso
        desceria quando a pessoa engorda."""
        linha = sparkline.desenhar([80, 90, 85])
        ys = [float(par.split(",")[1]) for par in linha.pontos.split()]

        self.assertEqual(min(ys), ys[1], "o maior valor tem o menor y")
        self.assertEqual(max(ys), ys[0])

    def test_a_serie_chata_desenha_no_meio_e_nao_divide_por_zero(self):
        """Seis pesagens no mesmo peso são um dado legítimo; `(v - min) / 0`
        não é."""
        linha = sparkline.desenhar([70, 70, 70])
        ys = {par.split(",")[1] for par in linha.pontos.split()}

        self.assertEqual(len(ys), 1)
        self.assertEqual(linha.minimo, linha.maximo)

    def test_as_coordenadas_saem_sem_virgula_decimal_no_template(self):
        """O DEFEITO MEDIDO NA RODADA 1: o app é pt-BR com `USE_L10N`, e um
        `float` no template vira "120,0". `cx="120,0"` é inválido e o SVG o
        descarta em silêncio — o círculo da ponta ia para a origem do
        `viewBox`, no canto esquerdo, longe da linha.

        Renderiza o parcial DE VERDADE, com a língua do app ligada: uma
        asserção sobre o dataclass passaria mesmo com o defeito de volta.
        """
        linha = sparkline.desenhar([0, 4.2, 5.0, 6.1])
        modelo = Template('{% include "plans/_linha_fina.html" %}')

        with translation.override("pt-br"):
            html = modelo.render(Context({"linha": linha, "classe": "", "rotulo": "x"}))

        for atributo in re.findall(r'c[xy]="([^"]+)"', html):
            self.assertNotIn(",", atributo, "coordenada localizada quebra o SVG")
            float(atributo)


class ASemanaDaCorridaContaSemanaTests(SimpleTestCase):
    """`semanas_com_km` é a fonte da linha de Corrida."""

    def test_a_semana_sem_corrida_entra_como_zero(self):
        """Pular a semana vazia desenharia quatro corridas espalhadas em dois
        meses como quatro semanas seguidas — o gráfico afirmaria uma
        constância que não houve."""
        hoje = date(2026, 9, 23)
        corridas = [
            (timezone.make_aware(datetime.combine(hoje - timedelta(days=2), time(7))), 5000),
        ]

        baldes = semanas_com_km(corridas, hoje)

        self.assertEqual(len(baldes), 8)
        self.assertEqual(baldes[:7], [0.0] * 7)
        self.assertEqual(baldes[7], 5.0)

    def test_a_corrida_da_noite_de_domingo_nao_cai_na_semana_seguinte(self):
        """`localtime` e não `.date()`: 22h de domingo em Brasília é
        segunda-feira em UTC."""
        hoje = date(2026, 9, 23)
        domingo = hoje - timedelta(days=hoje.weekday() + 1)
        corridas = [
            (timezone.make_aware(datetime.combine(domingo, time(22))), 4000),
        ]

        baldes = semanas_com_km(corridas, hoje)

        self.assertEqual(baldes[-2], 4.0, "a corrida é da semana passada")
        self.assertEqual(baldes[-1], 0.0)


class ALarguraDosCartoesTests(SimpleTestCase):
    """Linhas de TRÊS, e a sobra dividida em partes iguais."""

    def test_cinco_cartoes_sao_tres_mais_dois(self):
        self.assertEqual(
            larguras_do_desktop(5),
            ["terco", "terco", "terco", "meio", "meio"],
        )

    def test_quatro_cartoes_sao_dois_por_dois(self):
        """E não 3 + 1: um cartão sozinho com o dobro da largura dos vizinhos
        é o "cartão maior por acidente de contagem" que a regra de peso
        visual igual existe para impedir."""
        self.assertEqual(larguras_do_desktop(4), ["meio"] * 4)

    def test_nenhuma_contagem_deixa_coluna_orfa(self):
        """A soma das frações de cada linha fecha a grade de seis colunas."""
        peso = {"terco": 2, "meio": 3, "tudo": 6}
        for quantos in range(1, 7):
            with self.subTest(quantos=quantos):
                colunas = [peso[largura] for largura in larguras_do_desktop(quantos)]
                self.assertEqual(sum(colunas) % 6, 0, "sobra coluna na última linha")


class AFaixaDeTresColunasEDaHomeTests(SimpleTestCase):
    """O MESMO cartão vive em duas telas com larguras diferentes.

    REGRESSÃO MEDIDA (23/09/2026): a faixa de três colunas nasceu numa media
    query, que mede a JANELA. Na Home o cartão ocupa 1.024 px a 1280; na
    Alimentação ele mora na coluna esquerda do `split`, com ~420 px — e a
    1280 a janela passa de 48rem nas duas. Na coluna estreita as três colunas
    não cabiam: o bloco de texto era espremido até o nome da refeição sair
    ESCRITO NA VERTICAL, uma letra por linha (visto na captura).

    A régua é sobre o SELETOR, e não sobre a aparência: `grid-auto-flow:
    column` no cartão AGORA só vale dentro de `.hoje`.
    """

    def setUp(self):
        caminho = Path(__file__).resolve().parents[1] / "static" / "css" / "app.css"
        self.css = re.sub(r"/\*.*?\*/", "", caminho.read_text(encoding="utf-8"), flags=re.S)

    def _regras_do_cartao(self, declaracao):
        achadas = []
        for bloco in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.css):
            if declaracao not in bloco.group(2):
                continue
            for seletor in bloco.group(1).split(","):
                seletor = seletor.strip()
                if "agora-card" in seletor or "agora__" in seletor:
                    achadas.append(seletor)
        return achadas

    def test_a_faixa_de_tres_colunas_so_vale_na_Home(self):
        regras = self._regras_do_cartao("grid-auto-flow: column")

        self.assertTrue(regras, "controle positivo: a faixa existe no arquivo")
        for seletor in regras:
            with self.subTest(seletor=seletor):
                self.assertTrue(
                    seletor.startswith(".hoje "),
                    "a faixa de três colunas precisa do escopo da Home",
                )

    def test_a_faixa_so_entra_com_largura_de_verdade(self):
        """SEGUNDA REGRESSÃO, mesma causa: a faixa nasceu em `48rem` e a 768px
        o container tem ~736 — a coluna de ações (11,5rem) mais o medalhão
        deixavam o texto com quase nada, e o nome saía na vertical DE NOVO,
        agora na própria Home. O degrau é 60rem, onde o container tem ~928.

        Lê a media query que CONTÉM a regra, e não a regra sozinha: é a media
        query que decide quando ela vale.
        """
        blocos = re.findall(
            r"@media \(min-width:\s*([0-9.]+)rem\)\s*\{(.*?)\n\}", self.css, re.S
        )
        medidas = [
            float(largura) for largura, corpo in blocos
            if "grid-auto-flow: column" in corpo and "agora-card" in corpo
        ]

        self.assertTrue(medidas, "controle positivo: a faixa está numa media query")
        for medida in medidas:
            with self.subTest(rem=medida):
                self.assertGreaterEqual(medida, 60, "a faixa precisa de 60rem")

    def test_a_coluna_de_acoes_com_largura_minima_tambem(self):
        """`min-width: 11.5rem` na coluna de ações é o que impede os dois
        botões de saírem com larguras diferentes — e é a mesma armadilha: na
        coluna estreita ele rouba o espaço do texto."""
        for seletor in self._regras_do_cartao("min-width: 11.5rem"):
            with self.subTest(seletor=seletor):
                self.assertTrue(seletor.startswith(".hoje "))


class ASemanaEmSetePontosTests(TestCase):
    """A leitura que alimenta as DUAS tiras."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)
        cls.user = com_plano(email="tira@exemplo.com")

    def test_a_semana_vai_de_segunda_a_domingo(self):
        """E não "os últimos sete dias": a tira responde "como está a MINHA
        semana", que é a pergunta de quem olha na quarta para a sexta — e uma
        janela deslizante não tem sexta."""
        hoje = timezone.localdate()

        semana = streaks.calcular(self.user, hoje=hoje).semana

        self.assertEqual(len(semana), 7)
        self.assertEqual(semana[0].data.weekday(), 0)
        self.assertEqual(semana[-1].data.weekday(), 6)
        self.assertEqual(semana[hoje.weekday()].data, hoje)

    def test_hoje_e_marcado_e_e_um_so(self):
        semana = streaks.calcular(self.user).semana

        self.assertEqual([d.hoje for d in semana].count(True), 1)

    def _dia(self, **kwargs):
        """Um `DiaDaSemana` montado à mão, para o caso existir mesmo quando a
        ficha da pessoa não o produz.

        A PRIMEIRA VERSÃO deste teste varria `calcular()` e passava verde com
        a regra quebrada: o usuário do fixture não tem dia de treino previsto,
        então `estado_do_treino` devolvia "descanso" em todos os sete e a
        varredura media zero casos. A sabotagem mostrou.
        """
        base = dict(
            data=timezone.localdate(), letra="S", nome="segunda-feira",
            hoje=False, futuro=False, antes_da_conta=False,
        )
        base.update(kwargs)
        return streaks.DiaDaSemana(**base)

    def test_o_dia_futuro_com_treino_previsto_diz_previsto_e_nao_faltou(self):
        """Um app que marca falta na sexta-feira, na quarta, está cobrando
        por um dia que não aconteceu — a mesma razão por que hoje não quebra
        a sequência."""
        previsto_sem_registro = streaks.Dia(
            data=timezone.localdate() + timedelta(days=2), treino=False,
            dieta=False, agua=False, treino_previsto=True,
        )

        futuro = self._dia(dia=previsto_sem_registro, futuro=True)
        passado = self._dia(dia=previsto_sem_registro)

        self.assertEqual(futuro.estado_do_treino, "previsto")
        self.assertEqual(futuro.estado, "futuro")
        # CONTROLE POSITIVO: o mesmo dia, no passado, é "faltou" — senão o
        # teste acima passaria com `estado_do_treino` devolvendo uma constante.
        self.assertEqual(passado.estado_do_treino, "faltou")

    def test_nenhum_dia_futuro_da_semana_real_diz_que_faltou(self):
        """A mesma propriedade, agora sobre a semana que a tela desenha."""
        for dia in streaks.calcular(self.user).semana:
            if dia.futuro:
                with self.subTest(dia=dia.data):
                    self.assertEqual(dia.estado, "futuro")
                    self.assertNotEqual(dia.estado_do_treino, "faltou")

    def test_hoje_com_treino_previsto_e_sem_serie_ainda_e_previsto(self):
        """O dia não acabou."""
        hoje = timezone.localdate()
        semana = streaks.calcular(self.user, hoje=hoje).semana
        de_hoje = semana[hoje.weekday()]

        if de_hoje.dia.treino_previsto and not de_hoje.dia.treino:
            self.assertEqual(de_hoje.estado_do_treino, "previsto")

    def test_a_legenda_diz_o_dia_por_extenso_e_o_estado(self):
        """A LETRA repete (S de segunda e de sábado) e some para quem ouve a
        tela. Quem carrega o significado é o texto oculto."""
        semana = streaks.calcular(self.user).semana

        self.assertIn("segunda-feira", semana[0].legenda)
        self.assertIn("/", semana[0].legenda)
        self.assertIn(semana[0].legenda.split(": ")[1], streaks.LEGENDA_DO_ESTADO.values())
        self.assertIn(
            semana[0].legenda_do_treino.split(": ")[1], streaks.LEGENDA_DO_TREINO.values()
        )

    def test_a_tela_desenha_as_duas_tiras_da_MESMA_lista(self):
        """Duas contas separadas discordariam na virada da meia-noite — e
        custariam a leitura do histórico duas vezes."""
        self.client.force_login(self.user)

        contexto = self.client.get(reverse("plans:today")).context

        self.assertIs(contexto["semana"], contexto["ofensiva"].semana)


class OHeroiRegistraNaHomeTests(TestCase):
    """O cartão AGORA deixou de ser um PONTEIRO na Home (23/09/2026).

    A razão antiga — "registrar comida a partir da Home colocaria a escolha
    entre duas receitas dentro da tela que existe para não ter escolha
    nenhuma" — continua valendo, e é por isso que o herói oferece UMA opção e
    não duas: a primeira da projeção, com "Ver refeição" ao lado para quem
    quer comparar.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        cls.user = com_plano(email="heroi-home@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)

    def _tela(self, hora=8):
        with mock.patch("plans.views.relogio", return_value=_as(hora)):
            return self.client.get(reverse("plans:today"))

    def test_o_heroi_tem_o_formulario_da_refeicao_da_vez(self):
        resposta = self._tela(hora=8)
        html = resposta.content.decode()
        slot = resposta.context["acao"].slot
        heroi = html.split('class="agora__acoes"', 1)[1].split("</section>", 1)[0]

        self.assertIn(reverse("plans:mark_meal", args=[slot.pk]), heroi)
        self.assertIn("Comi esta", heroi)

    def test_o_botao_registra_a_opcao_RECOMENDADA_do_dia(self):
        """A mesma que o card da tela de Alimentação marca como sugerida. Um
        `option` qualquer registraria uma receita que a pessoa não viu."""
        resposta = self._tela(hora=8)
        slot = resposta.context["acao"].slot
        heroi = resposta.content.decode().split('class="agora__acoes"', 1)[1]

        self.assertIn(
            'name="option" value="%d"' % slot.opcoes_do_dia[0].pk, heroi
        )

    def test_o_toque_no_heroi_registra_de_verdade(self):
        """Prova de ponta a ponta: o formulário RENDERIZADO, e não um `post`
        de dicionário — um nome de campo trocado no template passaria."""
        resposta = self._tela(hora=8)
        slot = resposta.context["acao"].slot
        opcao = slot.opcoes_do_dia[0]

        self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]),
            {"status": MealStatus.DONE, "option": opcao.pk},
        )

        registro = MealLog.objects.get(user=self.user, slot=slot, date=timezone.localdate())
        self.assertEqual(registro.status, MealStatus.DONE)
        self.assertEqual(registro.chosen_option_id, opcao.pk)

    def test_registrar_pela_Home_devolve_para_a_Home(self):
        """MEDIDO no navegador: sem o `de`, "Comi esta" na primeira dobra da
        Hoje levava para `/alimentacao/` — a pessoa registrava uma refeição e
        se via noutra tela, sem ter pedido. O destino é uma LISTA FECHADA
        (`MarkMealView.DESTINOS`), e não a URL que veio no pedido.

        ENVIA O FORMULÁRIO RENDERIZADO, e não um dicionário: a primeira
        versão deste teste passava `{"de": "hoje"}` na mão e continuava verde
        com o campo REMOVIDO do template — a sabotagem mostrou. É a armadilha
        que o `CLAUDE.md` registra como recorrente: `client.post(url, {...})`
        prova a VIEW, não a TELA.
        """
        resposta = self._tela(hora=8)
        slot = resposta.context["acao"].slot

        volta = self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]),
            _campos_do_heroi(resposta.content.decode()),
        )

        self.assertEqual(volta["Location"], reverse("plans:today"))

    def test_registrar_pelo_cardapio_continua_voltando_ao_cardapio(self):
        """Controle positivo: sem `de`, nada muda para quem toca na tela de
        Alimentação — é de lá que este botão sempre foi tocado."""
        resposta = self._tela(hora=8)
        slot = resposta.context["acao"].slot

        volta = self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]),
            {"status": MealStatus.DONE, "option": slot.opcoes_do_dia[0].pk},
        )

        self.assertIn(reverse("plans:alimentacao"), volta["Location"])

    def test_um_destino_forjado_nao_redireciona_para_fora(self):
        """`?next=` livre seria redirecionamento aberto: esta view aceita POST
        de qualquer sessão autenticada."""
        resposta = self._tela(hora=8)
        slot = resposta.context["acao"].slot

        volta = self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]),
            {
                "status": MealStatus.DONE,
                "option": slot.opcoes_do_dia[0].pk,
                "de": "https://site-de-outra-pessoa.com/",
            },
        )

        self.assertIn(reverse("plans:alimentacao"), volta["Location"])

    def test_o_heroi_nao_oferece_as_DUAS_opcoes(self):
        """Uma, e a porta para a outra. A escolha continua morando na tela de
        Alimentação."""
        heroi = self._tela(hora=8).content.decode().split('class="agora__acoes"', 1)[1].split("</section>", 1)[0]

        self.assertEqual(heroi.count('name="option"'), 1)
        self.assertIn("Ver refeição", heroi)

    def test_nao_ha_dois_verbos_para_o_mesmo_registro(self):
        """O mockup do acabamento trazia "Marcar como concluída" ao lado de
        "Ver refeição" — o MESMO registro com outro nome. Duas palavras para
        a mesma coisa é a dúvida que a pessoa resolve não tocando em
        nenhuma."""
        html = self._tela(hora=8).content.decode()

        self.assertNotIn("Marcar como concluída", html)

    def test_o_sprite_das_ilustracoes_so_entra_quando_ha_receita(self):
        """Doze desenhos para usar UM seria o oposto do que um sprite existe
        para fazer. Controle positivo junto: com receita, ele está lá."""
        com_receita = self._tela(hora=8).content.decode()
        self.assertIn('id="ilu-', com_receita)

        # Depois da última refeição do dia não há refeição pendente.
        for slot in self.user.plans.get(is_active=True).slots.all():
            MealLog.objects.update_or_create(
                user=self.user, slot=slot, date=timezone.localdate(),
                defaults={"status": MealStatus.DONE},
            )
        sem_receita = self._tela(hora=23).content.decode()

        self.assertNotIn('id="ilu-', sem_receita)
        self.assertNotIn("Comi esta", sem_receita)


class OGraficoNaoEDecorativoNaTelaTests(TestCase):
    """A régua dos três pontos, vista de fora: pela tela, não pelo módulo."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        cls.user = com_plano(email="linha-home@exemplo.com")
        perfil = cls.user.profile
        for pilar, campo in CAMPO_DO_PILAR.items():
            setattr(perfil, campo, True)
        perfil.save()

    def setUp(self):
        self.client.force_login(self.user)
        Corrida.objects.filter(user=self.user).delete()
        self._pesar(1)

    def _html(self):
        return self.client.get(reverse("plans:today")).content.decode()

    def _pesar(self, quantas):
        """EXATAMENTE `quantas` pesagens, e nunca zero.

        Zero não é um estado que esta tela alcança: sem peso
        `services.plano_do_dia` levanta `IncompleteProfile` e a Home devolve
        para o onboarding — medido, a primeira versão deste arquivo lia uma
        resposta 302 vazia e achava que a curva não estava na página. "Sem
        histórico" aqui é a pesagem do cadastro, que toda conta tem.
        """
        WeightEntry.objects.filter(user=self.user).delete()
        hoje = timezone.localdate()
        for n in range(quantas):
            WeightEntry.objects.create(
                user=self.user, date=hoje - timedelta(days=7 * n),
                weight_kg=Decimal("82.0") + n,
            )

    def _correr(self, semanas):
        hoje = timezone.localdate()
        for n in range(semanas):
            comecou = timezone.make_aware(
                datetime.combine(hoje - timedelta(days=7 * n), time(7))
            )
            Corrida.objects.create(
                user=self.user, comecou_em=comecou,
                terminou_em=comecou + timedelta(minutes=30),
                distancia_m=5000, duracao_s=1800, origem="manual",
                op_id="corrida-%d" % n,
            )

    def test_duas_pesagens_nao_desenham_curva_e_a_tela_diz_o_que_falta(self):
        self._pesar(2)

        html = self._html()

        self.assertNotIn("linha-fina--peso", html)
        self.assertIn("A curva aparece na 3ª pesagem.", html)

    def test_tres_pesagens_desenham_a_curva(self):
        """Controle positivo: sem ele, o teste acima passaria com a linha
        removida do template."""
        self._pesar(3)

        self.assertIn("linha-fina--peso", self._html())

    def test_uma_corrida_nao_desenha_linha(self):
        """`semanas_com_km` devolve OITO baldes sempre, então `desenhar`
        receberia oito pontos e aceitaria qualquer histórico: uma reta no
        chão com um pico no fim. A régua conta SEMANAS COM CORRIDA."""
        self._correr(1)

        html = self._html()

        self.assertNotIn("linha-fina--corrida", html)
        self.assertIn("A linha aparece com 3 semanas", html)

    def test_tres_semanas_com_corrida_desenham_a_linha(self):
        self._correr(3)

        self.assertIn("linha-fina--corrida", self._html())

    def test_sem_historico_o_cartao_convida_em_vez_de_desenhar(self):
        """O primeiro dia: a pesagem do cadastro e nenhuma corrida."""
        html = self._html()

        self.assertNotIn("linha-fina", html)
        self.assertIn("A curva aparece na 3ª pesagem.", html)
        self.assertIn("Nenhuma corrida registrada", html)
        self.assertIn("Grave a primeira com o GPS", html)


class OCabecalhoNaoInventaTests(TestCase):
    """Sem declaração, sem personalização — inclusive no acabamento novo."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)
        cls.user = com_plano(email="neutra@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)

    def test_quem_nao_declarou_area_nao_recebe_selo(self):
        perfil = self.user.profile
        perfil.prioridade = ""
        for campo in CAMPO_DO_PILAR.values():
            setattr(perfil, campo, False)
        perfil.save()

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertNotIn("painel__selo", html)
        self.assertIn("painel__cartao", html)

    def test_a_area_declarada_recebe_o_selo(self):
        """Controle positivo do teste acima."""
        perfil = self.user.profile
        perfil.prioridade = Pilar.TREINO
        setattr(perfil, CAMPO_DO_PILAR[Pilar.TREINO], True)
        perfil.save()

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn("painel__selo", html)

    def test_nenhuma_frase_de_animo_entrou_com_o_acabamento(self):
        """O mockup punha uma linha de efeito ao lado de cada número. O que
        entrou no lugar foi o fato que contextualiza o número — e esta régua
        existe para a próxima rodada de polimento não trazer as frases de
        volta."""
        html = self.client.get(reverse("plans:today")).content.decode()

        for frase in (
            "Consistência é tudo",
            "Mova seu corpo",
            "Constância gera resultados",
            "Mantenha-se bem hoje",
            "Um dia de cada vez",
            "PEQUENAS ESCOLHAS",
            "HOJE CONSTRÓI",
        ):
            with self.subTest(frase=frase):
                self.assertNotIn(frase, html)
