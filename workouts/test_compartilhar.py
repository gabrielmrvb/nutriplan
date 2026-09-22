# -*- coding: utf-8 -*-
"""Compartilhar o placar como PNG (retenção, item 5 — 21/09/2026).

O treino fechado ganha um botão "Compartilhar" que desenha, NO NAVEGADOR
(canvas, sem servidor, sem dependência nova), uma imagem 1080×1350 no
design NERVURA com cinco dados e nada mais: nome da sessão, séries
registradas, kg levantados, minutos entre o primeiro e o último registro
(ou "—") e a marca. O servidor escreve os cinco em `data-compartilhar-*`
num único elemento, já formatados em pt-BR, e `pwa.js` lê — ele NÃO
recalcula nada e NÃO lê o resto da página: é o que garante que peso
corporal, e-mail e nome da pessoa não entram na imagem por acidente (a
mesma régua de `card.js` e de `test_compartilhar_honesto`).

O caminho de compartilhar/baixar é UM no repositório —
`NutriPlanCard.compartilhar` (`card.js`): Web Share com arquivo quando
`navigator.canShare({files})` diz sim, senão `<a download>` criado na
hora. Uma segunda cópia em `pwa.js` seria a que envelhece.
"""
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.template.defaultfilters import floatformat
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog
from workouts.tests import create_user, sem_scripts

JS = Path(settings.BASE_DIR) / "static" / "js" / "pwa.js"
CARD_JS = Path(settings.BASE_DIR) / "static" / "js" / "card.js"
AGORA = Path(settings.BASE_DIR) / "templates" / "workouts" / "agora.html"

BOTAO = re.compile(r"<button\b[^>]*data-compartilhar-placar[^>]*>.*?</button>", re.S)


