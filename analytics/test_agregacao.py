"""Bloco 1 — retenção e agregados.

Dois comandos, uma tensão: o bruto é caro e some em 90 dias; o agregado é
barato, não guarda ninguém e fica. O painel lê agregado para períodos longos.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import DailyAggregate, Event

User = get_user_model()


class AgregacaoTests(TestCase):
    def setUp(self):
        self.dia = timezone.now().replace(hour=12, minute=0)

    def _evento(self, nome, quando=None, **props_e_ids):
        campos = {"user": None, "anon_id": ""}
        for k in ("user", "anon_id"):
            if k in props_e_ids:
                campos[k] = props_e_ids.pop(k)
        return Event.objects.create(
            name=nome, ts=quando or self.dia, props=props_e_ids, **campos
        )

    def test_agrega_total_e_por_propriedade_com_pessoas_distintas(self):
        """O agregado do dia guarda a contagem total e a contagem por valor de
        propriedade, mais quantas PESSOAS distintas — a base do 'ativos'."""
        self._evento("dieta.refeicao_registrada", anon_id="a", opcao="almoço")
        self._evento("dieta.refeicao_registrada", anon_id="a", opcao="almoço")
        self._evento("dieta.refeicao_registrada", anon_id="b", opcao="janta")

        call_command("agregar_analytics", dia=self.dia.date().isoformat())

        total = DailyAggregate.objects.get(name="dieta.refeicao_registrada", prop_key="")
        self.assertEqual(total.count, 3)
        self.assertEqual(total.users, 2)  # a e b
        almoco = DailyAggregate.objects.get(prop_key="opcao", prop_value="almoço")
        self.assertEqual(almoco.count, 2)
        self.assertEqual(almoco.users, 1)  # só 'a'
        janta = DailyAggregate.objects.get(prop_key="opcao", prop_value="janta")
        self.assertEqual(janta.count, 1)

    def test_pessoa_conta_uma_vez_seja_por_user_ou_por_anon(self):
        u = User.objects.create_user(email="p@b.com", password="senha-bem-forte-123")
        self._evento("agua.registrada", user=u)
        self._evento("agua.registrada", user=u)
        call_command("agregar_analytics", dia=self.dia.date().isoformat())
        self.assertEqual(DailyAggregate.objects.get(name="agua.registrada").users, 1)

    def test_reagregar_o_mesmo_dia_nao_duplica(self):
        """Idempotente: rodar de novo recomputa, não soma."""
        self._evento("agua.registrada", anon_id="a")
        call_command("agregar_analytics", dia=self.dia.date().isoformat())
        call_command("agregar_analytics", dia=self.dia.date().isoformat())
        self.assertEqual(DailyAggregate.objects.get(name="agua.registrada").count, 1)


class PodaTests(TestCase):
    def test_poda_apaga_bruto_com_mais_de_90_dias_e_preserva_agregado(self):
        agora = timezone.now()
        velho = Event.objects.create(name="tela.vista", ts=agora - timedelta(days=91))
        novo = Event.objects.create(name="tela.vista", ts=agora - timedelta(days=5))
        DailyAggregate.objects.create(
            day=(agora - timedelta(days=91)).date(), name="tela.vista", count=100
        )

        call_command("podar_analytics")

        self.assertFalse(Event.objects.filter(pk=velho.pk).exists())
        self.assertTrue(Event.objects.filter(pk=novo.pk).exists())
        self.assertEqual(DailyAggregate.objects.count(), 1)  # agregado antigo fica

    def test_poda_e_idempotente(self):
        Event.objects.create(name="tela.vista", ts=timezone.now())
        call_command("podar_analytics")
        call_command("podar_analytics")
        self.assertEqual(Event.objects.count(), 1)
