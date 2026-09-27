# -*- coding: utf-8 -*-
"""Na execução, nada preso cobre o que a pessoa precisa ver (24/09/2026).

MEDIDO no Chromium antes desta missão, conta de QA, dia com treino:

| vista | faixa livre | o que ficava coberto |
|---|---:|---|
| 390×844 | 355 px | o vídeo aberto (391 px de altura) e "Série N de M" |
| 375×667 | 178 px | músculos, **"ver vídeo"**, a dica e "Série N de M" |
| 375×667 + descanso | 25 px | tudo acima do bloco |

A causa é somada de três partes, e esta suíte prende as três:

1. **o bloco reservava 94 px para uma barra de abas que esta tela não tem.**
   `ModoTreinoView` põe `sem_tabbar = True` desde 20/09/2026, e o `bottom`
   continuava em `calc(var(--tabbar-h) + …)`, corrigido só por uma media
   query de 60rem — ou seja, no celular nunca;
2. **o bloco carregava o que não se toca entre uma série e outra**: as
   pastilhas "1 2 3 4" (histórico) e "Anotar algo desta série" (opcional e
   recolhido) faziam dele 335 px;
3. **o vídeo vertical era 60vh**, sem relação com a faixa que sobra.

A régua GEOMÉTRICA — `elementFromPoint` no centro de cada elemento — mora em
`scratchpad/medir_execucao.py` e no E2E noturno; aqui ficam o contrato de
CSS e o de markup, que é o que um teste de suíte consegue provar sem
navegador.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
AGORA = Path(settings.BASE_DIR) / "templates" / "workouts" / "agora.html"


def sem_comentarios(texto):
    """Este repositório comenta muito, e o comentário cita o nome da coisa que
    a asserção procura — ler o arquivo cru faria toda regra "existir"."""
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def regras(css, seletor):
    """Todo bloco cujo seletor contém `seletor`, sem comentário."""
    limpo = sem_comentarios(css)
    achadas = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", limpo):
        if seletor in m.group(1):
            achadas.append((m.group(1).strip(), m.group(2)))
    return achadas


class OBlocoNaoReservaUmaBarraQueNaoExisteTests(SimpleTestCase):
    """Decisão do dono (24/09/2026): sem barra de abas, o bloco cola no
    rodapé — e quem decide é a CLASSE DO SERVIDOR, não a largura."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS.read_text(encoding="utf-8")

    def test_o_bloco_cola_no_rodape_quando_o_body_nao_tem_tabbar(self):
        alvo = [
            corpo for sel, corpo in regras(self.css, ".agora__registro")
            if "body:not(.tem-tabbar)" in sel
        ]
        self.assertTrue(
            alvo,
            "falta a regra `body:not(.tem-tabbar) .agora__registro` — sem ela a "
            "execução reserva 94px para uma barra que ela não desenha",
        )
        self.assertNotIn("--tabbar-h", alvo[0])

    def test_a_correcao_nao_depende_de_media_query(self):
        """A de 60rem consertava só o desktop; o bug é do celular.

        Ancorado no fato de a regra da CLASSE existir e vir depois — uma media
        query a mais não quebra nada, mas ela não pode ser a ÚNICA saída.
        """
        limpo = sem_comentarios(self.css)
        geral = limpo.index(".agora__registro {")
        porClasse = limpo.find("body:not(.tem-tabbar) .agora__registro")
        self.assertGreater(
            porClasse, geral,
            "a regra da classe tem de vir DEPOIS da geral, senão o bottom dela perde",
        )

    def test_o_aviso_de_conquista_tambem_nao_reserva_a_barra_ausente(self):
        """Ele é `fixed` e aparece em toda tela, inclusive nesta."""
        alvo = [
            corpo for sel, corpo in regras(self.css, ".conquista")
            if "body:not(.tem-tabbar)" in sel
        ]
        self.assertTrue(alvo, "o aviso de conquista reserva a tabbar em tela sem tabbar")
        self.assertNotIn("--tabbar-h", alvo[0])


