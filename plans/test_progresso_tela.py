# -*- coding: utf-8 -*-
"""A tela de Progresso, renderizada — e o que ela nunca pode desenhar.

O teste de `plans/test_evolucao.py` prende a REGRA (a janela não precede o
cadastro); este prende a TELA, que é onde o defeito aparecia: 24 linhas de
semana numa conta de três dias, sete delas começando antes de a conta
existir. Renderizar é o que separa "a função devolve certo" de "a página
mostra certo" — e foi renderizando que esta missão achou dois defeitos que
função nenhuma pegaria: coordenada de SVG localizada com vírgula, e a classe
de leitor de tela que este app não tem.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TrainingDay, WeightEntry
from plans import evolucao
from plans.models import HydrationLog
from plans.tests import create_complete_user


def _main(html):
    corpo = html.split("<main", 1)[1] if "<main" in html else html
    return corpo.split("</main>", 1)[0]


class ATelaNuncaDesenhaSemanaAnteriorAoCadastroTests(TestCase):
    """O defeito medido em produção (e6194b7), agora com rede embaixo."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="tela@exemplo.com")
        for weekday in (0, 2, 4):
            TrainingDay.objects.get_or_create(
                user=cls.user, weekday=weekday, defaults={"duration_min": 60}
            )

    def setUp(self):
        self.client.force_login(self.user)
        hoje = timezone.localdate()
        self.user.date_joined = timezone.now() - timedelta(days=2)
        self.user.save(update_fields=["date_joined"])
        HydrationLog.objects.update_or_create(
            user=self.user, date=hoje, defaults={"ml": 2000}
        )

    def _html(self, periodo=""):
        url = reverse("plans:history") + (("?p=" + periodo) if periodo else "")
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode()

    def test_nenhuma_data_desenhada_e_anterior_ao_cadastro(self):
        """A régua dura: toda data que a tela imprime nos gráficos tem de
        caber na vida da conta. Antes, o mapa começava oito semanas atrás."""
        nasceu = timezone.localtime(self.user.date_joined).date()
        for periodo in evolucao.PERIODOS:
            with self.subTest(periodo=periodo):
                html = _main(self._html(periodo))
                # As datas dos gráficos moram nos `<title>` dos quadrados e
                # das barras — é de lá que a leitura de tela as anuncia.
                datas = re.findall(r"<title>(\d{2}/\d{2})", html)
                self.assertTrue(datas, "a tela desenha alguma coisa")
                for texto in datas:
                    dia, mes = (int(p) for p in texto.split("/"))
                    # O ano é o de hoje ou o anterior (janela de 90 dias).
                    candidato = date(nasceu.year, mes, dia)
                    self.assertGreaterEqual(
                        candidato, nasceu,
                        "%s é anterior ao cadastro (%s)" % (texto, nasceu),
                    )

    def test_a_conta_nova_nao_tem_barra_de_semana_nenhuma(self):
        """Uma semana só não compara com nada: a barra desenharia 100% de si
        mesma. Quem responde nesse recorte é o mapa do dia."""
        html = _main(self._html("mes"))
        self.assertNotIn("colunas__barra", html)
        self.assertIn("mapa-dias__dia", html)

    def test_a_tela_diz_que_a_conta_e_nova_uma_vez_so(self):
        html = _main(self._html("trimestre"))
        # A CLASSE aparece duas vezes no mesmo elemento
        # (`previa-fantasma previa-fantasma--tela`): o que se conta é o
        # elemento, e contar a string seria contar o modificador.
        self.assertEqual(html.count('<p class="previa-fantasma'), 1)

    def test_o_seletor_de_periodo_marca_o_escolhido(self):
        html = _main(self._html("trimestre"))
        self.assertIn('href="?p=trimestre"', html)
        marcados = re.findall(r'href="\?p=(\w+)"[^>]*aria-current="true"', html)
        self.assertEqual(marcados, ["trimestre"], "um, e o que a URL pediu")
        self.assertEqual(html.count("periodo__item is-active"), 1)

    def test_periodo_invalido_na_url_nao_quebra_a_tela(self):
        resposta = self.client.get(reverse("plans:history") + "?p=../etc/passwd")
        self.assertEqual(resposta.status_code, 200)


class OSvgDaTelaEValidoTests(TestCase):
    """Coordenada de SVG é número que o NAVEGADOR lê.

    O app é pt-BR e o Django localiza número — `y="140,0"` é atributo
    inválido, e o efeito é a linha não desenhar: sem erro no console, sem
    nada vermelho num teste que só confira o status. Foi o que aconteceu em
    23/09/2026, e é por isso que esta classe existe.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="svg@exemplo.com")
        hoje = timezone.localdate()
        cls.user.date_joined = timezone.now() - timedelta(days=60)
        cls.user.save(update_fields=["date_joined"])
        for n, kg in enumerate((75.0, 74.2, 73.8, 73.1)):
            WeightEntry.objects.update_or_create(
                user=cls.user, date=hoje - timedelta(days=21 - n * 7),
                defaults={"weight_kg": Decimal(str(kg))},
            )
        for n in range(20):
            HydrationLog.objects.update_or_create(
                user=cls.user, date=hoje - timedelta(days=n), defaults={"ml": 2000}
            )

    def setUp(self):
        self.client.force_login(self.user)

    def test_nenhuma_coordenada_sai_com_virgula_decimal(self):
        html = self.client.get(reverse("plans:history") + "?p=mes").content.decode()
        ruins = re.findall(
            r'\s(?:x|y|x1|y1|x2|y2|cx|cy|width|height|r)="[-0-9]*,[0-9]', html
        )
        self.assertEqual(ruins, [], "coordenada localizada não desenha: %s" % ruins[:3])

    def test_o_caminho_da_linha_de_peso_tem_ponto_decimal(self):
        html = self.client.get(reverse("plans:history") + "?p=mes").content.decode()
        caminho = re.search(r'grafico-linha__traco" d="([^"]+)"', html)
        self.assertIsNotNone(caminho, "a linha do peso é desenhada")
        self.assertNotIn(",", caminho.group(1))
        self.assertTrue(caminho.group(1).startswith("M "))

    def test_a_tela_nao_chama_nada_de_plano(self):
        """`config/test_linguagem` já proíbe, e só não pegava porque o
        fixture de lá não tem refeição marcada — o ramo do "dia a dia" nunca
        era renderizado. Aqui ele é."""
        html = _main(self.client.get(reverse("plans:history")).content.decode())
        texto = re.sub(r"<[^>]+>", " ", html)
        self.assertIsNone(re.search(r"\bplanos?\b", texto, re.IGNORECASE))
