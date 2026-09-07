# -*- coding: utf-8 -*-
"""O que a pessoa registra em "Comi outra coisa" tem de chegar na tela.

Os testes que já existiam provavam que a descrição e os macros eram GRAVADOS
(`plans/tests.py`, no `assertEqual(log.notes, ...)`), e paravam ali. Gravar era
metade do caminho: o painel do dia somava só `status=DONE` e o cartão imprimia
um rótulo fixo, então tudo o que a pessoa contava era escrito no banco e nunca
lido. Estes testes cobrem a metade que faltava — a LEITURA.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Food
from plans.models import MealLog, MealStatus
from plans import tracking


class OQueFoiComidoForaDoPlanoContaTests(TestCase):
    """Medido na auditoria: 256 kcal gravados, painel parado no mesmo número."""

    fixtures = []

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="fora-do-plano@exemplo.com", password="senha-bem-forte-123"
        )
        self.arroz = Food.objects.create(
            name="Arroz de teste", kcal=Decimal("128"),
            protein_g=Decimal("2.5"), carb_g=Decimal("28"),
            fat_g=Decimal("0.2"),
        )

    def _plano_com_um_horario(self):
        from plans import services
        from accounts.models import Profile
        Profile.objects.update_or_create(
            user=self.pessoa,
            defaults={"sex": "M", "birth_date": timezone.localdate().replace(year=1990),
                      "height_cm": 178, "goal": "cut", "activity_level": "sedentary",
                      "onboarding_step": 7},
        )
        from accounts.models import WeightEntry
        WeightEntry.objects.update_or_create(
            user=self.pessoa, date=timezone.localdate(),
            defaults={"weight_kg": Decimal("82.5")},
        )
        plano, _ = services.sync_active_plan(self.pessoa)
        return plano

    def test_os_macros_do_que_comeu_fora_entram_no_total_do_dia(self):
        """O app pergunta o que foi comido, calcula os macros e grava. Se o
        total do dia ignora isso, ele subnotifica o que a própria pessoa
        acabou de contar — e o número que ela vê fica menor que a verdade que
        ela mesma registrou."""
        plano = self._plano_com_um_horario()
        slot = plano.slots.first()

        tracking.log_meal(
            self.pessoa, slot, MealStatus.OFF_PLAN, notes="Feijoada do vizinho",
            macros=tracking.macros_de_itens([(self.arroz, Decimal("200"))]),
        )

        resumo = tracking.day_summary(self.pessoa, plano, timezone.localdate())

        self.assertEqual(resumo["consumed_kcal"], 256)

    def test_aderencia_NAO_conta_o_que_foi_comido_fora(self):
        """CONTROLE NEGATIVO, e é o que impede a correção acima de virar outra.

        Comer fora do plano é registro honesto; não é seguir o plano. Se o
        contador subisse junto com a caloria, "comi outra coisa" viraria uma
        forma de fechar o dia em 100% sem comer nada do cardápio.
        """
        plano = self._plano_com_um_horario()
        slot = plano.slots.first()

        tracking.log_meal(
            self.pessoa, slot, MealStatus.OFF_PLAN, notes="Feijoada do vizinho",
            macros=tracking.macros_de_itens([(self.arroz, Decimal("200"))]),
        )

        resumo = tracking.day_summary(self.pessoa, plano, timezone.localdate())

        self.assertEqual(resumo["no_plano"], 0)
        self.assertEqual(resumo["fora_do_plano"], 1)

    def test_o_historico_soma_o_mesmo_que_a_tela_de_hoje(self):
        """As duas somas moravam em funções diferentes com o mesmo filtro
        errado. Corrigir uma e esquecer a outra devolveria a divergência entre
        telas por outro caminho."""
        plano = self._plano_com_um_horario()
        slot = plano.slots.first()

        tracking.log_meal(
            self.pessoa, slot, MealStatus.OFF_PLAN, notes="Feijoada do vizinho",
            macros=tracking.macros_de_itens([(self.arroz, Decimal("200"))]),
        )

        hoje = tracking.day_summary(self.pessoa, plano, timezone.localdate())
        linha = next(l for l in tracking.history(self.pessoa)
                     if l["date"] == timezone.localdate())

        self.assertEqual(linha["kcal"], hoje["consumed_kcal"])

    def test_quem_nao_descreve_alimento_nenhum_continua_com_zero(self):
        """CONTROLE POSITIVO da regra antiga, que não pode ter mudado: quem
        escreve só "comi na casa da minha mãe" não recebe caloria inventada."""
        plano = self._plano_com_um_horario()
        slot = plano.slots.first()

        tracking.log_meal(self.pessoa, slot, MealStatus.OFF_PLAN,
                          notes="Comi na casa da minha mãe", macros=None)

        resumo = tracking.day_summary(self.pessoa, plano, timezone.localdate())

        self.assertEqual(resumo["consumed_kcal"], 0)


class ATelaMostraOQuePediuParaAPessoaEscreverTests(TestCase):
    """A descrição é OBRIGATÓRIA e não aparecia em lugar nenhum.

    `MealLog.notes` era lido por zero templates — conferido por varredura no
    repositório inteiro. O app exigia a frase, guardava a frase e devolvia
    "Comeu outra coisa", que é exatamente o rótulo genérico que o botão veio
    substituir.
    """

    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="mostra-a-descricao@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.pessoa)

    def _preparar(self):
        from plans import services
        from accounts.models import Profile, WeightEntry
        Profile.objects.update_or_create(
            user=self.pessoa,
            defaults={"sex": "M", "birth_date": timezone.localdate().replace(year=1990),
                      "height_cm": 178, "goal": "cut", "activity_level": "sedentary",
                      "onboarding_step": 7},
        )
        WeightEntry.objects.update_or_create(
            user=self.pessoa, date=timezone.localdate(),
            defaults={"weight_kg": Decimal("82.5")},
        )
        plano, _ = services.sync_active_plan(self.pessoa)
        return plano

    def test_a_descricao_que_a_pessoa_escreveu_aparece_no_cartao(self):
        plano = self._preparar()
        slot = plano.slots.first()
        tracking.log_meal(self.pessoa, slot, MealStatus.OFF_PLAN,
                          notes="Feijoada do vizinho")

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn("Feijoada do vizinho", html)

    def test_registro_antigo_sem_descricao_cai_no_rotulo_generico(self):
        """CONTROLE: `notes` vazio existe no banco de quem usou a versão de
        antes, e para ele o rótulo genérico continua sendo a resposta certa."""
        plano = self._preparar()
        slot = plano.slots.first()
        tracking.log_meal(self.pessoa, slot, MealStatus.OFF_PLAN, notes="")

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn("Comeu outra coisa", html)
