"""A linguagem de movimento do NutriPlan (15/09/2026).

Uma auditoria real encontrou cartões de refeição saltando de 44 para 422 px
sem quadro intermediário, sanfonas instantâneas, toque sem retorno e troca de
tela seca. A resposta é UMA linguagem: tokens `--mov-*` no `:root`, animador
de `<details>` em `pwa.js`, indicador da aba que morfa por view transition,
eco do toque na água, números que contam, listas que entram escalonadas — e
tudo com saída em `prefers-reduced-motion`.

O que estes testes guardam é o CONTRATO, não o gosto: os tokens existem e
são a única fonte de duração; o animador intercepta e respeita movimento
reduzido; o botão tocado mostra processamento e não aceita o segundo toque;
o nome de view transition é único por documento (duplicado, o navegador
descarta a transição inteira, em silêncio); e o vídeo continua sendo um
player só.
"""
import re
from datetime import datetime, time
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TrainingDay, User
from push.test_cache_privado import sem_comentarios

RAIZ = Path(__file__).resolve().parent.parent
CSS = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
JS = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
CSS_LIMPO = sem_comentarios(CSS)
JS_LIMPO = sem_comentarios(JS)

TOKENS = (
    "--mov-toque", "--mov-estado", "--mov-expansao", "--mov-tela",
    "--mov-modal", "--mov-sucesso", "--mov-passo", "--mov-passo-longo",
    "--mov-degrau", "--ease", "--ease-sai",
)

#: Durações escritas à mão em `transition`/`animation`. Catraca: só desce.
#: O `.01ms` da saída de movimento reduzido é a única exceção, nomeada.
TETO_DURACAO_CRUA = 0


def raiz_css():
    return re.search(r":root\s*\{(.*?)\n\}", CSS_LIMPO, flags=re.S).group(1)


def duracoes_cruas(css):
    """Cada `transition`/`animation` (e `-duration`/`-delay`) com um número
    seguido de `s`/`ms` escrito na declaração, fora dos tokens."""
    achados = []
    for decl in re.findall(r"(?:transition|animation)(?:-duration|-delay)?\s*:\s*([^;{}]+)[;}]", css):
        if ".01ms" in decl:
            continue
        for valor in re.findall(r"(?<![\w-])(\d*\.?\d+)m?s(?![\w-])", decl):
            if float(valor):  # `0s` não é duração: é o desligamento do atraso
                achados.append((decl.strip(), valor))
    return achados


#: Catraca dos keyframes sem consumidor. Só desce.
KEYFRAMES_ORFAOS_TETO = 0

#: O que o shorthand `animation` escreve e que NÃO é nome de keyframe.
PALAVRAS_DO_SHORTHAND = frozenset(
    "none infinite both forwards backwards normal reverse alternate alternate-reverse "
    "running paused ease ease-in ease-out ease-in-out linear step-start step-end steps "
    "cubic-bezier var calc s ms".split()
)


def keyframes_orfaos(css):
    """Cada `@keyframes X` que nenhuma `animation`/`animation-name` dispara.

    Lê o CSS SEM comentários — este arquivo cita keyframe em frase de
    explicação, e `serie-ok` mencionado num comentário não é consumidor."""
    declarados = set(re.findall(r"@keyframes\s+([\w-]+)", css))
    usados = set()
    # `[;}]` fecha a declaração: a última de um bloco pode vir sem `;`, e
    # `[^;]+` engoliria a regra seguinte — o mesmo cuidado de `duracoes_cruas`.
    for corpo in re.findall(r"animation(?:-name)?\s*:\s*([^;{}]+)[;}]", css):
        usados.update(re.findall(r"[a-zA-Z_][\w-]*", corpo))
    # Palavra do shorthand não é nome de keyframe: `@keyframes both` existiria
    # órfão e passaria escondido atrás do `both` de qualquer `animation`.
    return sorted(declarados - (usados - PALAVRAS_DO_SHORTHAND))