class OBlocoPresoSoTemOQueSeTocaEntreSeriesTests(SimpleTestCase):
    """Decisão do dono: no máximo ~140px — carga (com reps na mesma linha) e
    "Concluir série". Pastilhas e "Anotar algo" voltam para o fluxo, ACIMA.

    Isto NÃO desfaz a B32 de 16/09: lá o formulário `sticky` cobria as
    pastilhas porque elas ficavam no fluxo e ele passava por cima. A resposta
    de hoje é a outra — as pastilhas continuam no fluxo e o bloco encolhe e
    reserva o próprio espaço (`scroll-margin-bottom`), em vez de engolir a
    fileira.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.html = AGORA.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")

    def _bloco_do_template(self):
        limpo = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", self.html, flags=re.S)
        i = limpo.index('<div class="agora__registro"')
        return limpo[i:limpo.index("data-conquista-alvo", i)]

    def test_as_pastilhas_ficam_fora_do_bloco_preso(self):
        self.assertNotIn('<ol class="series__lista">', self._bloco_do_template())

    def test_anotar_algo_fica_fora_do_bloco_preso(self):
        self.assertNotIn('class="registro__nota"', self._bloco_do_template())

    def test_as_pastilhas_vem_antes_do_bloco_no_documento(self):
        """Fora do bloco E acima dele: embaixo, ficariam atrás do sticky."""
        limpo = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", self.html, flags=re.S)
        self.assertLess(
            limpo.index('<ol class="series__lista">'),
            limpo.index('<div class="agora__registro"'),
        )

    def test_carga_e_reps_dividem_a_mesma_linha(self):
        """Duas linhas de campo são ~70px que a faixa livre não tem."""
        grade = [corpo for sel, corpo in regras(self.css, ".registro--agora") if "grid-template-areas" in corpo]
        self.assertTrue(grade, "a grade do registro sumiu")
        areas = re.search(r"grid-template-areas:([^;]+);", grade[0]).group(1)
        linhas = re.findall(r'"([^"]+)"', areas)
        self.assertTrue(linhas, "sem linhas na grade")
        for linha in linhas:
            nomes = set(linha.split())
            if "reps" in nomes:
                self.assertIn(
                    "carga", nomes,
                    "reps tem de dividir a linha com a carga: %r" % linha,
                )

    def test_o_bloco_declara_um_teto_de_altura(self):
        """O teto é o que impede a próxima linha de conteúdo de devolver o
        bloco aos 335px sem ninguém perceber."""
        preso = [corpo for sel, corpo in regras(self.css, ".agora__registro")
                 if "position: sticky" in corpo]
        self.assertTrue(preso)
        self.assertIn("--exec-bloco", preso[0])


class OVideoCabeNaFaixaLivreTests(SimpleTestCase):
    """Decisão do dono: o vídeo vertical tem `max-height` igual à faixa livre
    (`100dvh` − cabeçalho − descanso − bloco), nunca 60vh solto."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS.read_text(encoding="utf-8")

    def test_a_demonstracao_aberta_mede_a_faixa_livre_e_nao_o_viewport(self):
        aberta = [corpo for sel, corpo in regras(self.css, ".demo--aberta")
                  if "max-height" in corpo]
        self.assertTrue(aberta, "a demonstração aberta perdeu o teto de altura")
        teto = re.search(r"max-height:([^;]+);", aberta[0]).group(1)
        self.assertIn("100dvh", teto, "o teto tem de sair da altura VISÍVEL da janela")
        self.assertIn("--exec-bloco", teto, "o teto tem de descontar o bloco preso")

    def test_o_teto_desconta_a_cabeca_do_exercicio(self):
        """MEDIDO em 24/09/2026, depois da primeira correção: com o vídeo
        aberto, `.agora__nome` ia para -9px e `.agora__meta` para 42 — os dois
        `coberto por app-bar`. A causa era a rolagem levar a DEMONSTRAÇÃO para
        o topo da faixa, deixando o nome acima dela.

        A resposta tem duas metades, e esta é a do CSS: o teto do vídeo
        desconta a cabeça do exercício, para nome e músculos caberem na faixa
        JUNTO com o vídeo. A outra metade — rolar a cabeça, e não a
        demonstração — está em `OVideoSobeComONomeDoExercicioTests`.
        """
        aberta = [corpo for sel, corpo in regras(self.css, ".demo--aberta")
                  if "max-height" in corpo]
        self.assertTrue(aberta)
        teto = re.search(r"max-height:([^;]+);", aberta[0]).group(1)
        self.assertIn(
            "--exec-cabeca", teto,
            "sem descontar a cabeça, o vídeo ocupa a faixa toda e empurra o "
            "nome do exercício para trás do cabeçalho",
        )

    def test_a_faixa_desconta_o_descanso_quando_ele_existe(self):
        """O descanso é `sticky` no topo e come 64px — e quando ele está
        rodando é exatamente quando a pessoa olha o vídeo."""
        comDescanso = [corpo for sel, corpo in regras(self.css, ".agora--com-descanso")
                       if "--exec-descanso" in corpo]
        self.assertTrue(
            comDescanso,
            "falta o desconto do descanso: a classe vem do servidor "
            "(`agora--com-descanso`), nunca de `:has()`",
        )


class OVideoSobeComONomeDoExercicioTests(SimpleTestCase):
    """Decisão do dono (guarda 4): com o vídeo aberto, o NOME do exercício
    continua na faixa livre. Um vídeo sem o nome por cima não diz de que
    exercício é.

    O script da demonstração é partilhado com a rota de leitura do exercício,
    que não tem `.agora__topo` — por isso o alvo é `|| demo`, e não um
    `querySelector` que devolveria `null` e derrubaria o `scrollIntoView`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = (Path(settings.BASE_DIR) / "templates" / "workouts"
                  / "_demonstracao_js.html").read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")

    def _codigo(self):
        return re.sub(r"/\*.*?\*/", "", self.js, flags=re.S)

    def test_quem_sobe_e_a_cabeca_do_exercicio_com_reserva_para_a_demo(self):
        codigo = self._codigo()
        self.assertRegex(
            codigo,
            r'querySelector\("\.agora__topo"\)\s*\|\|\s*demo',
            "o alvo da rolagem é a cabeça, com a demonstração como reserva",
        )
        self.assertIn("alvo.scrollIntoView(", codigo)
        self.assertNotIn(
            "demo.scrollIntoView(", codigo,
            "rolar a demonstração direto é o que punha o nome atrás da barra",
        )

    def test_a_cabeca_tem_a_margem_de_rolagem_do_cabecalho_e_do_descanso(self):
        alvo = [corpo for sel, corpo in regras(self.css, ".agora__topo")
                if "scroll-margin-top" in corpo]
        self.assertTrue(alvo, "sem margem, a cabeça sobe para trás da barra")
        margem = re.search(r"scroll-margin-top:([^;]+);", alvo[0]).group(1)
        self.assertIn("--appbar-h", margem)
        self.assertIn("--exec-descanso", margem)

    def test_a_rolagem_respeita_quem_pediu_menos_movimento(self):
        codigo = self._codigo()
        self.assertIn("prefers-reduced-motion", codigo)
