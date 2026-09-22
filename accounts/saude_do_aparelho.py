# -*- coding: utf-8 -*-
"""As pesagens que o app INSTALADO leu do Apple Saúde / Health Connect
(Fase 2 da missão Capacitor, 22/09/2026).

A leitura é do aparelho (`capacitor-health`, em `static/js/nativo.js`); o
servidor só recebe o que a pessoa mandou importar. Uma pesagem por dia, e a
do aparelho NUNCA sobrescreve a que a pessoa digitou (`get_or_create` por
dia): a balança do app é a palavra final. A faixa é a mesma do formulário
de pesagem (20 a 400 kg), e data futura é recusada — relógio adiantado
escreveria num dia que ainda não existe.
"""
import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View

from .models import WeightEntry
from .views import OnboardingRequiredMixin

PESO_MINIMO = Decimal("20")
PESO_MAXIMO = Decimal("400")


class PesoDoAparelhoView(OnboardingRequiredMixin, View):
    def post(self, request):
        try:
            dados = json.loads(request.body or "{}")
            pesagens = dados["pesagens"]
            assert isinstance(pesagens, list)
        except (ValueError, KeyError, AssertionError):
            return JsonResponse({"error": "corpo inválido"}, status=400)

        hoje = timezone.localdate()
        gravadas = ja_tinha = recusadas = 0
        for item in pesagens[:400]:
            try:
                data = parse_date(str(item["data"]))
                peso = Decimal(str(item["peso_kg"])).quantize(Decimal("0.1"))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                recusadas += 1
                continue
            if data is None or data > hoje or not (PESO_MINIMO <= peso <= PESO_MAXIMO):
                recusadas += 1
                continue
            _, criada = WeightEntry.objects.get_or_create(user=request.user, date=data, defaults={"weight_kg": peso})
            if criada:
                gravadas += 1
            else:
                ja_tinha += 1
        return JsonResponse({"gravadas": gravadas, "ja_tinha": ja_tinha, "recusadas": recusadas})
