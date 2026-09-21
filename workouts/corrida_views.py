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
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import ListView

from accounts.views import OnboardingRequiredMixin

from . import doutrina_corrida
from .importar_corrida import ArquivoDeCorridaInvalido, corrida_de_arquivo
from .models import Corrida, PlanoDeCorrida
from .templatetags.corrida import relogio as _relogio

#: 5 MB. Um GPX de duas horas a uma leitura por segundo tem ~7.200 pontos e
#: fica bem abaixo disso; o teto existe para recusar upload absurdo antes de o
#: parser tocar no arquivo — não para julgar corrida longa.
TAMANHO_MAXIMO_ARQUIVO = 5 * 1024 * 1024

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
        # Corrida não é subfunção de treino — `Pilar` diz isso com todas as
        # letras, e com `workout` aqui a aba "Treino" acendia na tela de
        # corridas. Quem marca a área agora é o mapa da barra de cima.
        contexto["nav"] = "running"
        # TELA CRÍTICA: a corrida roda aqui, com o cronômetro na tela e o
        # aparelho no bolso. Um cartão fixo pedindo para instalar o app no meio
        # disso é interrupção, não convite. Ver `data-sem-convite` no
        # `base.html`.
        contexto["sem_convite"] = True

        # O CARTÃO DO PLANO. `plano` é o ativo ou `None` — o template decide
        # entre o convite ("Quer um plano?") e o cartão da semana sozinho,
        # sem `if/elif` duplicado aqui.
        hoje = timezone.localdate()
        plano = PlanoDeCorrida.objects.filter(user=self.request.user, ativo=True).first()
        contexto["plano"] = plano
        contexto["semana"] = plano.semana_atual(hoje) if plano else None
        sessoes = []
        if plano is not None and contexto["semana"] is not None:
            feitas = plano.sessoes_feitas(hoje)
            for linha in doutrina_corrida.sessoes(plano.plano, plano.nivel, contexto["semana"]):
                sessoes.append({**linha, "feita": linha["sessao"] <= feitas})
        contexto["sessoes"] = sessoes
        return contexto


#: Abaixo disto não é corrida, é o GPS tremendo parado.
DISTANCIA_MINIMA_M = 50

#: 12,5 m/s = 2:40/km — mais rápido que o recorde mundial dos 100 metros.
#: Folgada de propósito: ela existe para recusar o impossível, não para
#: julgar quem corre bem.
VELOCIDADE_MAXIMA_MS = 12.5

#: Uma parcial por quilômetro, com folga sobre o teto de distância.
PARCIAIS_MAXIMAS = 500


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

        # AS TRÊS RECUSAS ABAIXO SAÍRAM DE UMA AUDITORIA, e as três passavam
        # antes porque a conferência olhava cada número sozinho.
        #
        # 1. DISTÂNCIA ZERO virava corrida de 0 m no histórico. A tela não
        #    produz isso — é preciso andar para o GPS somar —, mas um reenvio
        #    torto ou um POST forjado produzia, e a lista ficava com uma linha
        #    que não quer dizer nada.
        if distancia < DISTANCIA_MINIMA_M:
            return "distância curta demais para virar corrida"

        # 2. A RAZÃO ENTRE OS DOIS não era conferida. Distância 100.000 passava
        #    (está abaixo do teto) e duração 1.000 s também — juntas, 100 km em
        #    dezesseis minutos, pace de 0:36/km. O docstring diz que a
        #    conferência existe para um POST forjado não "inventar uma
        #    maratona"; ele inventava, só que rápida. VELOCIDADE_MAXIMA_MS é
        #    folgada de propósito: 12,5 m/s é 2:40/km, mais rápido que o
        #    recorde mundial dos 100 m, então nenhuma corrida real esbarra.
        #    O `duracao > 0` que existia aqui era para evitar divisão por zero,
        #    e DESLIGAVA a regra inteira justamente no caso mais extremo:
        #    `distancia_m=299999, duracao_s=0` era aceito com 200, porque a
        #    duração zero também satisfaz "tempo em movimento menor que o
        #    relógio". Trezentos quilômetros em zero segundo — o impossível que
        #    esta guarda foi escrita para recusar, entrando pela porta que ela
        #    abriu. Achado em revisão adversarial da própria correção.
        if duracao <= 0:
            return "velocidade acima do que uma corrida alcança"
        if distancia / duracao > VELOCIDADE_MAXIMA_MS:
            return "velocidade acima do que uma corrida alcança"

        # 3. PARCIAIS SEM TETO. O campo é JSON livre e ia inteiro para o banco:
        #    um POST forjado com cinco mil parciais era aceito. O teto é o
        #    número de quilômetros que o app registra, com folga.
        parciais = dados.get("parciais") or []
        if not isinstance(parciais, list):
            return "parciais precisam ser uma lista"
        if len(parciais) > PARCIAIS_MAXIMAS:
            return "parciais demais"
        return None


