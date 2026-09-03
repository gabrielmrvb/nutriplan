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

#: Quanto tempo o app fica quieto depois de a pessoa RESPONDER ao aviso.
#:
#: Duas semanas, e o número não é escolha nova: é o que as duas respostas já
#: prometem por escrito. Cortar responde "Dê duas semanas antes de julgar o
#: resultado"; recusar responde "perguntamos de novo daqui a algumas semanas".
#:
#: `Profile.recalibrated_at` já era gravado pelas duas ações e não era lido por
#: ninguém — `grep` não achava uma leitura sequer. Medido no navegador: dois
#: toques em "Cortar 150 kcal" no mesmo minuto levaram o ajuste para −300 kcal,
#: e o cartão continuou na tela, com o mesmo texto, convidando ao terceiro.
#: Uma sugestão que não some depois de respondida deixa de ser sugestão e vira
#: um botão que baixa a meta calórica sem teto.
#:
#: O que NÃO muda é `semanas_paradas`: a média continua parada e a tela pode
#: dizer isso. O que espera é o CONVITE a mexer na dieta de novo.
ESPERA_APOS_RECALIBRAR = timedelta(days=14)

#: Quantas semanas mostrar no gráfico.
SEMANAS_NO_HISTORICO = 8

#: Pesagens por semana que o painel convida a registrar.
#:
#: Duas, em dias diferentes, sem dias obrigatórios. Duas porque é o mínimo que
#: dá uma média com alguma resistência ao ruído do dia — e porque pedir mais
#: transforma acompanhamento em cobrança diária, que é o jeito mais rápido de
#: a pessoa parar de se pesar e o app perder a série inteira. Os dias saem
#: diferentes sem nenhuma regra a mais: a unicidade por (usuário, dia) já
#: impede duas pesagens no mesmo dia.
#:
#: Não confundir com `Tendencia.faltam_registros`. Aquele conta o total
#: acumulado enquanto o histórico tem menos de duas semanas e zera para sempre
#: depois; ele responde "a média já é confiável?". Esta constante responde
#: "vale convidar a pessoa a se pesar hoje?", e a resposta reinicia toda
#: segunda-feira.
PESAGENS_POR_SEMANA = 2


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


def respondeu_ha_pouco(user, agora=None) -> bool:
    """A pessoa já respondeu ao aviso dentro da janela de espera?

    Lê `Profile.recalibrated_at`, que as duas respostas gravam. `getattr` e não
    `user.profile` direto porque este módulo é folha e não deve explodir para
    quem ainda não tem perfil — quem chega aqui pela tela sempre tem, mas o
    módulo é importável de qualquer lugar.
    """
    perfil = getattr(user, "profile", None)
    quando = getattr(perfil, "recalibrated_at", None)
    if quando is None:
        return False
    return (agora or timezone.now()) - quando < ESPERA_APOS_RECALIBRAR


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
        # A média parada continua sendo relatada; o que espera duas semanas é
        # o convite a mexer na dieta outra vez.
        sugerir_recalibragem=(
            paradas >= SEMANAS_PARA_RECALIBRAR and not respondeu_ha_pouco(user)
        ),
        faltam_registros=0,
    )


def convidar_a_pesar(user, hoje=None) -> bool:
    """O painel deve convidar a registrar o peso agora?

    Duas condições, e as duas precisam valer: a semana ainda não chegou a
    `PESAGENS_POR_SEMANA`, e hoje ainda não tem pesagem. A segunda não é
    redundante — quem se pesou hoje pela primeira vez na semana continua
    abaixo do alvo, e sem ela o convite ficaria pedindo a segunda pesagem no
    mesmo dia, que é exatamente o que a unicidade por (usuário, dia) recusa.

    A semana é a mesma da média: segunda a domingo, por `_inicio_da_semana`.
    Duas definições de semana no mesmo assunto seria o app dizendo que a
    contagem virou enquanto a média ainda não.

    A consulta é dirigida à semana de propósito. `analisar()` carrega o
    histórico inteiro para calcular médias, e isto roda no painel, que é a
    tela mais aberta do app: são no máximo sete linhas, pelo índice que a
    unicidade já cria.
    """
    hoje = hoje or timezone.localdate()
    inicio = _inicio_da_semana(hoje)
    dias = set(
        user.weight_entries.filter(
            date__gte=inicio, date__lt=inicio + timedelta(days=7)
        ).values_list("date", flat=True)
    )
    return hoje not in dias and len(dias) < PESAGENS_POR_SEMANA


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
