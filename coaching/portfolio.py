"""A carteira de alunos e os alertas que a fazem valer a pena abrir.

Uma lista de nomes não é um painel. O que faz o profissional abrir esta tela às
sete da manhã é ela responder, sem clique nenhum, *de quem eu preciso cuidar
hoje* — e isso é o que os alertas fazem.

Sobre consultas: a tela mostra a carteira inteira de uma vez, então tudo aqui é
resolvido em consultas agregadas sobre todos os alunos ao mesmo tempo. A versão
ingênua (um `analisar(aluno)` dentro do laço) custa cinco consultas por aluno, e
uma carteira de trinta alunos vira cento e cinquenta idas ao banco para desenhar
uma lista.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone

from accounts.models import WeightEntry
from plans import weight_trend
from plans.models import MealLog, MealStatus
from workouts.models import ExerciseLog, TrainingPlan

#: Além disso, a leitura de peso da semana já não existe: a média semanal
#: precisa de pesagem *na* semana, e sete dias sem subir na balança é o começo
#: do sumiço, não um atraso.
DIAS_SEM_PESAGEM = 7

#: Duas semanas de média parada ainda podem ser ruído; três é o limiar em que o
#: próprio app sugere recalibrar ao aluno. O painel avisa em duas porque o
#: profissional age antes do automático — é para isso que ele está ali.
SEMANAS_PARADAS_ALERTA = 2

#: Aderência abaixo disso nos últimos sete dias é o aluno comendo fora do plano
#: na maior parte dos dias.
ADESAO_BAIXA_PCT = 60


@dataclass
class Alerta:
    slug: str
    icone: str
    texto: str
    #: "atencao" pinta âmbar, "bom" pinta verde. Só isso — um painel com cinco
    #: cores de severidade vira semáforo que ninguém lê.
    tom: str = "atencao"


@dataclass
class Aluno:
    """Uma linha da carteira, com tudo que a linha precisa mostrar."""

    link: object
    user: object
    iniciais: str
    ultima_pesagem: object = None
    dias_sem_pesagem: object = None
    semanas_paradas: int = 0
    variacao_semanal: object = None
    treinos_feitos: int = 0
    treinos_previstos: int = 0
    adesao_pct: object = None
    alertas: list = field(default_factory=list)

    @property
    def precisa_atencao(self) -> bool:
        return any(a.tom == "atencao" for a in self.alertas)

    @property
    def sem_treino(self) -> bool:
        return self.treinos_previstos > 0 and self.treinos_feitos == 0

    @property
    def treino_completo(self) -> bool:
        return self.treinos_previstos > 0 and self.treinos_feitos >= self.treinos_previstos

    @property
    def situacao(self) -> str:
        """A chave do filtro. Um aluno cai em exatamente uma gaveta."""
        if self.precisa_atencao:
            return "atencao"
        if self.sem_treino:
            return "sem_treino"
        return "em_dia"


#: Os filtros da tela, na ordem em que aparecem.
FILTROS = (
    ("todos", "Todos"),
    ("atencao", "Atenção necessária"),
    ("em_dia", "Em dia"),
    ("sem_treino", "Sem treino registrado"),
)


def _iniciais(user) -> str:
    """Duas letras para o avatar. Nome quando existe, e-mail quando não."""
    partes = [p for p in (user.first_name, user.last_name) if p]
    if partes:
        return "".join(p[0] for p in partes[:2]).upper()
    return (user.email or "?")[:2].upper()


def _inicio_da_semana(dia):
    return dia - timedelta(days=dia.weekday())


def montar(links, hoje=None) -> list:
    """Transforma os vínculos ativos em linhas prontas de carteira."""
    links = list(links)
    if not links:
        return []

    hoje = hoje or timezone.localdate()
    inicio_semana = _inicio_da_semana(hoje)
    ids = [link.student_id for link in links]

    # ------------------------------------------------------------ peso
    pesagens = {}
    for entry in WeightEntry.objects.filter(user_id__in=ids).order_by("user_id", "date"):
        pesagens.setdefault(entry.user_id, []).append(entry)

    ultima = {
        row["user_id"]: row["ultima"]
        for row in WeightEntry.objects.filter(user_id__in=ids)
        .values("user_id")
        .annotate(ultima=Max("date"))
    }

    # ---------------------------------------------------------- treino
    previstos = {
        plan.user_id: plan.days_per_week
        for plan in TrainingPlan.objects.filter(user_id__in=ids, is_active=True)
    }
    # Um dia com qualquer carga anotada conta como treino feito. Não existe
    # botão de "concluir treino" no app — o registro de carga É o registro de
    # presença, e inventar um segundo gesto só para o painel seria pedir ao
    # aluno que trabalhe para o painel.
    feitos = {
        row["user_id"]: row["dias"]
        for row in ExerciseLog.objects.filter(user_id__in=ids, date__gte=inicio_semana)
        .values("user_id")
        .annotate(dias=Count("date", distinct=True))
    }

    # -------------------------------------------------------- aderência
    desde = hoje - timedelta(days=6)
    marcadas, cumpridas = {}, {}
    for row in (
        MealLog.objects.filter(user_id__in=ids, date__gte=desde)
        .exclude(status=MealStatus.PENDING)
        .values("user_id", "status")
        .annotate(total=Count("pk"))
    ):
        marcadas[row["user_id"]] = marcadas.get(row["user_id"], 0) + row["total"]
        if row["status"] == MealStatus.DONE:
            cumpridas[row["user_id"]] = cumpridas.get(row["user_id"], 0) + row["total"]

    alunos = []
    for link in links:
        uid = link.student_id
        semanas = weight_trend.semanas_de(pesagens.get(uid, []))
        paradas = _semanas_paradas(semanas)
        marcada = marcadas.get(uid, 0)

        aluno = Aluno(
            link=link,
            user=link.student,
            iniciais=_iniciais(link.student),
            ultima_pesagem=ultima.get(uid),
            dias_sem_pesagem=(hoje - ultima[uid]).days if uid in ultima else None,
            semanas_paradas=paradas,
            variacao_semanal=semanas[-1].delta if semanas else None,
            treinos_feitos=feitos.get(uid, 0),
            treinos_previstos=previstos.get(uid, 0),
            adesao_pct=int(cumpridas.get(uid, 0) * 100 / marcada) if marcada else None,
        )
        aluno.alertas = _alertas(aluno)
        alunos.append(aluno)

    # Quem precisa de atenção sobe. Numa carteira grande, a ordem alfabética
    # esconde o aluno em risco na letra T.
    alunos.sort(key=lambda a: (not a.precisa_atencao, a.user.first_name or a.user.email))
    return alunos


def _semanas_paradas(semanas) -> int:
    paradas = 0
    for semana in reversed(semanas):
        if semana.delta is None or abs(semana.delta) >= weight_trend.LIMIAR_KG:
            break
        paradas += 1
    return paradas


def _alertas(aluno) -> list:
    alertas = []

    if aluno.dias_sem_pesagem is None:
        alertas.append(
            Alerta("sem_peso", "balanca", "Nunca registrou peso")
        )
    elif aluno.dias_sem_pesagem > DIAS_SEM_PESAGEM:
        alertas.append(
            Alerta(
                "sem_peso",
                "balanca",
                f"Sem pesagem há {aluno.dias_sem_pesagem} dias",
            )
        )

    if aluno.semanas_paradas >= SEMANAS_PARADAS_ALERTA:
        alertas.append(
            Alerta(
                "estagnado",
                "grafico",
                f"Média parada há {aluno.semanas_paradas} semanas",
            )
        )

    if aluno.adesao_pct is not None and aluno.adesao_pct < ADESAO_BAIXA_PCT:
        alertas.append(
            Alerta("adesao", "prato", f"Aderência de {aluno.adesao_pct}% na semana")
        )

    if aluno.treino_completo:
        alertas.append(
            Alerta(
                "treino_ok",
                "halter",
                f"Fechou os {aluno.treinos_previstos} treinos da semana",
                tom="bom",
            )
        )

    return alertas


def filtrar(alunos, situacao) -> list:
    if situacao in (None, "", "todos"):
        return alunos
    return [aluno for aluno in alunos if aluno.situacao == situacao]


def contagem(alunos) -> dict:
    """Quantos alunos em cada gaveta."""
    total = {chave: 0 for chave, _ in FILTROS}
    total["todos"] = len(alunos)
    for aluno in alunos:
        total[aluno.situacao] += 1
    return total


def filtros_de(alunos, situacao) -> list:
    """Os filtros já com o número no rótulo, prontos para a tela.

    O número no próprio botão é o que faz o filtro valer: sem ele o
    profissional clica em cada gaveta para descobrir se tem alguém dentro, e
    "Atenção necessária (0)" é a informação mais útil da tela num dia bom.
    """
    total = contagem(alunos)
    return [
        {
            "chave": chave,
            "rotulo": rotulo,
            "total": total[chave],
            "ativo": chave == situacao,
        }
        for chave, rotulo in FILTROS
    ]