class CorridaNovaView(OnboardingRequiredMixin, View):
    """GET: formulário com `op_id` escondido; POST: cria. Duplo toque = uma corrida."""
    template_name = "workouts/corrida_form.html"

    def get(self, request):
        from .forms_corrida import CorridaManualForm
        form = CorridaManualForm(initial={"data": timezone.localdate()})
        return render(request, self.template_name, {"form": form, "op_id": uuid.uuid4().hex, "titulo": "Registrar corrida", "nav": "running"})

    def post(self, request):
        from .forms_corrida import CorridaManualForm
        form = CorridaManualForm(request.POST)
        op_id = (request.POST.get("op_id") or "")[:64]
        if not form.is_valid() or not op_id:
            return render(request, self.template_name, {"form": form, "op_id": op_id or uuid.uuid4().hex, "titulo": "Registrar corrida", "nav": "running"}, status=200)
        corrida = form.preencher(Corrida(user=request.user, op_id=op_id))
        try:
            with transaction.atomic():
                corrida.save()
        except IntegrityError:
            # I3 (avaliação de mercado, 17/09/2026): o `op_id` volta ESCONDIDO
            # no formulário, e o bfcache do navegador restaura a página (com
            # ele) quando a pessoa aperta Voltar — nada impede um SEGUNDO
            # envio, com dados DIFERENTES, sob o mesmo `op_id` (a pessoa volta,
            # corrige o campo e manda de novo sem notar que o identificador é
            # o de antes). Tratar todo `IntegrityError` como duplo toque
            # apagava esse segundo envio em silêncio — sucesso na tela, dado
            # perdido no banco.
            #
            # A distinção: MESMOS três números (distância, duração, início) é
            # o duplo toque de verdade — a MESMA corrida reenviada — e segue
            # respondendo sucesso, como sempre. Números DIFERENTES sob o
            # mesmo `op_id` é a colisão, e volta para o formulário com erro em
            # vez de fingir que gravou.
            existente = Corrida.objects.get(user=request.user, op_id=op_id)
            mesma_corrida = (
                existente.distancia_m == corrida.distancia_m
                and existente.duracao_s == corrida.duracao_s
                and existente.comecou_em == corrida.comecou_em
            )
            if not mesma_corrida:
                form.add_error(
                    None,
                    "Esse envio já foi usado por outra corrida — recarregue a página e registre de novo.",
                )
                return render(request, self.template_name, {"form": form, "op_id": op_id, "titulo": "Registrar corrida", "nav": "running"}, status=200)
        messages.success(request, "Corrida registrada.")
        return redirect("workouts:corridas")


