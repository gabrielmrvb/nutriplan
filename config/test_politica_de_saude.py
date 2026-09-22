"""A Política tem a seção de DADOS DE SAÚDE DO APARELHO, e ela é exigência
de loja, não enfeite (Fase 3 da missão Capacitor, 22/09/2026).

A Apple recusa app com HealthKit cuja política não diga o que é lido e para
quê; o Health Connect exige que o app MOSTRE uma política quando a pessoa
toca em "política de privacidade" na folha de permissões — e é esta âncora
(`#saude-do-aparelho`) que o `privacy_policy_url` do Android abre.

Três negativas são as que mais importam, e por isso têm teste: o app não
ESCREVE no Apple Saúde / Health Connect, não lê em segundo plano, e não
compartilha esses dados com ninguém. Se um dia alguma delas deixar de ser
verdade, é este teste que precisa ser mudado em voz alta.
"""
import plistlib
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

RAIZ = Path(__file__).resolve().parent.parent
ANCORA = "saude-do-aparelho"


class APoliticaCobreOsDadosDeSaudeDoAparelhoTests(TestCase):
    def setUp(self):
        self.html = self.client.get(reverse("privacidade")).content.decode()

    def test_a_secao_existe_com_a_ancora_que_o_health_connect_abre(self):
        self.assertIn('id="%s"' % ANCORA, self.html)

    def test_ela_diz_o_que_le_e_para_que(self):
        for trecho in ("Apple Saúde", "Health Connect", "Peso", "Treinos de corrida", "30 dias", "Importar do aparelho"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, self.html)

    def test_ela_diz_as_tres_negativas(self):
        secao = self.html[self.html.index('id="%s"' % ANCORA):]
        secao = secao[:secao.index("</section>")]
        texto = re.sub(r"<[^>]+>", " ", secao)
        self.assertIn("não", texto)
        for negativa in ("escreve", "segundo plano", "compartilha"):
            with self.subTest(negativa=negativa):
                self.assertIn(negativa, texto)

    def test_ela_diz_a_base_legal_e_como_revogar(self):
        self.assertIn("art. 11, I", self.html)
        self.assertIn("revogar", self.html)


class OAppApontaParaEssaSecaoTests(SimpleTestCase):
    def test_o_android_abre_a_ancora_na_folha_de_permissoes(self):
        strings = (RAIZ / "nativo" / "android" / "app" / "src" / "main" / "res" / "values" / "strings.xml").read_text(encoding="utf-8")
        self.assertIn("privacy_policy_url", strings)
        self.assertIn("/privacidade/#" + ANCORA, strings)

    def test_as_strings_do_ios_dizem_o_dado_o_uso_e_a_condicao(self):
        with open(RAIZ / "nativo" / "ios" / "App" / "App" / "Info.plist", "rb") as f:
            plist = plistlib.load(f)
        ler = plist["NSHealthShareUsageDescription"]
        for trecho in ("peso", "corrida", "importar"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, ler.lower())
        self.assertGreater(len(ler), 80, "texto vago é motivo comum de rejeição da Apple")
        self.assertIn("não grava", plist["NSHealthUpdateUsageDescription"].lower())

    def test_o_app_declara_so_as_tres_permissoes_de_saude_que_usa(self):
        manifesto = (RAIZ / "nativo" / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
        usadas = {"READ_WEIGHT", "READ_EXERCISE", "READ_DISTANCE"}
        declaradas = set(re.findall(r'android\.permission\.health\.(\w+)" />', manifesto))
        removidas = set(re.findall(r'android\.permission\.health\.(\w+)" tools:node="remove"', manifesto))
        self.assertEqual(declaradas - removidas, usadas)
        self.assertIn("READ_HEART_RATE", removidas, "o que o plugin traz e o app não usa é removido")
