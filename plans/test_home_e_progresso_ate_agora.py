"""Home e Progresso contam as refeições de hoje do mesmo jeito: até agora.

Decisão do dono de 27/09/2026. O PR #170 fez o Progresso mostrar, no
primeiro dia, "1/1 · hoje, até agora", recortado pelo relógio
(`tracking.history`, regra de 22/09). A Home continuou dividindo pelo dia
inteiro ("1/5 refeições"). Na mesma hora, as duas telas davam dois números
para a mesma pergunta. Agora a Home e o topo da Alimentação leem
`summary.ate_agora`, que usa a MESMA conta de `tracking.history`
(`teto_de_hoje`).

"O seu dia em 5 refeições", na Alimentação, continua usando `previstas`: ali
a frase fala da estrutura do plano, não do progresso do dia.
"""
import re
from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from config import relogio
from plans import services
from plans.models import MealLog, MealStatus
from plans.test_numeros_do_progresso import _caixa
from plans.tests import create_complete_user

HOME = re.compile(r"(\d+)/(\d+) até agora")


class AsDuasTelasDizemOMesmoNumeroTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="ate-agora@exemplo.com")
        self.client.force_login(self.user)

    def _no_meio_do_dia(self):
        """Uma hora em que umas refeições já passaram e outras não."""
        services.sync_active_plan(self.user)
        horarios = sorted(services.get_active_plan(self.user).slots.values_list("time", flat=True))
        meio = horarios[len(horarios) // 2]
        dia = timezone.localdate()
        instante = timezone.make_aware(datetime.combine(dia, meio) + timedelta(minutes=5))
        return instante, horarios

    def test_home_e_progresso_no_mesmo_instante(self):
        instante, horarios = self._no_meio_do_dia()
        with relogio.congelado_em(instante):
            self.user.date_joined = timezone.now() - timedelta(hours=10)
            self.user.save(update_fields=["date_joined"])
            slot = services.get_active_plan(self.user).slots.order_by("time").first()
            MealLog.objects.create(user=self.user, slot=slot, date=timezone.localdate(),
                                   status=MealStatus.DONE, kcal=Decimal("400"))
            home = self.client.get(reverse("plans:today")).content.decode()
            progresso = _caixa(self.client.get(reverse("plans:history")).content.decode())

        casou = HOME.search(home)
        self.assertIsNotNone(casou, "a Home não diz 'N/M até agora'")
        self.assertEqual("%s/%s" % casou.groups(), progresso["dieta"]["valor"])
        # E o número é o recorte, não o dia inteiro.
        self.assertLess(int(casou.group(2)), len(horarios))