class ImportarCorridaView(OnboardingRequiredMixin, View):
    """Importa uma corrida de um arquivo GPX ou TCX.

    O registro à mão continua sendo o caminho; esta é a segunda porta, para
    quem já corre com relógio ou outro app e exporta o percurso — traz o número
    pronto em vez de digitar. A view só ORQUESTRA: o parsing é puro
    (`importar_corrida`), os tetos são os MESMOS do GPS (as constantes deste
    módulo), e a corrida entra com `origem="arquivo"`, que não se edita pelo
    mesmo motivo do GPS. O traçado não é guardado — ver a docstring de
    `importar_corrida`. A Strava API fica de fora (precisa de app registrado e
    credencial que este ambiente não tem): a investigação está em
    `docs/running-analise.md`.
    """

    template_name = "workouts/corrida_importar.html"

    def get(self, request):
        return render(request, self.template_name, {"nav": "running"})

    def post(self, request):
        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            return self._erro(request, "Escolha um arquivo .gpx ou .tcx para importar.")
        # Teto de tamanho ANTES de ler: um upload absurdo não deve virar 5 MB
        # de string na memória só para ser recusado depois.
        if arquivo.size > TAMANHO_MAXIMO_ARQUIVO:
            return self._erro(request, "Arquivo grande demais — o limite é 5 MB.")
        try:
            # `utf-8-sig` tira o BOM que alguns aparelhos gravam no começo.
            conteudo = arquivo.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return self._erro(request, "Não consegui ler o arquivo como texto — ele não parece ser GPX/TCX.")

        try:
            dados = corrida_de_arquivo(conteudo, arquivo.name)
        except ArquivoDeCorridaInvalido as erro:
            return self._erro(request, str(erro))

        problema = self._conferir_negocio(dados)
        if problema:
            return self._erro(request, problema)

        try:
            with transaction.atomic():
                Corrida.objects.create(
                    user=request.user,
                    op_id=dados["op_id"],
                    comecou_em=dados["comecou_em"],
                    terminou_em=dados["terminou_em"],
                    distancia_m=dados["distancia_m"],
                    duracao_s=dados["duracao_s"],
                    parciais=dados["parciais"],
                    origem=Corrida.Origem.ARQUIVO,
                )
        except IntegrityError:
            # Reimportação do MESMO arquivo: o `op_id` é a impressão do
            # conteúdo, então o `UniqueConstraint(user, op_id)` recusa a
            # segunda cópia. Não é erro — a corrida já está lá; a pessoa só
            # arrastou o arquivo de novo. Dizer isso é melhor que "sucesso"
            # mudo (parece que gravou de novo) ou 500.
            messages.info(request, "Essa corrida já tinha sido importada.")
            return redirect("workouts:corridas")

        messages.success(request, "Corrida importada.")
        return redirect("workouts:corridas")

    def _erro(self, request, mensagem):
        return render(request, self.template_name, {"nav": "running", "erro": mensagem}, status=200)

    @staticmethod
    def _conferir_negocio(dados):
        """Os MESMOS tetos do GPS e do registro à mão — o arquivo não escapa
        deles. Uma conta de 0 m (aparelho parado) ou de velocidade impossível
        é recusada com a frase certa, em vez de virar linha morta no
        histórico. É a régua de `SalvarCorridaView._conferir` aplicada ao que
        o parser calculou."""
        distancia, duracao = dados["distancia_m"], dados["duracao_s"]
        if distancia < DISTANCIA_MINIMA_M:
            return "O arquivo não tem distância suficiente para virar corrida — o aparelho pode ter ficado parado."
        if distancia > DISTANCIA_MAXIMA_M:
            return "Distância acima do que o app registra."
        if duracao <= 0:
            return "O arquivo não tem tempo suficiente para virar corrida."
        if duracao > DURACAO_MAXIMA_S:
            return "Duração acima do que o app registra."
        if distancia / duracao > VELOCIDADE_MAXIMA_MS:
            return "A velocidade do arquivo é impossível para uma corrida — confira se é o arquivo certo."
        return None


