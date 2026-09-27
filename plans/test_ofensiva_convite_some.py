"""A ofensiva em zero não pede o que a pessoa acabou de fazer.

QA exploratório de 27/09/2026 (`achados/qa-exploratorio-20260927.md`, R2).
Duas personas, o mesmo defeito. A de academia registrou uma refeição e a de
casa bebeu 750 ml, e a Home continuou dizendo "0 dias · Comece hoje:
registre uma refeição ou um copo d'água" — o convite pedia exatamente o que
tinha acabado de ser feito.

A regra: **o convite sai na mesma resposta em que a ação é registrada.**
Com registro hoje e o dia ainda aberto, a frase diz o que FECHA o dia
(`falta_hoje`, a mesma lista da sequência em risco). O convite de zero
continua para quem não registrou nada hoje, e o verbo ("Comece" ou
"Recomeça") segue a idade da conta, como na decisão de 24/09.
"""
import html
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from plans import services
from plans.models import MealLog, MealStatus
from plans.tests import create_complete_user

CONVITE = "registre uma refeição ou um copo d'água"


def _frase(pagina):
    achado = re.search(r'class="ofensiva__texto">(.*?)</span>', pagina, re.S)
    assert achado, "a Home não desenhou a ofensiva"
    return " ".join(html.unescape(achado.group(1)).split())


class OConviteSaiQuandoAAcaoAconteceTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="convite@exemplo.com")
        self.user.date_joined = timezone.now() - timedelta(hours=6)
        self.user.save(update_fields=["date_joined"])
        self.client.force_login(self.user)
        services.sync_active_plan(self.user)

    def _home(self):
        return _frase(self.client.get(reverse("plans:today")).content.decode())

    def test_sem_registro_hoje_o_convite_aparece(self):
        """Controle positivo: é esta a frase que o defeito repetia."""
        self.assertIn(CONVITE, self._home())
        self.assertTrue(self._home().startswith("Comece hoje"))

    def test_o_copo_tira_o_convite_na_mesma_resposta(self):
        resposta = self.client.post(
            reverse("plans:log_hydration"), {"ml": "250", "de": "topo"}, follow=True
        )
        self.assertEqual(resposta.request["PATH_INFO"], reverse("plans:today"))
        frase = _frase(resposta.content.decode())
        self.assertNotIn(CONVITE, frase)
        self.assertIn("Falta", frase)

    def test_a_refeicao_tira_o_convite(self):
        """O catálogo não é semeado na suíte, então o registro entra direto:
        a regra é de ESTADO — com refeição marcada hoje, não há convite."""
        slot = services.get_active_plan(self.user).slots.order_by("time").first()
        MealLog.objects.create(user=self.user, slot=slot, date=timezone.localdate(),
                               status=MealStatus.DONE, kcal=Decimal("400"))
        frase = self._home()
        self.assertNotIn(CONVITE, frase)
        self.assertIn("Falta", frase)

    def test_comi_outra_coisa_tambem_e_registro(self):
        slot = services.get_active_plan(self.user).slots.order_by("time").first()
        MealLog.objects.create(user=self.user, slot=slot, date=timezone.localdate(),
                               status=MealStatus.OFF_PLAN, kcal=Decimal("300"))
        self.assertNotIn(CONVITE, self._home())

    def test_quem_ja_tinha_conta_ontem_tambem(self):
        self.user.date_joined = timezone.now() - timedelta(days=10)
        self.user.save(update_fields=["date_joined"])
        self.assertTrue(self._home().startswith("Recomeça hoje"))
        self.client.post(reverse("plans:log_hydration"), {"ml": "250", "de": "topo"})
        self.assertNotIn(CONVITE, self._home())
