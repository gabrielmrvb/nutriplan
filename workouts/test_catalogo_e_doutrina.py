"""Catálogo e doutrina, uma impressão digital só (parte 2, 28/09/2026).

Três textos que o app mostra ou que a doutrina afirma, e que diziam outra
coisa que a verdade:

- R8 (QA exploratório de 27/09): o subtítulo do "Peito, tríceps e ombro"
  dizia "Empurrar — peitoral, sinergista e deltoide" na primeira tela de
  quem está começando. "Sinergista" é palavra de livro de fisiologia;
- item 12 (a letra E do ABCDE, #190): o TREINO.md dizia que "Braços" fecha
  em 23–24 séries, e a faixa da tabela promete 55 minutos para `dois_grupos`
  — a ficha única entrega 27 séries e 52 minutos. Decisão do dono: a ficha
  manda, o texto segue;
- BA17/BA18 (caça-bugs de 27/09): a porta de Corridas na tela do Treino só
  falava de GPS, e o rodapé da lista afirmava "A distância vem das leituras
  de GPS do seu aparelho" com três corridas registradas à mão.
"""
import json
import re
from datetime import timedelta
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from accounts.models import DuracaoTreino, Musculacao, TrainingDay
from config.test_linguagem import texto_visivel
from plans.tests import create_complete_user
from workouts import services
from workouts.models import Corrida

RAIZ = Path(__file__).resolve().parent.parent
SPLITS = RAIZ / "workouts" / "data" / "splits.json"
TREINO_MD = RAIZ / "docs" / "briefs" / "treino" / "TREINO.md"


class OSubtituloDoTreinoFalaALinguaDeQuemTreinaTests(SimpleTestCase):
    """R8: o subtítulo é a segunda linha que a pessoa lê na ficha
    (`routine.html`, `ficha.html`), e a iniciante das personas parou em
    "sinergista" — palavra que ninguém usa na academia."""

    def setUp(self):
        self.modelos = json.loads(SPLITS.read_text(encoding="utf-8"))

    def test_nenhum_subtitulo_do_catalogo_diz_sinergista(self):
        com_jargao = [
            "%s %s: %s" % (m["split"], m["label"], m["focus"])
            for m in self.modelos
            if "sinergista" in m.get("focus", "").lower()
        ]
        self.assertEqual(com_jargao, [])

    def test_o_empurrar_do_abc_diz_peito_triceps_e_ombro(self):
        """Controle positivo: a letra ainda tem subtítulo, e ele nomeia os
        três grupos que o nome promete — não sumiu nem virou genérico."""
        abc_a = next(m for m in self.modelos if (m["split"], m["label"]) == ("abc", "A"))
        self.assertEqual(abc_a["focus"], "Empurrar — peito, tríceps e ombro")


class OTreinoMdDizOQueAFichaDeBracosEntregaTests(TestCase):
    """Item 12: o TREINO.md afirma que a tabela cobre toda letra, e a letra E
    do ABCDE ("Braços") saiu dela com a ficha única (#190). O dono decidiu
    que o texto segue a ficha; este teste impede o texto de envelhecer de
    novo — lê o número do documento e o compara com o que o motor monta."""

    FRASE = re.compile(
        r'"Braços", a letra E do ABCDE, fecha em (\d+)\s+séries e \*\*(\d+)\s+minutos\*\*'
        r"\s+no intermediário e no avançado \((\d+)\s+no iniciante\)"
    )

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def _letra_e(self, nivel):
        user = create_complete_user(
            email="bracos-%s@exemplo.com" % nivel, experiencia=nivel, split_preference="one",
            duracao_treino=DuracaoTreino.COMPLETO,
        )
        TrainingDay.objects.filter(user=user).delete()
        for dia in range(5):
            TrainingDay.objects.create(user=user, weekday=dia, duration_min=60)
        plano = services.create_routine(user)
        self.assertEqual(plano.split, "abcde")
        letra = next(s for s in plano.sessions.prefetch_related("exercises__exercise") if s.label == "E")
        self.assertEqual(letra.name, "Braços")
        return letra

    def test_a_linha_da_letra_e_e_a_que_o_motor_monta(self):
        achado = self.FRASE.search(" ".join(TREINO_MD.read_text(encoding="utf-8").split()))
        self.assertIsNotNone(achado, "TREINO.md sem a frase da letra E do ABCDE")
        series, minutos, minutos_iniciante = (int(g) for g in achado.groups())
        for nivel in ("intermediario", "avancado"):
            letra = self._letra_e(nivel)
            with self.subTest(nivel=nivel):
                self.assertEqual(sum(i.sets for i in letra.da_opcao(1)), series)
                self.assertEqual(letra.minutos_da_opcao(1), minutos)
        self.assertEqual(self._letra_e("iniciante").minutos_da_opcao(1), minutos_iniciante)


class ACorridaAMaoApareceOndeOGpsApareceTests(TestCase):
    """BA17/BA18: a pessoa das personas que só corre registrou três corridas
    à mão e leu, na porta do Treino, só "Registrar corrida com GPS" e, no
    rodapé da lista, que a distância "vem das leituras de GPS do seu
    aparelho" — as três distâncias ela mesma digitou."""

    def setUp(self):
        self.pessoa = create_complete_user(email="so-corre@exemplo.com", musculacao=Musculacao.NAO)
        TrainingDay.objects.filter(user=self.pessoa).delete()
        self.client.force_login(self.pessoa)

    def _cartao_da_corrida(self):
        html = self.client.get("/treino/").content.decode()
        cartao = html.split(">Corrida</h2>", 1)[1].split("</section>", 1)[0]
        return texto_visivel(cartao)

    def test_a_porta_do_treino_diz_que_da_para_registrar_a_mao(self):
        cartao = self._cartao_da_corrida()
        self.assertIn("à mão", cartao)
        # O limite do GPS continua dito antes de abrir
        # (`ACorridaTemPortaTests.test_a_porta_avisa_do_limite_antes_de_abrir`).
        self.assertIn("tela acesa", cartao)

    def test_o_rodape_da_lista_nao_atribui_ao_gps_a_distancia_digitada(self):
        inicio = timezone.now() - timedelta(days=1)
        for n in range(3):
            Corrida.objects.create(
                user=self.pessoa, op_id="mao-%d" % n, origem=Corrida.Origem.MANUAL,
                comecou_em=inicio - timedelta(days=n), terminou_em=inicio - timedelta(days=n) + timedelta(minutes=30),
                distancia_m=5000, duracao_s=1800,
            )
        texto = texto_visivel(self.client.get("/treino/corridas/").content.decode())
        # Controle positivo: a lista está na tela, com o selo "à mão".
        self.assertIn("à mão", texto)
        self.assertNotIn("A distância vem das leituras de GPS", texto)
        self.assertIn("Nas corridas com GPS, a distância vem das leituras do seu aparelho", texto)