class CorridaEditarView(OnboardingRequiredMixin, View):
    """Só a corrida à mão se edita: o traço do GPS contradiria os números."""
    template_name = "workouts/corrida_form.html"

    def _corrida(self, request, pk):
        return get_object_or_404(Corrida, pk=pk, user=request.user, origem=Corrida.Origem.MANUAL)

    def get(self, request, pk):
        from .forms_corrida import CorridaManualForm
        c = self._corrida(request, pk)
        form = CorridaManualForm(initial={"distancia_km": ("%.2f" % (c.distancia_m / 1000)).replace(".", ","), "tempo": _relogio(c.duracao_s), "data": timezone.localdate(c.comecou_em), "sensacao": c.sensacao})
        return render(request, self.template_name, {"form": form, "titulo": "Editar corrida", "corrida": c, "nav": "running"})

    def post(self, request, pk):
        from .forms_corrida import CorridaManualForm
        c = self._corrida(request, pk)
        form = CorridaManualForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "titulo": "Editar corrida", "corrida": c, "nav": "running"})
        form.preencher(c).save()
        messages.success(request, "Corrida atualizada.")
        return redirect("workouts:corridas")


class CorridaExcluirView(OnboardingRequiredMixin, View):
    """Exclusão em duas etapas, como `ExcluirContaView`: GET confirma, POST apaga.

    Vale para GPS e para manual — a edição é que é exclusiva da corrida à mão.
    """

    def get(self, request, pk):
        c = get_object_or_404(Corrida, pk=pk, user=request.user)
        return render(request, "workouts/corrida_excluir.html", {"corrida": c, "nav": "running"})

    def post(self, request, pk):
        get_object_or_404(Corrida, pk=pk, user=request.user).delete()
        messages.success(request, "Corrida excluída.")
        return redirect("workouts:corridas")


class PlanoDeCorridaView(OnboardingRequiredMixin, View):
    """Escolhe, troca ou encerra o plano de corrida ativo.

    GET lista as quatro combinações de `doutrina_corrida.planos()` — a
    doutrina é a fonte, a view não inventa opção. POST com `plano`+`nivel`
    desativa o ativo (se houver) e cria um novo começando hoje; POST com
    `encerrar=1` só desativa. As duas escritas ficam na mesma transação que
    `services.create_routine` usa para `TrainingPlan`: o índice único
    parcial não aceita dois ativos, nem por um instante entre o UPDATE e o
    INSERT.
    """

    template_name = "workouts/corrida_plano.html"

    def get(self, request):
        # `plano_display`/`nivel_display` vêm das MESMAS `choices` do modelo
        # (`PlanoDeCorrida.Plano`, `.Nivel`) — "10K" e "intermediário" com o
        # acento, sem reescrever o rótulo aqui e correr o risco de os dois
        # divergirem um dia.
        opcoes = [
            {
                "plano": plano,
                "nivel": nivel,
                "plano_display": PlanoDeCorrida.Plano(plano).label,
                "nivel_display": PlanoDeCorrida.Nivel(nivel).label,
                **dados,
            }
            for (plano, nivel), dados in doutrina_corrida.planos().items()
        ]
        ativo = PlanoDeCorrida.objects.filter(user=request.user, ativo=True).first()
        return render(request, self.template_name, {"opcoes": opcoes, "ativo": ativo, "nav": "running"})

    def post(self, request):
        if request.POST.get("encerrar"):
            PlanoDeCorrida.objects.filter(user=request.user, ativo=True).update(ativo=False)
            messages.success(request, "Plano de corrida encerrado.")
            return redirect("workouts:corridas")

        plano = request.POST.get("plano", "")
        nivel = request.POST.get("nivel", "")
        if (plano, nivel) not in doutrina_corrida.planos():
            messages.error(request, "Escolha um dos planos da lista.")
            return redirect("workouts:corrida_plano")

        with transaction.atomic():
            PlanoDeCorrida.objects.filter(user=request.user, ativo=True).update(ativo=False)
            PlanoDeCorrida.objects.create(
                user=request.user,
                plano=plano,
                nivel=nivel,
                comecou_em=timezone.localdate(),
                ativo=True,
            )
        messages.success(request, "Plano de corrida iniciado.")
        return redirect("workouts:corridas")
