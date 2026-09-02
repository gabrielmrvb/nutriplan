"""As telas da corrida.

O que elas NÃO prometem está em `docs/running-analise.md` e aparece na
interface: uma PWA não tem geolocalização em segundo plano, então a corrida é
registrada enquanto o app está aberto, com a tela acesa por Wake Lock. Dizer
"pode guardar o telefone" seria mentir.

O cálculo mora no NAVEGADOR e não aqui. Não é otimização: as leituras de GPS
são o dado mais sensível do app, e mandá-las para o servidor para ele somar
seria transportar o traçado inteiro por rede e por log de acesso para obter um
número que o aparelho já tem. O que sobe é o resultado.
"""
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import ListView

from .models import Corrida

#: Uma corrida de doze horas é erro de quem esqueceu de encerrar, não um
#: ultramaratonista — e mesmo que fosse, o registro dela não é confiável numa
#: PWA que precisa da tela acesa.
DURACAO_MAXIMA_S = 12 * 60 * 60

#: 300 km. O limite existe para recusar payload absurdo, e não para julgar
#: distância: quem manda 40.000 km errou o cálculo ou está forjando.
DISTANCIA_MAXIMA_M = 300_000


class HistoricoDeCorridasView(LoginRequiredMixin, ListView):
    model = Corrida
    template_name = "workouts/corridas.html"
    context_object_name = "corridas"
    paginate_by = 20

    def get_queryset(self):
        return Corrida.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["nav"] = "workout"
        return contexto


class SalvarCorridaView(LoginRequiredMixin, View):
    """Recebe o RESULTADO de uma corrida, nunca o traçado.

    Idempotente por `op_id`: a fila offline reenvia o que ficou parado, e sem
    chave o reenvio criaria uma segunda corrida idêntica. O segundo envio
    devolve a corrida que já existe, com 200 — devolver erro faria a fila
    tentar de novo para sempre.
    """

    def post(self, request, *args, **kwargs):
        try:
            dados = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "corpo inválido"}, status=400)

        problema = self._conferir(dados)
        if problema:
            return JsonResponse({"erro": problema}, status=400)

        try:
            with transaction.atomic():
                corrida = Corrida.objects.create(
                    user=request.user,
                    op_id=dados["op_id"],
                    comecou_em=parse_datetime(dados["comecou_em"]),
                    terminou_em=parse_datetime(dados["terminou_em"]),
                    distancia_m=int(dados["distancia_m"]),
                    duracao_s=int(dados["duracao_s"]),
                    teve_lacuna=bool(dados.get("teve_lacuna")),
                    parciais=dados.get("parciais") or [],
                )
        except IntegrityError:
            # Reenvio da fila. A corrida já está gravada, e é essa que
            # responde: criar outra duplicaria, e recusar faria a fila insistir.
            corrida = Corrida.objects.get(user=request.user, op_id=dados["op_id"])

        return JsonResponse(
            {"id": corrida.pk, "distancia_m": corrida.distancia_m}, status=200
        )

    @staticmethod
    def _conferir(dados):
        """O que o servidor recusa, e por quê.

        O cálculo vem do navegador, então o servidor não pode conferir a
        distância — ele não tem as leituras. O que ele PODE é recusar o
        impossível, e é só isso que ele faz: aceitar qualquer número deixaria
        um POST forjado inventar uma maratona.
        """
        for campo in ("op_id", "comecou_em", "terminou_em", "distancia_m", "duracao_s"):
            if dados.get(campo) in (None, ""):
                return f"falta {campo}"

        try:
            distancia = int(dados["distancia_m"])
            duracao = int(dados["duracao_s"])
        except (TypeError, ValueError):
            return "distância e duração precisam ser números"

        if distancia < 0 or duracao < 0:
            return "distância e duração não podem ser negativas"
        if distancia > DISTANCIA_MAXIMA_M:
            return "distância acima do que o app registra"
        if duracao > DURACAO_MAXIMA_S:
            return "duração acima do que o app registra"

        comecou = parse_datetime(dados["comecou_em"])
        terminou = parse_datetime(dados["terminou_em"])
        if comecou is None or terminou is None:
            return "datas inválidas"
        if terminou < comecou:
            return "a corrida terminou antes de começar"
        # O tempo EM MOVIMENTO nunca pode passar do tempo de relógio: se passar,
        # o aparelho contou errado ou alguém forjou. A folga de um minuto é
        # para arredondamento entre o relógio do aparelho e o do servidor.
        if duracao > (terminou - comecou).total_seconds() + 60:
            return "tempo em movimento maior que o tempo total"

        if len(str(dados["op_id"])) > 64:
            return "identificador longo demais"
        return None
