"""Testes da entrada por voz.

O interpretador mora no servidor justamente para caber aqui: em JavaScript,
dentro do template, ele só seria testável abrindo um navegador com microfone —
o que na prática significa não testado.

O que estes testes protegem não é o acerto: é o comportamento quando ele erra.
Reconhecimento de fala erra em silêncio, e um registro errado de água estraga a
ofensiva sem nunca dar mensagem de erro.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from . import services, voice
from .models import HydrationLog, MealLog, MealStatus
from .tests import CatalogFixture, create_complete_user


class Slot:
    """Um horário mínimo — o interpretador só olha `pk` e `name`."""

    def __init__(self, pk, name):
        self.pk = pk
        self.name = name


SLOTS = [
    Slot(1, "Café da manhã"),
    Slot(2, "Lanche da manhã"),
    Slot(3, "Almoço"),
    Slot(4, "Lanche da tarde"),
    Slot(5, "Jantar"),
]


class WaterSpeechTests(TestCase):
    def test_it_hears_a_number_in_millilitres(self):
        self.assertEqual(voice.interpretar("300 ml de água", SLOTS).ml, 300)

    def test_it_hears_containers(self):
        casos = [
            ("um copo de água", 250),
            ("uma garrafinha de água", 500),
            ("uma garrafa de água", 750),
            ("meio litro de água", 500),
            ("duas garrafinhas de água", 1000),
            ("um litro de água", 1000),
        ]
        for frase, esperado in casos:
            with self.subTest(frase=frase):
                self.assertEqual(voice.interpretar(frase, SLOTS).ml, esperado)

    def test_it_survives_missing_accents(self):
        """A transcrição nem sempre acentua, e "agua" é o caso mais comum."""
        self.assertEqual(voice.interpretar("500 ml de agua", SLOTS).ml, 500)

    def test_it_keeps_the_number_the_person_said(self):
        """Os botões têm três volumes porque tocar precisa de conjunto pequeno.
        Falar não: quem diz "trezentos" quis dizer trezentos, e encaixar isso
        no botão de 250 faria o app ficar calado sobre 50 ml registrados."""
        self.assertEqual(voice.interpretar("300 ml de água", SLOTS).ml, 300)
        self.assertEqual(voice.interpretar("330 ml de água", SLOTS).ml, 330)

    def test_it_rounds_to_the_nearest_ten(self):
        self.assertEqual(voice.interpretar("333 ml de água", SLOTS).ml, 330)

    def test_an_absurd_volume_is_refused_with_the_number_it_heard(self):
        """"Dois" virando "dois mil" é o engano que o microfone comete. Dizer o
        número ouvido é o que deixa a pessoa entender o que deu errado."""
        intencao = voice.interpretar("3 litros de água", SLOTS)

        self.assertFalse(intencao.entendeu)
        self.assertIn("3000", intencao.erro)

    def test_a_tiny_volume_is_refused(self):
        self.assertFalse(voice.interpretar("5 ml de água", SLOTS).entendeu)

    def test_water_wins_over_the_eating_verb(self):
        """"Tomei água" tem o verbo de comer dentro. Sem a precedência, viraria
        refeição fora do plano."""
        intencao = voice.interpretar("tomei 500 ml de água", SLOTS)

        self.assertEqual(intencao.tipo, "agua")
        self.assertEqual(intencao.ml, 500)

    def test_water_without_a_quantity_asks_again(self):
        intencao = voice.interpretar("bebi água", SLOTS)

        self.assertFalse(intencao.entendeu)
        self.assertIn("quanta água", intencao.erro)


class MealSpeechTests(TestCase):
    def test_it_finds_the_meal_by_name(self):
        intencao = voice.interpretar("comi frango no almoço", SLOTS)

        self.assertEqual(intencao.tipo, "refeicao")
        self.assertEqual(intencao.slot_nome, "Almoço")
        self.assertEqual(intencao.status, "off_plan")

    def test_it_finds_the_meal_by_nickname(self):
        """Ninguém fala "Lanche da tarde" — fala "lanche"."""
        casos = [
            ("comi banana no lanche", "Lanche"),
            ("pulei a janta", "Jantar"),
            ("comi ovo no café", "Café"),
        ]
        for frase, prefixo in casos:
            with self.subTest(frase=frase):
                intencao = voice.interpretar(frase, SLOTS)
                self.assertTrue(intencao.slot_nome.startswith(prefixo), intencao.slot_nome)

    def test_skipping_is_heard_as_skipping(self):
        for frase in ("pulei o jantar", "não comi o almoço", "deixei de comer o jantar"):
            with self.subTest(frase=frase):
                self.assertEqual(voice.interpretar(frase, SLOTS).status, "skipped")

    def test_what_was_said_is_kept_whole(self):
        """Guardar a frase, e não uma extração: "200 g de frango" sozinho perde
        o "no almoço" que dava sentido a ele."""
        intencao = voice.interpretar("comi 200g de frango no almoço", SLOTS)

        self.assertIn("200g de frango", intencao.nota)
        self.assertIn("almoço", intencao.nota)

    def test_a_skipped_meal_carries_no_note(self):
        """Não há o que anotar sobre o que não foi comido."""
        self.assertEqual(voice.interpretar("pulei o jantar", SLOTS).nota, "")

    def test_food_without_a_meal_asks_which_one(self):
        intencao = voice.interpretar("comi pizza", SLOTS)

        self.assertFalse(intencao.entendeu)
        self.assertIn("qual refeição", intencao.erro)

    def test_nonsense_gets_an_example_and_not_a_shrug(self):
        intencao = voice.interpretar("blergh", SLOTS)

        self.assertFalse(intencao.entendeu)
        self.assertIn("300 ml de água", intencao.erro)

    def test_silence_is_not_an_error_message_about_understanding(self):
        self.assertIn("Não ouvi", voice.interpretar("", SLOTS).erro)

    def test_it_never_invents_macros_from_a_sentence(self):
        """Chutar macro a partir de fala contaminaria o histórico — e o
        histórico é o que sustenta todo o resto do app."""
        intencao = voice.interpretar("comi 200g de frango no almoço", SLOTS)

        self.assertEqual(intencao.status, "off_plan")
        for campo in ("kcal", "protein_g", "carb_g"):
            self.assertFalse(hasattr(intencao, campo))


class VoiceEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.client.force_login(self.user)

    def _falar(self, frase):
        return self.client.post(reverse("plans:voice"), {"frase": frase})

    def test_the_endpoint_proposes_and_never_acts(self):
        """A view devolve o que FARIA. Nada é gravado até a confirmação."""
        resposta = self._falar("300 ml de água")

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["entendeu"])
        self.assertFalse(HydrationLog.objects.filter(user=self.user).exists())

    def test_the_proposal_carries_what_the_form_needs(self):
        dados = self._falar("300 ml de água").json()

        self.assertEqual(dados["tipo"], "agua")
        self.assertEqual(dados["ml"], 300)
        self.assertIn("300", dados["resumo"])

    def test_a_meal_proposal_points_at_a_real_slot(self):
        dados = self._falar("comi frango no almoço").json()

        self.assertEqual(dados["tipo"], "refeicao")
        self.assertTrue(
            self.plan.slots.filter(pk=dados["slot_id"]).exists(),
            "o id proposto não é um horário deste plano",
        )

    def test_confirming_water_actually_records_it(self):
        dados = self._falar("300 ml de água").json()

        self.client.post(reverse("plans:log_hydration"), {"ml": dados["ml"]})

        self.assertEqual(HydrationLog.objects.get(user=self.user).ml, 300)

    def test_confirming_a_meal_records_the_sentence(self):
        dados = self._falar("comi 200g de frango no almoço").json()

        self.client.post(
            reverse("plans:mark_meal", args=[dados["slot_id"]]),
            {"status": dados["status"], "notes": dados["nota"]},
        )

        log = MealLog.objects.get(user=self.user, slot_id=dados["slot_id"])
        self.assertEqual(log.status, MealStatus.OFF_PLAN)
        self.assertIn("frango", log.notes)
        # Comida fora do plano não traz macro: não sabemos o que foi.
        self.assertEqual(log.kcal, Decimal("0"))

    def test_a_sentence_it_cannot_read_says_why(self):
        dados = self._falar("blergh").json()

        self.assertFalse(dados["entendeu"])
        self.assertTrue(dados["erro"])

    def test_the_mic_only_appears_when_the_browser_can_hear(self):
        """Um botão de microfone que não escuta é pior que a ausência dele."""
        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn("data-voz", html)
        self.assertIn("webkitSpeechRecognition", html)
        self.assertIn("caixa.hidden = false", html)

    def test_the_page_speaks_portuguese_to_the_recogniser(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn('motor.lang = "pt-BR"', html)

    def test_it_asks_for_login(self):
        self.client.logout()
        resposta = self._falar("300 ml de água")

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

    def test_one_person_never_marks_a_meal_for_another(self):
        outro = create_complete_user(email="outro@exemplo.com")
        plano_alheio = services.create_plan(outro)
        alheio = plano_alheio.slots.first()

        resposta = self.client.post(
            reverse("plans:mark_meal", args=[alheio.pk]), {"status": "skipped"}
        )

        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(MealLog.objects.filter(user=outro).exists())