def _sem_comentarios(js):
    """O JS sem `/* */` nem `//`: a armadilha do repositório é afirmar
    comportamento lendo um comentário que só descreve o que se pretendia."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"^\s*//.*$", "", js, flags=re.M)


class OBotaoDeCompartilharNoPlacarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="placar@exemplo.com", weekdays=(timezone.localdate().weekday(),))
        services.sync_active_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        estado = services.estado_do_treino(self.pessoa)
        self.itens = estado.itens
        self.sessao = estado.sessao
        for item in self.itens:
            for numero in range(1, item.sets + 1):
                services.record_load(self.pessoa, item.exercise, Decimal("40"), set_number=numero, reps=10)

    def _placar(self):
        html = sem_scripts(self.client.get(reverse("workouts:now")).content.decode())
        return html.split('class="card fim recompensa"', 1)[1].split("</section>", 1)[0]

    def _botao(self):
        m = BOTAO.search(self._placar())
        self.assertIsNotNone(m, "o placar do treino fechado tem o botão de compartilhar")
        return m.group(0)

    def _atributo(self, botao, nome):
        m = re.search(r'data-compartilhar-%s="([^"]*)"' % nome, botao)
        self.assertIsNotNone(m, "o botão leva data-compartilhar-%s" % nome)
        return m.group(1)

    def test_o_treino_fechado_tem_o_botao_com_os_cinco_dados_formatados(self):
        """Os cinco dados da imagem saem do SERVIDOR, prontos: o JS desenha
        o que recebe. Kg com ponto de milhar (pt-BR), a data no nome do
        arquivo em ISO, e "—" quando a tela não tem minutos para mostrar —
        registros feitos no mesmo segundo arredondam para zero, e zero não
        vira número na imagem."""
        botao = self._botao()
        self.assertIn('type="button"', botao)
        self.assertIn("Compartilhar", botao)
        self.assertRegex(botao, r'class="[^"]*\bbtn\b[^"]*\bbtn--ghost\b')
        self.assertEqual(self._atributo(botao, "sessao"), "Treino %s · %s" % (self.sessao.label, self.sessao.name))
        self.assertEqual(self._atributo(botao, "series"), str(sum(item.sets for item in self.itens)))
        esperado = Decimal(sum(item.sets * 400 for item in self.itens))
        self.assertEqual(self._atributo(botao, "kg"), floatformat(esperado, "0g"))
        self.assertEqual(self._atributo(botao, "minutos"), "—")
        self.assertEqual(self._atributo(botao, "data"), timezone.localdate().isoformat())

    def test_os_minutos_da_imagem_sao_os_da_tela(self):
        """O mesmo intervalo entre o primeiro e o último registro que a
        tela mostra — não a estimativa da ficha, que já saiu como "47 min"
        para registros separados por um minuto."""
        primeiro = ExerciseLog.objects.filter(user=self.pessoa).order_by("created_at", "pk").first()
        ExerciseLog.objects.filter(pk=primeiro.pk).update(created_at=primeiro.created_at - timedelta(minutes=47))
        self.assertEqual(services.estado_do_treino(self.pessoa).minutos_entre_registros, 47)
        self.assertEqual(self._atributo(self._botao(), "minutos"), "47")

    def test_no_meio_do_treino_nao_ha_botao(self):
        """4 de 16 séries já viraram "treino concluído" num story uma vez
        (UX P1-12). O botão só existe quando a ficha inteira está coberta."""
        outra = create_user(email="meio@exemplo.com", weekdays=(timezone.localdate().weekday(),))
        services.sync_active_routine(outra)
        self.client.force_login(outra)
        html = sem_scripts(self.client.get(reverse("workouts:now")).content.decode())
        self.assertFalse(services.estado_do_treino(outra).concluido)
        self.assertNotIn("data-compartilhar-placar", html)
        self.assertNotIn("Compartilhar", html)

    def test_o_bloco_de_compartilhar_nao_carrega_peso_corporal_nem_quem_e_a_pessoa(self):
        """A imagem vai para o story de alguém. `create_user` grava 82,4 kg
        de peso corporal e o e-mail é o login: nenhum dos dois pode estar
        no markup que o JS lê — nem por atributo, nem por texto."""
        botao = self._botao()
        atributos = re.findall(r'data-compartilhar-([a-z-]+)=', botao)
        # `heroi`/`heroi-rotulo` (22/09/2026): o número grande do cartão é o
        # da tela — kg com carga, repetições no treino de peso do corpo.
        self.assertEqual(sorted(atributos), ["data", "heroi", "heroi-rotulo", "kg", "minutos", "series", "sessao"])
        for proibido in ("82,4", "82.4", "weight", "peso", "placar@exemplo.com", "@", "kcal"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, botao)
        template = AGORA.read_text(encoding="utf-8")
        bloco = BOTAO.search(re.sub(r"{% comment %}.*?{% endcomment %}", "", template, flags=re.S)).group(0)
        for proibido in ("weight", "peso", "email", "user.", "profile", "first_name", "kcal"):
            with self.subTest(template=proibido):
                self.assertNotIn(proibido, bloco)


class OPwaJsDesenhaECompartilhaTests(SimpleTestCase):
    def setUp(self):
        self.js = JS.read_text(encoding="utf-8")
        self.card = _sem_comentarios(CARD_JS.read_text(encoding="utf-8"))

    def _secao(self):
        """A seção do placar, do cabeçalho dela até o fim do arquivo, SEM os
        comentários: o que se afirma abaixo é sobre código que roda."""
        self.assertIn("COMPARTILHAR O PLACAR", self.js, "a seção tem o cabeçalho das outras")
        inicio = self.js.rfind("/*", 0, self.js.index("COMPARTILHAR O PLACAR"))
        return _sem_comentarios(self.js[inicio:])

    def test_o_pwa_js_desenha_o_placar_em_1080_por_1350_e_nomeia_o_arquivo_pela_data(self):
        """Retrato 4:5, o formato que feed e story aceitam sem cortar; o
        arquivo diz o que é e de quando é, para a galeria de quem baixa."""
        secao = self._secao()
        self.assertIn('"nutriplan-treino-"', secao)
        self.assertIn("1080", secao)
        self.assertIn("1350", secao)
        self.assertIn("getContext(\"2d\")", secao)
        self.assertIn('"image/png"', self.card)

    def test_as_fontes_da_direcao_sao_pedidas_antes_de_desenhar_e_nunca_travam(self):
        """O canvas não espera pelo CSS: sem `document.fonts.load` a
        primeira imagem sai em sans-serif. E a espera tem teto — sem rede,
        `fonts.load` pode nunca resolver, e o botão ficaria mudo."""
        secao = self._secao()
        self.assertIn('document.fonts.load', secao)
        self.assertIn('"Big Shoulders Display"', secao)
        self.assertIn("Archivo", secao)
        self.assertIn("ESPERA_FONTES_MS = 1500;", secao)
        self.assertIn("setTimeout(resolve, ESPERA_FONTES_MS)", secao)

    def test_as_cores_vem_dos_tokens_com_a_paleta_nervura_de_reserva(self):
        """O canvas não lê CSS, mas a fonte da verdade é o token; a reserva
        são os hex de Ferro da direção, para o card não sair preto."""
        secao = self._secao()
        for token_, reserva in (("--bg", "#0b140f"), ("--brand", "#43df7a"), ("--terra", "#e8a33d"),
                                ("--text", "#f2f6f2"), ("--text-mute", "#a9bbae")):
            with self.subTest(token=token_):
                self.assertRegex(secao, r'"%s",\s*"%s"' % (re.escape(token_), reserva))

    def test_o_compartilhar_e_um_so_no_repositorio(self):
        """Web Share com arquivo quando o aparelho sabe, `<a download>`
        quando não — a lógica mora em `card.js` e o placar a REUSA."""
        secao = self._secao()
        self.assertIn("NutriPlanCard.compartilhar(", secao)
        self.assertNotIn("navigator.share", secao)
        self.assertIn("navigator.canShare", self.card)
        self.assertRegex(self.card, r"navigator\s*\.share\(\{ files: \[arquivo\]")
        self.assertIn("link.download = nome", self.card)

    def test_o_js_le_os_data_e_nao_a_pagina(self):
        """Nenhum `querySelector` fora do botão e nenhum número calculado:
        o servidor escreveu os cinco, o JS desenha os cinco."""
        secao = self._secao()
        for dado in ("compartilharSessao", "compartilharSeries", "compartilharKg",
                     "compartilharMinutos", "compartilharData"):
            with self.subTest(dado=dado):
                self.assertIn("dataset." + dado, secao)
        self.assertNotIn("console.", secao)
        self.assertNotIn("weight", secao)
        self.assertIn('addEventListener("click"', secao)