def _partes_reduzidas(css):
    for m in re.finditer(r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{", css):
        i, nivel = m.end(), 1
        while nivel and i < len(css):
            nivel += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        yield css[m.end():i - 1]


def bloco_reduzido(css):
    """Todo o CSS dentro de `@media (prefers-reduced-motion: reduce)`."""
    return "\n".join(_partes_reduzidas(css))


def sem_reduzido(css):
    """O CSS sem os blocos de movimento reduzido."""
    for parte in _partes_reduzidas(css):
        css = css.replace(parte, "")
    return css


def bloco_movimento(js):
    """O IIFE de movimento é o último do arquivo; começa em `reduzido()`."""
    return js[js.index("function reduzido()"):]


class TokensDeMovimentoTests(SimpleTestCase):
    def test_os_tokens_existem_no_root(self):
        raiz = raiz_css()
        for token in TOKENS:
            with self.subTest(token=token):
                self.assertRegex(raiz, r"\n\s*" + re.escape(token) + r"\s*:")

    def test_toque_estado_expansao_tela_modal_sucesso_estao_nas_faixas(self):
        """As faixas do brief: toque 90–120, estado 160–220, expansão 220–280,
        tela 180–240, modal 240–320, sucesso 400–700 ms; passos de 4 a 12 px."""
        raiz = raiz_css()
        faixas = {
            "--mov-toque": (90, 120), "--mov-estado": (160, 220),
            "--mov-expansao": (220, 280), "--mov-tela": (180, 240),
            "--mov-modal": (240, 320), "--mov-sucesso": (400, 700),
        }
        for token, (piso, teto) in faixas.items():
            valor = re.search(re.escape(token) + r"\s*:\s*([\d.]+)(m?s)", raiz)
            ms = float(valor.group(1)) * (1 if valor.group(2) == "ms" else 1000)
            with self.subTest(token=token, ms=ms):
                self.assertTrue(piso <= ms <= teto)
        for token, (piso, teto) in {"--mov-passo": (4, 12), "--mov-passo-longo": (4, 12)}.items():
            px = float(re.search(re.escape(token) + r"\s*:\s*([\d.]+)px", raiz).group(1))
            with self.subTest(token=token, px=px):
                self.assertTrue(piso <= px <= teto)

    def test_nenhuma_duracao_escrita_a_mao(self):
        """Tudo que anima lê um token. Valor solto é o começo de uma segunda
        linguagem de movimento — foi assim que o app chegou a `.12s`, `.15s`,
        `.16s`, `.22s`, `.32s` e `.7s` espalhados."""
        cruas = duracoes_cruas(CSS_LIMPO)
        self.assertLessEqual(
            len(cruas), TETO_DURACAO_CRUA,
            f"{len(cruas)} duração(ões) escrita(s) à mão: {cruas[:5]}",
        )

    def test_o_dur_antigo_e_apelido_do_estado(self):
        self.assertRegex(raiz_css(), r"--dur\s*:\s*var\(--mov-estado\)")


class KeyframeSemConsumidorTests(SimpleTestCase):
    """Keyframe que ninguém anima é linguagem morta: `serie-ok`, `serie-anel`,
    `esqueleto` e `descanso-acabando` foram escritos para a execução do treino
    e nunca ganharam a classe que os dispara (ela depende de `workouts/views.py`,
    fora desta onda). Saem agora; se a onda 6 os quiser, nascem com o
    consumidor no mesmo commit. `varrer` sai porque o anel nascia varrendo a
    cada abertura — movimento que não confirma ação nenhuma."""

    TETO = KEYFRAMES_ORFAOS_TETO

    def test_o_leitor_enxerga_um_orfao(self):
        """Controle positivo do leitor: sem isto, um CSS que declarasse os
        keyframes de um jeito que a regex não lê deixaria a catraca verde por
        não achar nada."""
        self.assertEqual(keyframes_orfaos("@keyframes x { } .a { animation: y 1s; }"), ["x"])
        self.assertEqual(keyframes_orfaos("@keyframes x { } .a { animation: x 1s; }"), [])
        # `animation-name` também conta como consumidor.
        self.assertEqual(keyframes_orfaos("@keyframes x { } .a { animation-name: x; }"), [])
        # Duas animações na mesma declaração; a última do bloco sem `;`.
        self.assertEqual(keyframes_orfaos("@keyframes x { } @keyframes y { } .a { animation: x 1s, y 2s }"), [])
        self.assertEqual(keyframes_orfaos("@keyframes x { } .a { animation: y 1s } .x { color: red; }"), ["x"])
        # Palavra do shorthand não esconde um keyframe com o mesmo nome.
        self.assertEqual(keyframes_orfaos("@keyframes both { } .a { animation: y 1s both; }"), ["both"])
        # O leitor recebe CSS SEM comentários; com comentário, a menção contaria.
        self.assertEqual(keyframes_orfaos(sem_comentarios("@keyframes x { } /* animation: x; */")), ["x"])

    def test_todo_keyframe_tem_quem_o_anime(self):
        # Piso: um regex que não casasse `@keyframes` daria zero órfãos por
        # não achar nada. Hoje são 18 declarados.
        self.assertGreaterEqual(len(re.findall(r"@keyframes\s+[\w-]+", CSS_LIMPO)), 10)
        orfaos = keyframes_orfaos(CSS_LIMPO)
        self.assertLessEqual(len(orfaos), self.TETO, f"keyframes sem consumidor: {orfaos}")

    def test_o_anel_nao_varre_ao_abrir(self):
        self.assertNotIn("@keyframes varrer", CSS_LIMPO)
        self.assertNotRegex(CSS_LIMPO, r"animation:[^;]*\bvarrer\b")

    def test_os_anchors_de_movimento_continuam(self):
        """`encher` ao abrir FICA (é a única recompensa da tela de progresso, e
        `config/tests.py` diz por quê); `pulso` é o esqueleto, onde há mesmo
        algo acontecendo. Este teste é o que impede a catraca de "limpar"
        demais."""
        self.assertIn("@keyframes encher", CSS_LIMPO)
        self.assertIn("animation: encher", CSS_LIMPO)
        self.assertIn("animation: pulso", CSS_LIMPO)


class MovimentoReduzidoTests(SimpleTestCase):
    def test_o_css_zera_duracoes_e_atrasos_para_quem_pediu_menos_movimento(self):
        reduzido = bloco_reduzido(CSS_LIMPO)
        self.assertIn("animation-duration: .01ms !important", reduzido)
        self.assertIn("transition-duration: .01ms !important", reduzido)
        # `animation-delay` não é duração: um cartão com `both` ficaria
        # invisível durante o atraso. O bloco zera os atrasos das listas.
        self.assertRegex(reduzido, r"\[data-escalonado\]\s*>\s*\*[^{]*\{[^}]*animation-delay:\s*0s")
        # E nenhum nome de view transition sobrevive: sem nome, sem morfar.
        for seletor in (".tabbar__item.is-active", ".wizard__avanco", ".today-hero__facts"):
            with self.subTest(seletor=seletor):
                self.assertRegex(reduzido, re.escape(seletor) + r"[^{]*\{[^}]*view-transition-name:\s*none")
        self.assertIn("navigation: none", reduzido)

    def test_o_javascript_consulta_a_preferencia_antes_de_animar(self):
        movimento = bloco_movimento(JS_LIMPO)
        self.assertIn("prefers-reduced-motion: reduce", movimento)
        # A sanfona, o eco e a contagem — os três caminhos que animam por JS.
        self.assertRegex(movimento, r"if \(!details\.animate \|\| reduzido\(\)\) return;")
        self.assertRegex(movimento, r"if \(!botao \|\| reduzido\(\)\) return;")
        self.assertRegex(movimento, r"if \(reduzido\(\) \|\| !window\.requestAnimationFrame")


class SanfonaAnimadaTests(SimpleTestCase):
    """`<details>` abre e fecha com a altura acompanhando, nos dois sentidos."""

    def test_o_animador_intercepta_o_toque_e_mede_as_duas_alturas(self):
        movimento = bloco_movimento(JS_LIMPO)
        self.assertIn("evento.preventDefault();", movimento)
        self.assertIn("function abrirSanfona(details, summary)", movimento)
        self.assertIn("function fecharSanfona(details, summary)", movimento)
        # Abre: mede fechado, abre, mede aberto, anima entre os dois.
        self.assertRegex(movimento, r"var de = details\.offsetHeight;\s*details\.dataset\.animando = \"1\";\s*details\.style\.overflow = \"clip\";\s*details\.open = true;\s*var ate = details\.offsetHeight;")
        # Fecha: só troca `open` DEPOIS de animar.
        self.assertRegex(movimento, r"anim\.onfinish = anim\.oncancel = function \(\) \{\s*details\.open = false;")
        # Os estilos em linha saem ao terminar — o elemento volta a ser um `<details>` comum.
        self.assertRegex(movimento, r"details\.style\.height = \"\";\s*details\.style\.overflow = \"\";")

    def test_a_duracao_vem_do_token_de_expansao(self):
        self.assertIn('tempo("--mov-expansao", 250)', bloco_movimento(JS_LIMPO))

    def test_o_mapa_de_areas_e_quem_pedir_ficam_de_fora(self):
        movimento = bloco_movimento(JS_LIMPO)
        self.assertIn('details.hasAttribute("data-sem-animacao")', movimento)
        # Um link ou botão dentro do `summary` segue o caminho dele.
        self.assertIn('evento.target.closest("a, button, input, select, textarea, label")', movimento)

    def test_a_grade_da_refeicao_fora_do_plano_nao_transita_mais(self):
        """`grid-template-rows` transitava na abertura; com o animador medindo
        a altura, a transição da grade daria a medida errada."""
        regra = re.search(r"\.fora__corpo\s*\{([^}]*)\}", CSS_LIMPO).group(1)
        self.assertNotIn("transition", regra)

    def test_a_seta_da_refeicao_gira_em_vez_de_trocar_de_glifo(self):
        self.assertRegex(CSS_LIMPO, r"\.meal__futuro\[open\] > \.meal__abrir::after\s*\{[^}]*rotate\(180deg\)")
        self.assertNotRegex(CSS_LIMPO, r"\.meal__futuro\[open\] > \.meal__abrir::after\s*\{[^}]*content:")


class ToqueEProcessamentoTests(SimpleTestCase):
    def test_o_botao_tocado_e_desligado_e_marcado_como_ocupado(self):
        """Proteção contra o segundo toque: o botão do envio é desligado no
        mesmo instante (depois de o valor dele entrar no formulário)."""
        # A guarda GERAL (todo formulário), e não a de `[data-envia]` do login,
        # que tem o texto de espera na linha seguinte.
        self.assertRegex(JS_LIMPO, r"botao\.disabled = true;\s*botao\.setAttribute\(\"aria-busy\", \"true\"\);\s*\}, 0\);")

    def test_o_botao_volta_quando_a_pagina_volta_ou_o_envio_fica_na_fila(self):
        self.assertRegex(JS_LIMPO, r'addEventListener\("pageshow", function \(\) \{\s*document\.querySelectorAll\("\[type=submit\]\[aria-busy\]"\)[\s\S]*?b\.disabled = false;')
        self.assertRegex(JS_LIMPO, r'addEventListener\("nutriplan:enfileirado"[\s\S]*?b\.disabled = false;')

    def test_o_estado_de_processamento_tem_anel_visivel(self):
        self.assertRegex(CSS_LIMPO, r'\.btn\[aria-busy="true"\]::after,\s*\.agua__botao\[aria-busy="true"\]::after\s*\{[^}]*animation:\s*montagem-gira')

    def test_o_toque_afunda_com_o_tempo_de_toque(self):
        # O cartão de sessão entrou na lista ÚNICA de toque (uma escala, .96).
        self.assertRegex(CSS_LIMPO, r"\.sessao-cartao:active,\s*\.tabbar__item:active\s*\{\s*transform: scale\(\.96\);")
        # A transição do afundamento lê o token, e não `.12s`.
        self.assertNotIn("transform .12s", CSS_LIMPO)
        self.assertIn("transform var(--mov-toque) var(--ease)", CSS_LIMPO)

    def test_o_anel_de_processamento_fica_fora_do_fluxo_e_nao_gira_sem_movimento(self):
        # `.agua__botao` é grid: um `::after` no fluxo virava terceira linha.
        self.assertRegex(CSS_LIMPO, r'\.agua__botao\[aria-busy="true"\]::after\s*\{[^}]*position: absolute')
        self.assertRegex(bloco_reduzido(CSS_LIMPO), r'\.agua__botao\[aria-busy="true"\]::after\s*\{\s*animation: none')


class UmPlayerSoTests(SimpleTestCase):
    def test_o_player_nasce_no_toque_e_recusa_o_segundo(self):
        js = sem_comentarios((RAIZ / "templates" / "workouts" / "_demonstracao_js.html").read_text(encoding="utf-8"))
        self.assertIn('if (demo.querySelector("iframe, video")) return;', js)
        self.assertNotIn("<iframe", (RAIZ / "templates" / "workouts" / "_demonstracao.html").read_text(encoding="utf-8"))

    def test_o_video_abre_e_o_poster_volta_em_fade(self):
        self.assertRegex(CSS_LIMPO, r"\.demo--aberta > iframe,\s*\.demo--aberta > video,\s*\.demo--aberta > img,\s*\.demo__abrir\s*\{\s*animation: entra-suave var\(--mov-expansao\)")


class GanchosNosTemplatesTests(SimpleTestCase):
    def ler(self, caminho):
        return (RAIZ / "templates" / caminho).read_text(encoding="utf-8")

    def test_as_tres_formas_de_marcar_a_refeicao_celebram_o_cartao(self):
        hoje = self.ler("plans/today.html")
        self.assertEqual(hoje.count('data-celebra="slot-{{ slot.pk }}"'), 3)
        self.assertIn('id="slot-{{ slot.pk }}"', hoje)

    def test_a_agua_tem_total_barra_e_eco_por_botao(self):
        agua = self.ler("plans/_agua.html")
        self.assertIn("<b data-agua-total>", agua)
        self.assertIn("data-agua-barra", agua)
        for eco in ("+250 ml", "+500 ml", "+750 ml"):
            with self.subTest(eco=eco):
                self.assertIn(f'data-agua-eco="{eco}"', agua)
        # A tela do pilar Hidratação tem os mesmos botões: mesma ação, mesmo eco.
        hidratacao = self.ler("plans/hydration.html")
        self.assertIn('data-agua-eco="+{{ passo }} ml"', hidratacao)
        self.assertIn('class="ring__value num" data-agua-total', hidratacao)

    def test_as_listas_que_entram_escalonadas(self):
        for caminho, trecho in (
            ("workouts/routine.html", '<ul class="programa__sessoes" data-escalonado>'),
            ("workouts/ficha.html", '<ol class="ficha-lista" data-escalonado>'),
            ("workouts/ficha.html", '<ol class="ficha-lista" data-escalonado start='),
            ("accounts/areas.html", '<nav class="modulos" data-escalonado'),
            ("plans/history.html", '<div class="history-rows" data-escalonado>'),
            ("plans/_progresso_agua.html", '<ul class="semanas" data-escalonado'),
            ("plans/_progresso_treino.html", '<ul class="semanas" data-escalonado'),
        ):
            with self.subTest(caminho=caminho):
                self.assertIn(trecho, self.ler(caminho))

    def test_os_numeros_do_progresso_contam(self):
        self.assertEqual(self.ler("plans/history.html").count('class="tile__value" data-conta>'), 3)

    def test_o_onboarding_grava_e_le_a_direcao(self):
        etapa = self.ler("accounts/onboarding/step.html")
        self.assertIn('<form method="post" novalidate data-direcao="avanca" data-rascunho>', etapa)
        self.assertIn('href="{{ previous_url }}" data-direcao="volta"', etapa)
        # Na edição, "Voltar" sai do cadastro: não é uma direção dentro dele.
        self.assertIn('href="{{ voltar_para }}">Voltar</a>', etapa)
        self.assertIn('sessionStorage.getItem("nutriplan:direcao")', etapa)
        self.assertIn('setAttribute("data-transicao", d)', etapa)
        self.assertRegex(CSS_LIMPO, r':root\[data-transicao="volta"\]::view-transition-new\(root\)')


def classes_de_cada_tag(html):
    """Os conjuntos de classes de cada tag com `class=`."""
    return [set(c.split()) for c in re.findall(r'<\w+[^>]*\bclass="([^"]*)"', html)]


#: Os nomes de view transition que o CSS declara, LIDOS do CSS: cada um vira
#: o conjunto de classes do primeiro composto do seletor (`.series__titulo >
#: b.num` conta o `.series__titulo`). Dois elementos com o mesmo nome fazem
#: o navegador PULAR a transição inteira, sem erro — e ler do CSS é o que faz
#: uma regra nova (`.meal { view-transition-name: ... }`) cair aqui sozinha.
def nomes_declarados():
    css = sem_reduzido(CSS_LIMPO)
    nomes = {}
    for seletor, nome in re.findall(r"([^{}]+)\{[^}]*view-transition-name:\s*([\w-]+);", css):
        composto = seletor.strip().split(">")[0].strip().split()[0]
        classes = set(re.findall(r"\.([\w-]+)", composto))
        nomes.setdefault(nome, []).append(classes)
    return nomes


ESPERADOS = {
    "barra-topo", "barra-abas", "aba-ativa", "trilha-do-cadastro",
    "fatos-do-dia", "numero-da-serie", "nome-do-exercicio",
}


class NomeDeViewTransitionUnicoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        from plans.tests import create_complete_user
        self.user = create_complete_user(email="movimento@exemplo.com")
        TrainingDay.objects.update_or_create(
            user=self.user, weekday=timezone.localdate().weekday(), defaults={"duration_min": 45}
        )
        from workouts.services import acertar_rotina, registrar_escolha
        plano, _ = acertar_rotina(self.user)
        # Desde 15/09/2026 a letra pode ter duas opções e a execução pede a
        # escolha na ficha; o teste escolhe a 1 para abrir a execução direto.
        sessao = plano.sessions.get(weekday=timezone.localdate().weekday())
        registrar_escolha(self.user, sessao, 1)
        self.client.force_login(self.user)

    def test_o_css_declara_cada_nome_uma_vez(self):
        nomes = nomes_declarados()
        self.assertEqual(set(nomes), ESPERADOS)
        for nome, seletores in nomes.items():
            with self.subTest(nome=nome):
                self.assertEqual(len(seletores), 1, seletores)

    def test_nenhuma_pagina_repete_um_nome(self):
        rotas = [
            reverse("plans:today"), reverse("workouts:routine"), reverse("plans:history"),
            reverse("areas"), reverse("workouts:now"), reverse("accounts:profile"),
        ] + [reverse("accounts:onboarding_step", kwargs={"step": n}) for n in (1, 2, 3)]
        for rota in rotas:
            html = self.client.get(rota, follow=True).content.decode()
            tags = classes_de_cada_tag(html)
            for nome, seletores in nomes_declarados().items():
                quantos = sum(1 for classes in seletores for t in tags if classes and classes <= t)
                with self.subTest(rota=rota, nome=nome):
                    self.assertLessEqual(quantos, 1)
            # Controle positivo: as barras existem e a aba ativa é UMA.
            if "onboarding" not in rota:
                with self.subTest(rota=rota, controle="barras"):
                    self.assertEqual(sum(1 for t in tags if {"app-bar"} <= t), 1)
                    self.assertEqual(sum(1 for t in tags if {"tabbar__item", "is-active"} <= t), 1)

    def test_a_execucao_serve_o_numero_da_serie_uma_vez_e_zero_iframe(self):
        html = self.client.get(reverse("workouts:now")).content.decode()
        self.assertEqual(html.count('class="series__titulo"'), 1)
        titulo = re.search(r'<p class="series__titulo">(.*?)</p>', html, flags=re.S).group(1)
        self.assertEqual(titulo.count('<b class="num">'), 1)
        self.assertEqual(html.count("<iframe"), 0)
        # O número precisa de CAIXA para o navegador capturá-lo.
        self.assertRegex(CSS_LIMPO, r"\.series__titulo > b\.num \{ display: inline-block; view-transition-name")


class SemJavaScriptTests(TestCase):
    """O que o JavaScript anima já funcionava sem ele, e continua."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def test_a_refeicao_e_um_details_nativo_e_a_agua_um_formulario_comum(self):
        from plans.tests import create_complete_user
        self.client.force_login(create_complete_user(email="semjs@exemplo.com"))
        # Sete da manhã, sempre: a sanfona "Ver opções" só existe em refeição
        # FUTURA, e o `pre-push` de 15/09/2026 às 21h30 não tinha nenhuma.
        manha = timezone.make_aware(datetime.combine(timezone.localdate(), time(7, 0)))
        with mock.patch("plans.views.relogio", return_value=manha):
            html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn('<details class="meal__futuro">', html)
        self.assertIn('<summary class="meal__abrir">Ver opções</summary>', html)
        # O eco e a contagem são atributos de dados: sem script, o botão é
        # um `<button type="submit">` e o total é o número servido.
        self.assertRegex(html, r'<button type="submit" class="agua__botao" data-agua-eco="\+250 ml">')
        self.assertRegex(html, r"<b data-agua-total>\d+</b>")
