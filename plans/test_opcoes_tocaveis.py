"""FASE 2 — a opção A/B para de parecer um bloco de informação.

O DEFEITO. Cada opção do cardápio é um `<details>`: a linha visível traz letra,
nome, calorias, proteína e tempo, e o botão que REGISTRA a refeição mora dentro
do corpo colapsado. Quem abre a tela vê duas linhas de informação e nenhuma
ação — para marcar o almoço é preciso primeiro descobrir que a linha abre.

A ação é o motivo da tela existir. Ela não pode estar atrás de uma descoberta.

A CORREÇÃO é de posição, não de contrato: o formulário sai de dentro do corpo e
vira irmão do `<details>`, sempre visível, com o rótulo dizendo o que faz e qual
opção registra. O corpo continua guardando o que é consulta — ingredientes e
modo de preparo —, que é exatamente o que uma sanfona deve guardar.

O QUE NÃO MUDA, e cada item aqui tem teste: os campos que o formulário envia
(`status` e `option`), os números mostrados na linha, e o papel secundário de
"Pulei" e "Comi outra coisa".
"""
import re

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import MealLog, MealStatus, NutritionPlan
from .test_saldo_sem_registro import com_plano


def corpo_da_sanfona(html):
    """Só o que está DENTRO dos corpos colapsados das opções.

    A asserção que importa nesta fase é sobre POSIÇÃO — o botão saiu de dentro
    da sanfona —, e uma busca na página inteira não distingue dentro de fora.
    """
    return "\n".join(re.findall(
        r'<div class="option__body">(.*?)</div>\s*</details>', html, re.S))


class ARegistrarNaoMoraMaisDentroDaSanfonaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = com_plano()
        self.client.force_login(self.pessoa)
        self.html = self.client.get(reverse("plans:today")).content.decode("utf-8")

    def test_a_tela_tem_opcoes_para_medir(self):
        """Controle positivo: sem opção na tela, tudo abaixo passaria vazio."""
        self.assertIn('class="option__summary"', self.html)

    def test_o_botao_de_registrar_esta_fora_do_corpo_colapsado(self):
        """Fora da sanfona E existindo.

        Só `assertNotIn` passaria por ausência: enquanto o botão se chamasse
        "Comi esta", "Registrar" não estava dentro do corpo porque não estava
        em lugar nenhum. As duas asserções juntas é que descrevem a mudança.
        """
        self.assertIn("Registrar", self.html)
        self.assertNotIn("Registrar", corpo_da_sanfona(self.html))
        self.assertNotIn("Comi esta", corpo_da_sanfona(self.html))

    def test_o_botao_diz_qual_opcao_registra(self):
        """"Comi esta" só funciona depois de abrir a opção certa.

        Fora da sanfona existem DOIS botões lado a lado, e "esta" deixa de ter
        antecedente: a letra é o que distingue um do outro.
        """
        self.assertIn("Registrar A", self.html)
        self.assertIn("Registrar B", self.html)

    def test_o_corpo_ainda_guarda_a_receita(self):
        """A sanfona não ficou vazia — ela ficou com o que é consulta."""
        corpo = corpo_da_sanfona(self.html)
        self.assertIn("option__items", corpo)

    def test_a_linha_visivel_preserva_os_numeros(self):
        for marca in ("option__kcal", "option__name", "option__label", "g P"):
            with self.subTest(marca=marca):
                self.assertIn(marca, self.html)

    def test_o_tempo_de_preparo_continua_na_linha(self):
        self.assertIn("min", self.html)

    def test_as_acoes_secundarias_continuam_secundarias(self):
        """"Pulei" e "Comi outra coisa" não podem virar botão primário."""
        self.assertIn("Pulei", self.html)
        self.assertIn("Comi outra coisa", self.html)
        # `btn--quiet` é a receita de ação secundária deste projeto.
        self.assertIn('value="skipped" class="btn btn--quiet"', self.html)


class OContratoDoFormularioNaoMudouTests(TestCase):
    """O botão mudou de lugar; o que ele envia não pode ter mudado.

    A fila offline e a view leem `status` e `option`. Mover o formulário e
    renomear um campo por descuido quebraria a marcação em silêncio — a tela
    continuaria bonita e nada seria gravado.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = com_plano()
        self.client.force_login(self.pessoa)
        self.plano = NutritionPlan.objects.filter(
            user=self.pessoa, is_active=True).first()
        self.slot = self.plano.slots.first()
        self.opcao = self.slot.options.first()

    def test_o_formulario_envia_status_e_opcao(self):
        """Os DOIS campos que a view e a fila offline leem.

        O valor de `option` não é fixado num pk: a tela desenha as duas opções
        do dia, escolhidas por `rodizio`, e `options.first()` pode não ser uma
        delas. O que o contrato exige é o par de campos, e que o id enviado
        pertença ao horário — as duas coisas medidas aqui.
        """
        html = self.client.get(reverse("plans:today")).content.decode("utf-8")

        self.assertIn('name="status" value="done"', html)
        enviados = {int(pk) for pk in re.findall(
            r'name="option" value="(\d+)"', html)}
        self.assertTrue(enviados, "nenhum formulário manda a opção")
        do_horario = set(self.slot.options.values_list("pk", flat=True))
        self.assertTrue(enviados & do_horario)

    def test_registrar_grava_a_refeicao(self):
        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": self.opcao.pk},
        )

        log = MealLog.objects.get(user=self.pessoa, slot=self.slot,
                                  date=timezone.localdate())
        self.assertEqual(log.status, MealStatus.DONE)
        self.assertEqual(log.chosen_option_id, self.opcao.pk)


class ToqueRepetidoNaoDuplicaRegistroTests(TestCase):
    """Dedo nervoso não pode produzir duas refeições.

    A garantia é do SERVIDOR e é estrutural: `log_meal` usa `update_or_create`
    com chave (pessoa, slot, dia), então o segundo envio reescreve a mesma
    linha. Não é um debounce no JavaScript — debounce falha com a rede lenta,
    que é exatamente quando o dedo bate de novo.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.pessoa = com_plano()
        self.client.force_login(self.pessoa)
        plano = NutritionPlan.objects.filter(user=self.pessoa, is_active=True).first()
        self.slot = plano.slots.first()
        self.opcoes = list(self.slot.options.all()[:2])

    def _marcar(self, opcao):
        return self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": opcao.pk},
        )

    def test_dois_toques_iguais_gravam_uma_refeicao(self):
        self._marcar(self.opcoes[0])
        self._marcar(self.opcoes[0])

        self.assertEqual(
            MealLog.objects.filter(user=self.pessoa, slot=self.slot,
                                   date=timezone.localdate()).count(),
            1,
        )

    def test_trocar_de_opcao_reescreve_em_vez_de_somar(self):
        """Tocou A, mudou de ideia, tocou B: sobra B, e uma linha só."""
        self._marcar(self.opcoes[0])
        self._marcar(self.opcoes[1])

        logs = MealLog.objects.filter(user=self.pessoa, slot=self.slot,
                                      date=timezone.localdate())
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().chosen_option_id, self.opcoes[1].pk)

    def test_uma_refeicao_registrada_nao_contamina_a_outra(self):
        """Isolamento entre horários: marcar o café não marca o almoço."""
        plano = NutritionPlan.objects.filter(user=self.pessoa, is_active=True).first()
        outro = plano.slots.exclude(pk=self.slot.pk).first()

        self._marcar(self.opcoes[0])

        self.assertFalse(
            MealLog.objects.filter(user=self.pessoa, slot=outro,
                                   date=timezone.localdate()).exists()
        )
