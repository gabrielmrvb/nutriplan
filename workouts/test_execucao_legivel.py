# -*- coding: utf-8 -*-
"""A execução na primeira abertura do dia: cabeçalho legível, pastilhas à vista.

Avaliação de 16/09/2026 (B28 e B32), a 390 px, antes de escolher a opção:

- o sobretítulo "TREINO C · PERNAS E OMBROS · OPÇÃO 1" saía em QUATRO linhas
  em caixa alta, porque dividia a linha do topo com a frase "Opção 1, a
  recomendada de hoje — trocar de opção na ficha." (`.agora__opcao-aviso`,
  sem regra própria, virava um terceiro item do flex);
- com o cabeçalho mais alto, o bloco preso ao rodapé (Carga · Reps ·
  Concluir) cobria a METADE DE BAIXO das pastilhas "1 2 3 4" — a fileira
  que é o histórico da sessão e o único retorno visual do toque. Depois da
  primeira série, com o cabeçalho mais baixo, sobravam 9–10 px. E no
  desktop, onde a barra de abas é `display: none`, o `bottom` continuava
  reservando 94 px para ela.

Correções, guardadas aqui pela DECLARAÇÃO (o sintoma não rola a tela; a
medida visual fica com o QA de navegador, que refez as capturas):

1. a frase da opção sai da linha do topo e ganha linha própria, depois dela
   — no DOM, e não por `order`, para a ordem de foco (frase → "← Ficha")
   continuar a ordem visual;
2. as pastilhas entram no bloco preso: `.agora__registro` envolve a fileira,
   a nota de "aguardando rede" e o formulário, e é ELE que é `sticky`. O que
   a pessoa toca e o que muda com o toque ficam na mesma caixa, e nada da
   caixa cobre a fileira;
3. a partir de 60rem, sem barra de abas, o bloco cola em `bottom: 0`.
"""
import re

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from config.test_design_system import CSS, sem_comentarios
from workouts import services
from workouts.models import Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts


def _regras(css, seletor):
    """Todos os corpos do seletor — ele pode aparecer fora e dentro de uma
    media query, e a ordem no arquivo não é a ordem de leitura."""
    return re.findall(r"(?:^|\})\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", css)


def _regra(css, seletor):
    corpos = _regras(css, seletor)
    return corpos[0] if corpos else None


def _bloco(html, marcador, fim):
    inicio = html.index(marcador)
    return html[inicio:html.index(fim, inicio)]


class OCabecalhoDaExecucaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="cabecalho@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def _html(self):
        return sem_scripts(self.client.get(reverse("workouts:now")).content.decode())

    def test_o_cabecalho_nao_fala_de_opcao(self):
        """Ficha única (17/09/2026): o sobretítulo é "Treino C · Pernas e
        ombros", sem "· Opção N", e não há aviso de opção recomendada."""
        html = self._html()
        self.assertNotIn("Opção", html.split("agora__sessao-rotulo", 1)[1].split("</p>", 1)[0])
        self.assertNotIn("agora__opcao-aviso", html)

    def test_as_pastilhas_ficam_dentro_do_bloco_preso(self):
        html = self._html()
        bloco = _bloco(html, '<div class="agora__registro"', "</form>")
        self.assertIn('<ol class="series__lista">', bloco)
        self.assertIn("data-aguardando-rede", bloco)
        self.assertIn('class="registro registro--agora"', bloco)

    def test_com_o_exercicio_concluido_as_pastilhas_continuam_no_bloco(self):
        """O formulário vira "Tudo registrado"; a fileira, que é o histórico
        da sessão, continua no mesmo lugar."""
        sessao = escolher_opcao_de_hoje(self.pessoa)
        item = next(i for i in sessao.da_opcao(1) if i.measure == Measure.REPS)
        for _ in range(item.sets):
            services.append_set(self.pessoa, item.exercise, 40, reps=10, op_id="")
        url = "%s?exercicio=%d" % (reverse("workouts:now"), item.exercise_id)
        html = sem_scripts(self.client.get(url).content.decode())
        bloco = _bloco(html, '<div class="agora__registro"', "agora__extra")
        self.assertIn('<ol class="series__lista">', bloco)


class OBlocoPresoTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_quem_e_sticky_e_o_bloco_e_nao_o_formulario(self):
        blocos = _regras(self.css, ".agora__registro")
        self.assertTrue(blocos, "a regra .agora__registro sumiu")
        preso = [b for b in blocos if "position: sticky" in b]
        self.assertEqual(len(preso), 1, blocos)
        self.assertIn("background: var(--surface)", preso[0])
        formularios = _regras(self.css, ".registro--agora")
        self.assertTrue(formularios)
        for corpo in formularios:
            self.assertNotIn("sticky", corpo)

    def test_sem_barra_de_abas_o_bloco_cola_no_rodape(self):
        """E a media query vem DEPOIS da regra geral: com a mesma
        especificidade, quem vence é a última — a primeira versão escreveu
        o `bottom: 0` na media query geral de 60rem, que fica ANTES da
        regra do bloco no arquivo, e perdia."""
        geral = re.search(r"\.agora__registro\s*\{[^}]*position: sticky", self.css)
        self.assertIsNotNone(geral)
        medias = [
            m for m in re.finditer(r"@media \(min-width: 60rem\) \{(.*?)\n\}", self.css, re.S)
            if re.search(r"\.agora__registro\s*\{[^}]*bottom:\s*0", m.group(1))
        ]
        self.assertEqual(len(medias), 1)
        self.assertGreater(medias[0].start(), geral.start())

    def test_a_frase_da_opcao_saiu_com_o_css_dela(self):
        """Ficha única (17/09/2026): a frase "Opção N, a recomendada de hoje"
        não existe mais — nem a regra órfã dela no CSS."""
        self.assertIsNone(_regra(self.css, ".agora__opcao-aviso"))


class OFocoVoltaAoRegistroTests(SimpleTestCase):
    """U7 (16/09/2026): a página seguinte abre em `#registro`, e o alvo do
    fragmento deixa espaço acima para "Série N de M" e o descanso — sem a
    margem de rolagem o bloco colaria no topo e o relógio ficaria fora."""

    def test_o_bloco_tem_margem_de_rolagem(self):
        css = sem_comentarios(CSS.read_text(encoding="utf-8"))
        preso = [b for b in _regras(css, ".agora__registro") if "position: sticky" in b]
        self.assertEqual(len(preso), 1)
        self.assertRegex(preso[0], r"scroll-margin-top:")
        # Foco programático no bloco não pode desenhar anel: ele é alvo, não controle.
        self.assertRegex(css, r"\.agora__registro:focus\s*\{[^}]*outline:\s*none")
