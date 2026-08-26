"""Média semanal de peso, e a hora de recalibrar a dieta.

O peso do dia mente. Ele oscila com sal, com carboidrato do dia anterior, com
o intestino, com a hora da pesagem, com o ciclo menstrual — variações de um a
dois quilos que não são gordura e desaparecem sozinhas. Quem se pesa todo dia
e olha o número do dia desiste na primeira quinta-feira em que a balança sobe.

O que informa é a média da semana comparada com a da semana anterior. É por
isso que o módulo inteiro existe: transformar sete números ruidosos em um
número que significa alguma coisa.

E é por isso que a estagnação precisa de três semanas para ser declarada. Duas
semanas iguais acontecem por acaso o tempo todo; mexer na dieta a cada
oscilação é como ajustar o volante a cada buraco da estrada.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

#: Quanto a média precisa mudar, em quilos, para ser considerada movimento.
#:
#: Cento e cinquenta gramas por semana é menos que o erro de uma balança
#: doméstica e menos que a variação normal de hidratação. Abaixo disso a
#: pessoa não está perdendo devagar — ela está parada, e o número só parece
#: mudar porque o ruído não sumiu de todo.
LIMIAR_KG = Decimal("0.15")

#: Semanas paradas para o app sugerir mudança. Três é o mínimo defensável:
#: com duas, metade dos avisos seriam falso alarme de retenção de água.
SEMANAS_PARA_RECALIBRAR = 3

#: O ajuste sugerido quando a média empaca. Cento e cinquenta calorias é o
#: menor corte que produz efeito mensurável em uma ou duas semanas sem tornar
#: a dieta insustentável — cortes de 300 ou 500 numa dieta que já está em
#: déficit levam à fome e ao abandono.
AJUSTE_KCAL = 150

#: Quantas semanas mostrar no gráfico.
SEMANAS_NO_HISTORICO = 8


@dataclass(frozen=True)
class Semana:
    """Uma semana fechada de pesagens."""

    inicio: object
    media: Decimal
    registros: int
    #: Diferença para a semana anterior. `None` na primeira semana.
    delta: object


@dataclass(frozen=True)
class Tendencia:
    """O que o histórico de peso está dizendo."""

    semanas: list
    #: Diferença entre a última média e a anterior, em kg.
    variacao_semanal: object
    #: Quantas semanas seguidas sem movimento relevante.
    semanas_paradas: int
    #: O app deve sugerir recalibragem?
    sugerir_recalibragem: bool
    #: Quantas pesagens faltam para a leitura ser confiável.
    faltam_registros: int

    @property
    def tem_dados(self) -> bool:
        return bool(self.semanas)

    @property
    def direcao(self) -> str:
        """"perdendo", "ganhando", "estável" ou "" — para a tela escolher a cor."""
        if self.variacao_semanal is None:
            return ""
        if self.variacao_semanal <= -LIMIAR_KG:
            return "perdendo"
        if self.variacao_semanal >= LIMIAR_KG:
            return "ganhando"
        return "estável"


def _inicio_da_semana(data):
    """A segunda-feira daquela semana.

    Semana fixa e não janela móvel: assim a média de uma semana não muda
    quando a pessoa registra o peso de ontem hoje, e duas telas abertas em
    horas diferentes mostram o mesmo número.
    """
    return data - timedelta(days=data.weekday())


def semanas_de(entries, limite=SEMANAS_NO_HISTORICO) -> list:
    """Agrupa as pesagens em semanas, da mais antiga para a mais recente."""
    por_semana = {}
    for entry in entries:
        por_semana.setdefault(_inicio_da_semana(entry.date), []).append(entry.weight_kg)

    ordenadas = sorted(por_semana.items())[-limite:]

    semanas = []
    anterior = None
    for inicio, pesos in ordenadas:
        media = (sum(pesos) / len(pesos)).quantize(Decimal("0.01"))
        semanas.append(
            Semana(
                inicio=inicio,
                media=media,
                registros=len(pesos),
                delta=None if anterior is None else (media - anterior).quantize(Decimal("0.01")),
            )
        )
        anterior = media
    return semanas


def analisar(user) -> Tendencia:
    """Lê o histórico de peso e devolve o que ele está dizendo."""
    entries = list(user.weight_entries.all())
    semanas = semanas_de(entries)

    if len(semanas) < 2:
        # Com uma semana só não há do que comparar. Dizer quantas pesagens
        # faltam é mais útil que um gráfico vazio.
        registros = sum(s.registros for s in semanas)
        return Tendencia(
            semanas=semanas,
            variacao_semanal=None,
            semanas_paradas=0,
            sugerir_recalibragem=False,
            faltam_registros=max(0, 2 - registros),
        )

    variacao = semanas[-1].delta

    # Conta de trás para frente enquanto a média não se mexeu.
    paradas = 0
    for semana in reversed(semanas):
        if semana.delta is None or abs(semana.delta) >= LIMIAR_KG:
            break
        paradas += 1

    return Tendencia(
        semanas=semanas,
        variacao_semanal=variacao,
        semanas_paradas=paradas,
        sugerir_recalibragem=paradas >= SEMANAS_PARA_RECALIBRAR,
        faltam_registros=0,
    )


def hidratacao_ml(weight_kg) -> int:
    """Meta diária de água, em mililitros.

    Trinta e cinco mililitros por quilo é a recomendação usual para adulto
    ativo. Para 102 kg dá 3,6 L — dentro da faixa de 3,5 a 4 L que se espera
    de alguém desse porte treinando cinco vezes por semana.

    Arredondado para o meio litro mais próximo porque ninguém mede 3.570 ml:
    a pessoa enche uma garrafa, e a meta precisa caber em garrafas.
    """
    ml = Decimal(weight_kg) * 35
    return int((ml / 500).quantize(Decimal("1")) * 500)
