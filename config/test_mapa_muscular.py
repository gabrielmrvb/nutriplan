# -*- coding: utf-8 -*-
"""O mapa muscular: três níveis, duas vistas, e nenhum grupo esquecido.

O que este arquivo protege, e por que cada coisa pode dar errado sozinha:

**Os três níveis têm de ser TRÊS.** Principal a 100%, auxiliar a 50% e neutro
sem tinta só valem se der para distinguir os três numa olhada — duas cores
quase iguais fazem sentido para quem escreveu o CSS e para mais ninguém. Cor
não se julga: `OContrasteDosTresNiveisTests` calcula as distâncias WCAG a
partir dos tokens dos dois temas, com controle positivo, e a porcentagem sai
do CSS em vez de ser reescrita aqui. Esta frase já esteve neste arquivo sem
nenhuma conta atrás dela; uma revisão adversarial cobrou a promessa.

**E não podem depender só de cor.** Quem não distingue verde de cinza precisa
ler o mesmo mapa, então a espessura da borda carrega a mesma informação —
2px, 1px, nenhuma.

**Nenhum grupo pode ficar sem desenho em silêncio.** Um `MuscleGroup` novo sem
região apagaria a informação sem ninguém notar, e é isso que o teste de
cobertura impede — ele reprova quando alguém acrescenta um grupo e esquece o
mapa.

**E o mapa e a tabela de vistas não podem divergir.** O desenho mora no SVG e
a tabela de vistas mora em `workouts/anatomia.py`; são dois lugares porque o
Python precisa saber a vista para escolher qual abrir, e só. Um teste compara
os dois, para que desenhar uma região e esquecer a tabela fique vermelho.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from config.tests import _contraste, _tokens
from workouts import anatomia
from workouts.models import Exercise, MuscleGroup

RAIZ = Path(__file__).resolve().parent.parent
SVG = RAIZ / "templates" / "partials" / "mapa_muscular.html"
CSS = RAIZ / "static" / "css" / "app.css"


def regioes_do_svg():
    """grupo -> quantas regiões ele tem desenhadas, por vista.

    Lê o SVG de verdade em vez de repetir a lista: o desenho é a fonte, e uma
    segunda cópia aqui divergiria dele na primeira região nova.
    """
    fonte = SVG.read_text(encoding="utf-8")
    # As duas vistas são os dois `<g class="corpo__vista">`.
    vistas = fonte.split('<g class="corpo__vista">')[1:]
    assert len(vistas) == 2, "o SVG deixou de ter duas vistas"

    saida = {anatomia.FRENTE: {}, anatomia.COSTAS: {}}
    for nome, trecho in zip((anatomia.FRENTE, anatomia.COSTAS), vistas):
        # `[a-z_0-9]+` e não `[a-z]+`: os onze slugs de hoje são só letras, mas
        # um `lower_back` desenhado CORRETAMENTE faria a trava de cobertura
        # reprovar por engano, e a trava do slug inexistente ficaria cega para
        # ele. Buraco latente que uma revisão adversarial apontou.
        for grupo in re.findall(r'data-grupo="([a-z_0-9]+)"', trecho):
            saida[nome][grupo] = saida[nome].get(grupo, 0) + 1
    return saida


class ACoberturaDaTaxonomiaTests(SimpleTestCase):
    """A dívida que este teste existe para impedir: um grupo novo sem desenho."""

    def test_todo_grupo_da_taxonomia_tem_regiao_desenhada(self):
        desenhados = set()
        for vista in regioes_do_svg().values():
            desenhados |= set(vista)

        faltando = {g.value for g in MuscleGroup} - desenhados

        self.assertEqual(
            faltando,
            set(),
            "grupo sem região no mapa: acrescente o desenho ou declare o "
            "fallback de propósito",
        )

    def test_o_svg_nao_desenha_grupo_que_nao_existe(self):
        """O outro lado: uma região com slug errado nunca acenderia, e ninguém
        notaria — ela simplesmente ficaria neutra para sempre."""
        desenhados = set()
        for vista in regioes_do_svg().values():
            desenhados |= set(vista)

        sobrando = desenhados - {g.value for g in MuscleGroup}

        self.assertEqual(sobrando, set(), "região com grupo inexistente")

    def test_a_tabela_de_vistas_bate_com_o_desenho(self):
        """Duas fontes que precisam concordar, e um teste que as compara.

        `anatomia.VISTAS_POR_GRUPO` existe porque o Python precisa escolher a
        vista inicial; o desenho é quem tem as regiões. Desenhar o tríceps de
        frente e esquecer a tabela — ou o contrário — deixaria a escolha da
        vista mentindo sobre o que a pessoa vai ver.
        """
        do_svg = regioes_do_svg()
        for grupo in MuscleGroup:
            com_desenho = {
                vista for vista, mapa in do_svg.items() if grupo.value in mapa
            }
            with self.subTest(grupo=grupo.value):
                self.assertEqual(
                    com_desenho,
                    set(anatomia.vistas_do_grupo(grupo)),
                    "a tabela de vistas divergiu do SVG",
                )

    def test_a_ordem_das_vistas_e_comportamento_e_esta_travada(self):
        """A tupla é ORDENADA, e `do_principal[0]` é o desempate final.

        O teste de cobertura compara `set()`, então inverter
        `TRAPS: (COSTAS, FRENTE)` para `(FRENTE, COSTAS)` passava verde e
        mudava em silêncio a vista em que o encolhimento abre. Só o ombro
        tinha trava; os três grupos de vista dupla passam a ter.
        """
        esperado = {
            MuscleGroup.SHOULDERS: (anatomia.FRENTE, anatomia.COSTAS),
            MuscleGroup.FOREARMS: (anatomia.FRENTE, anatomia.COSTAS),
            # O trapézio se lê de costas: de frente ele é uma faixa fina no
            # pescoço, de costas é o losango inteiro.
            MuscleGroup.TRAPS: (anatomia.COSTAS, anatomia.FRENTE),
        }
        for grupo, ordem in esperado.items():
            with self.subTest(grupo=grupo.value):
                self.assertEqual(anatomia.vistas_do_grupo(grupo), ordem)

    def test_o_svg_tem_exatamente_duas_vistas(self):
        """O CSS separa as vistas por `:first-of-type`/`:last-of-type` e este
        arquivo por posição no `split`. Um terceiro `<g class="corpo__vista">`
        — uma legenda, uma moldura — quebraria a regra de CSS em silêncio."""
        fonte = SVG.read_text(encoding="utf-8")

        self.assertEqual(fonte.count('<g class="corpo__vista">'), 2)

    def test_um_grupo_pode_ter_varias_regioes(self):
        """A arquitetura aceita 1 grupo → N regiões, e o desenho usa isso: o
        peito são dois peitorais, o quadríceps são duas coxas."""
        frente = regioes_do_svg()[anatomia.FRENTE]

        self.assertGreaterEqual(frente["chest"], 2)
        self.assertGreaterEqual(frente["quads"], 2)


class OsTresNiveisTests(SimpleTestCase):
    """Principal, auxiliar e neutro têm de ser três coisas distinguíveis."""

    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")

    def regra(self, seletor):
        achado = re.search(
            re.escape(seletor) + r"\s*\{([^}]*)\}", self.css
        )
        self.assertIsNotNone(achado, "regra ausente: %s" % seletor)
        return achado.group(1)

    def test_o_auxiliar_esta_na_faixa_de_40_a_60(self):
        """A faixa é decisão do dono. 50 é o meio, e o meio é escolha: 40
        aproxima o auxiliar do neutro, 60 o aproxima do principal."""
        corpo = self.regra('.corpo__musculo[data-nivel="auxiliar"]')
        achado = re.search(r"var\(--brand\)\s+(\d+)%", corpo)

        self.assertIsNotNone(achado, "o auxiliar deixou de sair de --brand")
        self.assertGreaterEqual(int(achado.group(1)), 40)
        self.assertLessEqual(int(achado.group(1)), 60)

    def test_o_principal_usa_a_marca_cheia(self):
        corpo = self.regra('.corpo__musculo[data-nivel="principal"]')

        self.assertIn("fill: var(--brand);", corpo)

    def test_o_neutro_nao_tem_tinta_da_marca(self):
        corpo = self.regra(".corpo__musculo")

        self.assertNotIn("--brand", corpo)
        self.assertIn("var(--surface-3)", corpo)

    def test_o_nivel_nao_depende_so_de_cor(self):
        """A espessura da borda carrega a mesma informação — 2, 1 e 0.

        Sem isto, quem não distingue verde de cinza teria um mapa em que
        principal e auxiliar são a mesma mancha.
        """
        larguras = []
        for seletor in (
            '.corpo__musculo[data-nivel="principal"]',
            '.corpo__musculo[data-nivel="auxiliar"]',
            ".corpo__musculo",
        ):
            corpo = self.regra(seletor)
            achado = re.search(r"stroke-width:\s*(\d+)", corpo)
            self.assertIsNotNone(achado, "sem borda declarada: %s" % seletor)
            larguras.append(int(achado.group(1)))

        self.assertEqual(len(set(larguras)), 3, larguras)
        self.assertEqual(larguras, sorted(larguras, reverse=True), larguras)

    def test_nenhum_hex_solto_no_mapa(self):
        """O sistema visual é de tokens; uma paleta paralela aqui seria a
        segunda fonte de cor do app — e o tema claro deixaria de acompanhar.

        Comentário sai antes de procurar: este projeto comenta muito, e o
        comentário desta seção cita `#hex` justamente para dizer que não usa.
        A primeira versão deste teste ficou vermelha por causa disso.
        """
        secao = self.css.split("47. Treino V4 fase B", 1)[1]
        # Da abertura da seção até o próximo cabeçalho numerado, ou o fim.
        proxima = re.search(r"\n\s+\d+\.\s+\S", secao)
        if proxima:
            secao = secao[: proxima.start()]
        sem_comentario = re.sub(r"/\*.*?\*/", "", secao, flags=re.S)

        self.assertGreater(len(sem_comentario), 800, "o recorte da seção falhou")
        self.assertIn("corpo__musculo", sem_comentario, "recorte errado")
        self.assertEqual(
            re.findall(r"#[0-9a-fA-F]{3,8}\b", sem_comentario),
            [],
            "cor crua na seção do mapa",
        )


def _mistura(cor, fundo, pct):
    """`color-mix(in srgb, cor pct%, fundo)` em sRGB, para conta de contraste.

    O CSS mistura em sRGB por pedido explícito (`in srgb`), então a conta aqui
    é a mesma que o navegador faz: componente a componente, sem gama. Medido
    no Chrome, o auxiliar do tema escuro computa
    `color(srgb 0.1 0.439216 0.352941)` — que é exatamente o que esta função
    devolve para 50% de `#10b981` sobre `#232733`.
    """
    a = [int(cor.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    b = [int(fundo.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    p = pct / 100
    return "#%02x%02x%02x" % tuple(
        round(a[i] * p + b[i] * (1 - p)) for i in range(3)
    )


class OContrasteDosTresNiveisTests(SimpleTestCase):
    """As distâncias de cor, CALCULADAS — porque três lugares prometiam isso.

    O comentário do SVG, o da seção 47 e o cabeçalho deste arquivo diziam "o
    contraste é medido em `config/test_mapa_muscular.py`". Não era: a primeira
    versão conferia de onde o `fill` saía e que a porcentagem estava na faixa,
    o que não é distância nenhuma. Uma revisão adversarial pegou a promessa sem
    a conta — o pior dos estados, porque quem lê confia.

    E O RESULTADO NÃO É REDONDO, então fica escrito com todas as letras:

    - **principal × neutro**, que é a pergunta que importa — "este exercício
      trabalha este músculo?" —, dá 5,87:1 no escuro e 5,39:1 no claro. Passa
      folgado o 3:1 que a WCAG 1.4.11 pede de elemento gráfico significativo.
    - **principal × auxiliar**, que é questão de GRAU, dá 2,36:1 e 2,51:1.
      Fica ABAIXO de 3:1, e não dá para consertar dentro da faixa de 40–60%
      que o dono fixou: o auxiliar teria de escurecer para perto de 30% para
      alcançar 3:1 contra o principal, e aí colaria no neutro.

    A mitigação é declarada e tem teste próprio (`test_o_nivel_nao_depende_so_de_cor`):
    a espessura da borda diz a mesma coisa sem cor nenhuma — 2px, 1px, zero.
    Estas asserções travam os pisos que os valores REALMENTE cumprem, para que
    um ajuste de token não derrube nenhum dos três sem ninguém ver.

    E A CONTA DERRUBOU AS PONTAS DA FAIXA. Varrida de 5 em 5 sobre os tokens
    dos dois temas (principal×auxiliar / auxiliar×neutro):

        %     escuro          claro
        40    2,88  2,04      2,96  1,82   <- o auxiliar cola no neutro
        45    2,59  2,27      2,74  1,97   <- idem, por pouco
        50    2,36  2,49      2,50  2,16
        55    2,15  2,73      2,30  2,35
        60    1,95  3,02      2,11  2,56   <- o auxiliar cola no principal

    Nos DOIS temas juntos, só 50 e 55 mantêm os três níveis a 2:1 ou mais um
    do outro. Ou seja: 50 não é "o meio da faixa" por simetria — é um dos dois
    valores da faixa que funcionam, e o comentário do SVG dizia a coisa fraca.
    A faixa de 40–60 continua sendo a decisão do dono; o que este arquivo
    acrescenta é que ela tem pontas que não entregam três níveis.
    """

    def setUp(self):
        css = CSS.read_text(encoding="utf-8")
        self.temas = {
            "escuro": _tokens(css, ":root {"),
            "claro": _tokens(css, "@media (prefers-color-scheme: light) {"),
        }
        # A PORCENTAGEM SAI DO CSS, e isso é o teste medir a coisa em vez de
        # medir uma hipótese. A primeira versão escrevia `50` à mão aqui: uma
        # sabotagem que baixou o auxiliar para 30% no CSS — encostando ele no
        # neutro — passou pelas três asserções de contraste sem piscar, porque
        # elas continuavam calculando a mistura de 50.
        regra = re.search(
            r'\.corpo__musculo\[data-nivel="auxiliar"\]\s*\{([^}]*)\}', css
        )
        self.assertIsNotNone(regra, "a regra do auxiliar sumiu")
        achado = re.search(r"var\(--brand\)\s+(\d+)%", regra.group(1))
        self.assertIsNotNone(achado, "o auxiliar deixou de sair de --brand")
        self.pct = int(achado.group(1))

    def niveis(self, tema):
        t = self.temas[tema]
        return (
            t["--brand"],
            _mistura(t["--brand"], t["--surface-3"], self.pct),
            t["--surface-3"],
        )

    def test_o_controle_positivo_da_21(self):
        """Sem ele, uma conta quebrada devolveria números bonitos e falsos."""
        self.assertEqual(round(_contraste("#000000", "#ffffff"), 2), 21.0)

    def test_trabalhado_e_nao_trabalhado_passam_o_3_para_1(self):
        for tema in self.temas:
            principal, _, neutro = self.niveis(tema)
            with self.subTest(tema=tema):
                self.assertGreaterEqual(
                    round(_contraste(principal, neutro), 2), 3.0
                )

    def test_os_tres_niveis_sao_tres_e_nao_dois(self):
        """Piso baixo de propósito: 2:1 é o que os valores cumprem, e o que
        impede alguém de aproximar dois níveis a ponto de virarem um."""
        for tema in self.temas:
            principal, auxiliar, neutro = self.niveis(tema)
            with self.subTest(tema=tema):
                self.assertGreaterEqual(
                    round(_contraste(principal, auxiliar), 2), 2.0
                )
                self.assertGreaterEqual(
                    round(_contraste(auxiliar, neutro), 2), 2.0
                )

    def test_a_porcentagem_escolhida_e_uma_que_funciona_nos_dois_temas(self):
        """A trava do RACIOCÍNIO, e não do número.

        Ela varre a faixa que o dono fixou, descobre quais valores mantêm os
        três níveis separados nos dois temas, e exige que o CSS use um deles.
        Se alguém trocar um token de cor e isso mudar o conjunto, o teste
        reprova dizendo qual é o conjunto novo — em vez de repetir "50" para
        sempre sem saber mais por quê.
        """
        funcionam = []
        for pct in range(40, 61):
            ok = True
            for tema, t in self.temas.items():
                auxiliar = _mistura(t["--brand"], t["--surface-3"], pct)
                ok = ok and _contraste(t["--brand"], auxiliar) >= 2.0
                ok = ok and _contraste(auxiliar, t["--surface-3"]) >= 2.0
            if ok:
                funcionam.append(pct)

        self.assertIn(
            self.pct,
            funcionam,
            "o auxiliar está em %d%%, e nesta paleta só %s mantêm os três "
            "níveis a 2:1 nos dois temas" % (self.pct, funcionam),
        )

    def test_o_auxiliar_fica_no_meio_e_nao_num_dos_extremos(self):
        """Um auxiliar mais perto de um lado que do outro seria, na prática,
        aquele lado. Medido: 2,36 contra 2,49 no escuro."""
        for tema in self.temas:
            principal, auxiliar, neutro = self.niveis(tema)
            de_cima = _contraste(principal, auxiliar)
            de_baixo = _contraste(auxiliar, neutro)
            with self.subTest(tema=tema):
                self.assertLess(
                    max(de_cima, de_baixo) / min(de_cima, de_baixo),
                    1.6,
                    "o auxiliar encostou num dos extremos: %.2f e %.2f"
                    % (de_cima, de_baixo),
                )


class OQuadroCercaUmCorpoSoTests(SimpleTestCase):
    """O `viewBox` não pode voltar a enquadrar as DUAS vistas.

    Medido no drawer a 390px com o quadro largo: SVG de 240×273 com o boneco
    em 73×206 — 30% da largura era a outra vista, escondida, e 24% da altura
    era o vazio abaixo dos pés. Como um corpo em pé é alto e estreito, é a
    ALTURA que limita o tamanho do desenho; sobrar altura é sobrar nada.

    Depois do aperto, e já com o teto em `vh` que a regressão de altura
    obrigou a pôr: 98×253 de quadro com o boneco em 78×223 a 390×844 — 8%
    mais alto que os 206 originais, com o cartão de séries no mesmo lugar.

    O comentário do próprio SVG diz que um boneco pequeno não mostra onde fica
    o tríceps. Este teste é o que impede o desenho de contradizê-lo de novo.
    """

    def test_o_viewbox_nao_cabe_nas_duas_vistas(self):
        # O comentário do arquivo CITA o viewBox antigo, para explicar por que
        # ele mudou — e a primeira versão deste teste leu a citação em vez do
        # atributo, reprovando com "220" num arquivo que já dizia 83. É a
        # armadilha que o CLAUDE.md descreve: o comentário fala da coisa que a
        # asserção procura.
        fonte = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
            "",
            SVG.read_text(encoding="utf-8"),
            flags=re.S,
        )
        achado = re.search(r'viewBox="([\d.\s-]+)"', fonte)
        self.assertIsNotNone(achado, "o SVG perdeu o viewBox")
        _, _, largura, altura = [float(n) for n in achado.group(1).split()]

        # As duas vistas estão a 110 unidades uma da outra no mesmo sistema de
        # coordenadas; um quadro que alcance as duas é o quadro largo de volta.
        self.assertLess(largura, 110, "o quadro voltou a enquadrar dois corpos")
        self.assertGreater(largura, 67, "o quadro cortou o corpo pelos lados")
        # O corpo vai de y=8 a y=197. A legenda saiu do SVG (texto ali escala
        # com o `viewBox` e caía abaixo do piso de 11px), então o quadro
        # termina logo depois dos pés em vez de reservar espaço para ela.
        self.assertLess(altura, 215, "sobrou vazio abaixo dos pés")
        self.assertGreater(altura, 197, "o quadro cortou os pés")

    def test_a_legenda_da_vista_nao_mora_dentro_do_svg(self):
        """Texto em SVG escala com o `viewBox`, e o teto de altura faz o fator
        variar: a 320×568 ele é 0,79, e os 11,2px do token viravam 8,9px na
        tela — abaixo do piso de 11px que o CLAUDE.md fixa. A régua de tipo do
        projeto mede o TOKEN, então ela não via isto."""
        fonte = SVG.read_text(encoding="utf-8")
        sem_comentario = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", fonte, flags=re.S
        )

        self.assertNotIn("<text", sem_comentario)

    def test_a_altura_e_quem_manda_no_css(self):
        """Com o quadro estreito, largura-primeiro daria 240×621 e o boneco
        empurraria séries, descanso e carga para fora da tela."""
        css = CSS.read_text(encoding="utf-8")
        achado = re.search(r"\n\.corpo \{([^}]*)\}", css)
        self.assertIsNotNone(achado, "a regra .corpo sumiu")
        corpo = achado.group(1)

        altura = re.search(r"height:\s*([^;]+);", corpo)
        self.assertIsNotNone(altura, "sem altura declarada")
        self.assertNotIn("auto", altura.group(1))
        self.assertIn("width: auto", corpo)


class AVistaPreferidaTests(TestCase):
    """Abrir na vista que informa, sem obrigar ninguém a virar o boneco."""

    def exercicio(self, principal, auxiliares=()):
        return Exercise(
            name="Teste vista",
            muscle_group=principal,
            equipment="machine",
            secondary_muscles=list(auxiliares),
        )

    def test_principal_da_frente_abre_de_frente(self):
        alvo = self.exercicio(MuscleGroup.CHEST, ["triceps", "shoulders"])

        self.assertEqual(anatomia.vista_preferida(alvo), anatomia.FRENTE)

    def test_principal_das_costas_abre_de_costas(self):
        """O caso que o pedido nomeia: puxada não pode abrir de frente e
        deixar a pessoa procurar onde está o dorsal."""
        alvo = self.exercicio(MuscleGroup.BACK, ["biceps", "forearms"])

        self.assertEqual(anatomia.vista_preferida(alvo), anatomia.COSTAS)

    def test_principal_sem_auxiliar_abre_na_vista_dele(self):
        alvo = self.exercicio(MuscleGroup.CALVES)

        self.assertEqual(anatomia.vista_preferida(alvo), anatomia.COSTAS)

    def test_principal_nas_duas_vistas_deixa_os_auxiliares_decidirem(self):
        """Ombro tem massa dos dois lados: quem desempata é onde está o resto
        do trabalho."""
        para_tras = self.exercicio(MuscleGroup.SHOULDERS, ["back", "triceps"])
        para_frente = self.exercicio(MuscleGroup.SHOULDERS, ["chest", "biceps"])

        self.assertEqual(anatomia.vista_preferida(para_tras), anatomia.COSTAS)
        self.assertEqual(anatomia.vista_preferida(para_frente), anatomia.FRENTE)

    def test_empate_cai_na_preferencia_declarada_do_grupo(self):
        alvo = self.exercicio(MuscleGroup.SHOULDERS, ["chest", "back"])

        self.assertEqual(anatomia.vista_preferida(alvo), anatomia.FRENTE)

    def test_grupo_sem_desenho_nao_quebra_a_escolha(self):
        """Fallback declarado: um grupo futuro sem região ainda devolve uma
        vista, e a tela continua de pé."""
        alvo = self.exercicio("um_grupo_que_nao_existe")

        self.assertIn(
            anatomia.vista_preferida(alvo), (anatomia.FRENTE, anatomia.COSTAS)
        )


class OsDestaquesSaemDoDadoTests(TestCase):
    def exercicio(self, principal, auxiliares=()):
        return Exercise(
            name="Teste destaque",
            muscle_group=principal,
            equipment="machine",
            secondary_muscles=list(auxiliares),
        )

    def test_so_o_principal(self):
        alvo = self.exercicio(MuscleGroup.CALVES)

        self.assertEqual(anatomia.destaques(alvo), {"calves": "principal"})

    def test_principal_e_um_auxiliar(self):
        alvo = self.exercicio(MuscleGroup.BICEPS, ["forearms"])

        self.assertEqual(
            anatomia.destaques(alvo),
            {"biceps": "principal", "forearms": "auxiliar"},
        )

    def test_principal_e_varios_auxiliares(self):
        alvo = self.exercicio(MuscleGroup.QUADS, ["hamstrings", "core"])

        self.assertEqual(
            anatomia.destaques(alvo),
            {"quads": "principal", "hamstrings": "auxiliar", "core": "auxiliar"},
        )

    def test_o_principal_nunca_e_rebaixado_a_auxiliar(self):
        """`clean()` já proíbe repetir, e esta é a segunda camada: o seed e o
        `shell` escrevem sem validar."""
        alvo = self.exercicio(MuscleGroup.CHEST, ["chest", "triceps"])

        self.assertEqual(anatomia.destaques(alvo)["chest"], "principal")

    def test_a_string_do_atributo_e_legivel_pelo_javascript(self):
        alvo = self.exercicio(MuscleGroup.CHEST, ["triceps"])

        texto = alvo.destaques_anatomicos

        self.assertIn("chest:principal", texto)
        self.assertIn("triceps:auxiliar", texto)
        self.assertNotIn(" ", texto)


class OsCincoExerciciosRepresentativosTests(TestCase):
    """Os casos que o pedido nomeia, contra o catálogo de verdade."""

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_workouts", verbosity=0)

    def test_cada_um_abre_na_vista_certa_com_os_musculos_certos(self):
        esperado = {
            "Supino reto com barra": (
                anatomia.FRENTE, "chest", {"triceps", "shoulders"}
            ),
            "Puxada frente na polia": (
                anatomia.COSTAS, "back", {"biceps", "forearms"}
            ),
            "Agachamento livre": (
                anatomia.FRENTE, "quads", {"hamstrings", "core"}
            ),
            "Panturrilha em pé": (anatomia.COSTAS, "calves", set()),
            "Rosca direta com barra": (anatomia.FRENTE, "biceps", {"forearms"}),
        }
        for nome, (vista, principal, auxiliares) in esperado.items():
            with self.subTest(exercicio=nome):
                alvo = Exercise.objects.get(name=nome)
                niveis = anatomia.destaques(alvo)

                self.assertEqual(anatomia.vista_preferida(alvo), vista)
                self.assertEqual(niveis[principal], "principal")
                self.assertEqual(
                    {g for g, n in niveis.items() if n == "auxiliar"}, auxiliares
                )

    def test_todo_exercicio_do_catalogo_tem_mapa(self):
        """Nenhum dos 36 pode cair num estado sem desenho."""
        for alvo in Exercise.objects.all():
            with self.subTest(exercicio=alvo.name):
                niveis = anatomia.destaques(alvo)
                self.assertTrue(niveis)
                self.assertIn(
                    anatomia.vista_preferida(alvo),
                    (anatomia.FRENTE, anatomia.COSTAS),
                )


class OGatilhoRenderizadoTests(TestCase):
    """O VALOR do atributo, na página de verdade — não a palavra no template.

    Este era o buraco entre dois testes que passavam: um media
    `destaques_anatomicos` isolado no modelo, o outro procurava a string
    `data-destaques=` no código-fonte do template. Nenhum dos dois olhava o
    HTML que o servidor emite.

    O caminho concreto que escapava: se `destaques_anatomicos` passasse a
    devolver `""` — exceção engolida, `secondary_muscles` malformado, refactor
    no `Exercise` —, o template emitiria `data-destaques=""`, `temAnatomia`
    devolveria `false`, o botão "Anatomia" nunca apareceria e o mapa ficaria
    INALCANÇÁVEL, com a suíte inteira verde.

    É a lição que `workouts/test_treino_v4.py` já tinha registrado por escrito
    para `data-auxiliares`, e que a fase B não aplicou ao campo novo. Uma
    revisão adversarial cobrou.
    """

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        # O mesmo helper que o resto da suíte de treino usa: perfil completo,
        # três dias e horário. Montar o usuário à mão aqui já custou um
        # `NotNullViolation` em `start_time`.
        from workouts.tests import create_user

        call_command("seed_workouts", verbosity=0)
        cls.user = create_user(email="mapa@exemplo.com")

    def setUp(self):
        from workouts import services

        self.client.force_login(self.user)
        services.sync_active_routine(self.user)
        self.html = self.client.get(reverse("workouts:routine")).content.decode()

    def gatilho(self, nome):
        """O trecho do `<button>` daquele exercício, e nada além dele.

        Ancorar no nome e recortar até o fim da tag é o que impede a asserção
        de casar com outro exercício da mesma ficha — a armadilha registrada no
        CLAUDE.md, aqui com 27 gatilhos na página para casar por acidente.
        """
        marca = 'data-nome="%s"' % nome
        self.assertIn(marca, self.html, "exercício fora da ficha: %s" % nome)
        antes = self.html.rindex("<button", 0, self.html.index(marca))
        return self.html[antes : self.html.index(">", self.html.index(marca))]

    def test_o_valor_de_destaques_chega_montado_na_pagina(self):
        botao = self.gatilho("Supino reto com barra")

        self.assertIn(
            'data-destaques="chest:principal,triceps:auxiliar,shoulders:auxiliar"',
            botao,
        )

    def test_o_valor_da_vista_chega_na_pagina(self):
        self.assertIn('data-vista="frente"', self.gatilho("Supino reto com barra"))

    def test_a_vista_de_cada_gatilho_mostra_o_musculo_principal(self):
        """A propriedade que importa, conferida contra O DESENHO.

        Uma sabotagem que fixava `vista_anatomica` em `"frente"` passou verde:
        os testes de `vista_preferida` chamam a função direto, e o único
        gatilho conferido na página era o do supino — que abre de frente de
        qualquer jeito. Um exercício de costas nunca era olhado, e a fiação
        propriedade → template ficava sem cobertura para metade dos valores.

        Aqui a asserção não pergunta à tabela de vistas (seria a mesma fonte
        respondendo a si mesma): ela pergunta ao SVG se o grupo principal tem
        região desenhada NAQUELA vista. É o que "abrir na vista que informa"
        quer dizer, e é verificável de fora.
        """
        do_svg = regioes_do_svg()
        vistos = set()

        for trecho in re.findall(r"<button[^>]*exercise__ver[^>]*>", self.html):
            nome = re.search(r'data-nome="([^"]*)"', trecho).group(1)
            vista = re.search(r'data-vista="([^"]*)"', trecho).group(1)
            principal = Exercise.objects.get(name=nome).muscle_group
            vistos.add(vista)
            with self.subTest(exercicio=nome):
                self.assertIn(
                    principal,
                    do_svg[vista],
                    "%s abre em '%s', onde o %s não está desenhado"
                    % (nome, vista, principal),
                )

        # Sem isto, uma ficha que só tivesse exercícios de frente deixaria a
        # varredura acima passar sem nunca exercitar o outro valor.
        self.assertEqual(vistos, {anatomia.FRENTE, anatomia.COSTAS}, vistos)

    def test_um_isolador_publica_so_o_principal(self):
        botao = self.gatilho("Elevação lateral com halteres")
        valor = re.search(r'data-destaques="([^"]*)"', botao).group(1)

        # O VALOR, e não o botão inteiro: `data-auxiliares` é outro atributo do
        # mesmo gatilho, e a palavra "auxiliar" está dentro do NOME dele. A
        # primeira versão deste teste reprovou por isso.
        self.assertEqual(valor, "shoulders:principal")

    def test_nenhum_gatilho_da_pagina_sai_com_o_campo_vazio(self):
        """A varredura que fecha o buraco: um só vazio já esconde o botão
        "Anatomia" daquele exercício, e um teste por exemplo não veria."""
        vazios = re.findall(r'data-destaques=""', self.html)

        self.assertEqual(vazios, [], "gatilho sem destaques na ficha")
        self.assertEqual(re.findall(r'data-vista=""', self.html), [])

    def test_todo_gatilho_tem_os_dois_campos(self):
        # `class="exercise__ver"` e não `data-ver`: este é um prefixo de
        # `data-vertical`, que mora no mesmo botão — contar a string curta
        # devolvia 56 para 27 gatilhos.
        gatilhos = self.html.count('class="exercise__ver"')

        self.assertGreater(gatilhos, 0, "a ficha não tem exercício nenhum")
        self.assertEqual(self.html.count("data-destaques="), gatilhos)
        self.assertEqual(self.html.count("data-vista="), gatilhos)

    def test_cada_botao_do_seletor_aponta_a_regiao_que_ele_revela(self):
        """`aria-controls` tem de nomear o que APARECE, não o que some.

        O botão "Anatomia" apontava `drawer-media` — justamente a caixa que
        fica `hidden` quando ele é pressionado —, e o bloco que aparece não
        tinha `id` nenhum. Para tecnologia assistiva, o botão declarava
        controlar uma região que desaparece. Uma revisão pegou; a correção não
        tinha trava, e voltar atrás passava verde.
        """
        for midia, alvo in (("execucao", "drawer-media"), ("anatomia", "drawer-anatomia")):
            with self.subTest(midia=midia):
                botao = re.search(
                    r'<button[^>]*data-drawer-midia="%s"[^>]*>' % midia, self.html
                )
                self.assertIsNotNone(botao, "botão do seletor sumiu: %s" % midia)
                self.assertIn('aria-controls="%s"' % alvo, botao.group(0))
                self.assertIn('id="%s"' % alvo, self.html, "a região perdeu o id")

    def test_a_url_de_animacao_saiu_do_html_da_ficha(self):
        """`data-animacao` carregava a URL de embed completa em cada um dos 27
        gatilhos, e o único leitor dela morreu na fase B.

        A asserção é sobre os GATILHOS e não sobre a página: o comentário do
        JavaScript que explica a remoção cita o nome do atributo, e o
        JavaScript é servido junto com o HTML. Procurar na página inteira
        reprovava por causa da própria explicação.
        """
        botoes = re.findall(r"<button[^>]*exercise__ver[^>]*>", self.html)

        # Sem isto o laço vazio passaria verde — e passaria também no dia em
        # que a regex parasse de casar por outro motivo qualquer.
        self.assertGreater(len(botoes), 20, "a regex do gatilho parou de casar")
        for trecho in botoes:
            with self.subTest(gatilho=trecho[:60]):
                self.assertNotIn("data-animacao", trecho)
                self.assertIn("data-destaques", trecho)


class OMapaNaoCustaConsultaTests(TestCase):
    """Nenhuma consulta nova por exercício — provado, não afirmado.

    O risco concreto de uma tela que ganha dois campos calculados: se
    `destaques_anatomicos` ou `vista_anatomica` tocassem uma relação, a ficha
    da semana faria uma consulta por exercício. São 27 na ficha de três dias e
    63 na de sete — um N+1 clássico, e invisível em desenvolvimento.

    Os dois leem só `muscle_group` e `secondary_muscles`, que são colunas do
    próprio `Exercise`. `assertNumQueries(0)` é a prova de que continuam assim:
    trocar `secondary_muscles` por uma tabela relacionada deixaria este teste
    vermelho no mesmo commit.
    """

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        from workouts.tests import create_user

        call_command("seed_workouts", verbosity=0)
        cls.user = create_user(email="consulta@exemplo.com")

    def test_os_dois_campos_novos_nao_consultam_nada(self):
        from workouts import services

        plano, _ = services.sync_active_routine(self.user)
        itens = list(
            type(plano)
            .objects.get(pk=plano.pk)
            .sessions.prefetch_related("exercises__exercise")
            .all()
        )
        # Materializa tudo ANTES de contar: o que se mede é o custo dos dois
        # campos, não o de carregar a ficha.
        exercicios = [
            item.exercise for sessao in itens for item in sessao.exercises.all()
        ]
        self.assertGreater(len(exercicios), 10)

        with self.assertNumQueries(0):
            for exercicio in exercicios:
                exercicio.destaques_anatomicos
                exercicio.vista_anatomica

    def test_a_ficha_inteira_nao_ganhou_consulta_por_exercicio(self):
        """O outro lado: contar as consultas da PÁGINA e provar que o número
        não acompanha a quantidade de exercícios."""
        from workouts import services

        services.sync_active_routine(self.user)
        self.client.force_login(self.user)

        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as capturadas:
            html = self.client.get(reverse("workouts:routine")).content.decode()

        gatilhos = html.count('class="exercise__ver"')

        self.assertGreater(gatilhos, 20)
        self.assertLess(
            len(capturadas),
            gatilhos,
            "a ficha faz mais consultas que exercícios: cheiro de N+1",
        )


class OVolumeContinuaIntocadoTests(TestCase):
    """A fase B é puramente visual. Se ela mexer no volume, a tela de treino
    passa a mostrar outro número sem ninguém ter decidido isso."""

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_workouts", verbosity=0)

    def test_o_volume_continua_somando_so_pelo_principal(self):
        from workouts import views
        from workouts.models import WorkoutTemplate

        modelo = WorkoutTemplate.objects.filter(is_active=True).first()
        itens = list(modelo.items.select_related("exercise").all())

        class SessaoFalsa:
            def __init__(self, itens):
                self._itens = itens

            @property
            def exercises(self):
                sessao = self

                class Gerente:
                    def all(self_):
                        return sessao._itens

                return Gerente()

        linhas = views.muscle_volume([SessaoFalsa(itens)])
        por_grupo = {linha["slug"]: linha["sets"] for linha in linhas}

        esperado = {}
        for item in itens:
            grupo = item.exercise.muscle_group
            esperado[grupo] = esperado.get(grupo, 0) + item.sets

        self.assertEqual(por_grupo, esperado)
