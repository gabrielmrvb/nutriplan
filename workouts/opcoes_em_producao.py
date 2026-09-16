"""Quantas letras saem com DUAS opções, por divisão — o gate de deploy.

Regra permanente desde 16/09/2026: nenhum deploy pode reduzir o número de
letras com duas opções em produção em relação ao estado anterior. O número
não é uma promessa do catálogo; é o que o MOTOR entrega com o catálogo
ATIVO — a régua de equivalência, o teto semanal e o relógio incluídos. Por
isso a conta aqui monta uma pessoa transitória por divisão (intermediária,
"Padrão — até 60", a preferência que produz a divisão) e passa pela mesma
`create_routine` que produção usa, dentro de uma transação desfeita ao
sair: nada fica no banco.

`LETRAS_COM_OPCOES_EM_PRODUCAO` é o CONJUNTO de letras que produção TEM com
duas opções — por letra, e não uma contagem (17/09/2026): uma letra que
perde a segunda opção enquanto outra ganha é regressão para quem treina
naquela divisão, e "16 = 16" esconderia isso. O conjunto cresce quando um
deploy sobe uma letra (o relatório de deploy mostra "antes / depois" por
letra); o teste em `workouts/test_catalogo.py` fica vermelho enquanto o
código local tirar a segunda opção de qualquer letra do conjunto — e é para
ficar: o pre-push roda a suíte.
"""
from datetime import date, time

from django.db import transaction

#: As letras que produção tem com duas opções: 16 em 16/09/2026 (catálogo de
#: 35 ativos, sem `ab A` e `full A`); TODAS as 18 desde o deploy de 17/09/2026,
#: com os 63 ativos e os modelos redimensionados pelo `TREINO.md`.
LETRAS_COM_OPCOES_EM_PRODUCAO = frozenset({
    ("ab", "A"), ("ab", "B"),
    ("full", "A"),
    ("abc", "A"), ("abc", "B"), ("abc", "C"),
    ("abc2", "A"), ("abc2", "B"), ("abc2", "C"),
    ("abcd", "A"), ("abcd", "B"), ("abcd", "C"), ("abcd", "D"),
    ("abcde", "A"), ("abcde", "B"), ("abcde", "C"), ("abcde", "D"), ("abcde", "E"),
})

#: Uma pessoa por divisão: (split, dias de treino, preferência de divisão).
#: `split_for` cruza preferência com frequência, e estes pares são os que
#: produzem cada divisão do catálogo — os mesmos de `test_perfis_de_qa`.
PERFIS_POR_DIVISAO = (
    ("full", 1, "one"),
    ("ab", 2, "one"),
    ("abc", 3, "one"),
    ("abc2", 3, "two"),
    ("abcd", 4, "one"),
    ("abcde", 5, "one"),
)


class _Desfazer(Exception):
    """Sinal para a transação desfazer tudo — a conta não escreve."""


def _pessoa_transitoria(split, dias, preferencia):
    from accounts.models import (
        ONBOARDING_DONE, ActivityLevel, DuracaoTreino, Goal, Profile, Sex, TrainingDay, User,
    )

    user = User.objects.create_user(
        email="gate-%s@opcoes.invalid" % split, password="gate-sem-uso-123",
    )
    Profile.objects.create(
        user=user,
        sex=Sex.MALE,
        birth_date=date(1995, 4, 12),
        height_cm=178,
        activity_level=ActivityLevel.LIGHT,
        goal=Goal.CUT,
        wake_time=time(7, 0),
        sleep_time=time(23, 0),
        onboarding_step=ONBOARDING_DONE,
        split_preference=preferencia,
        split_preference_confirmada=True,
        experiencia="intermediario",
        duracao_treino=DuracaoTreino.PADRAO,
    )
    for weekday in range(dias):
        TrainingDay.objects.create(user=user, weekday=weekday, duration_min=60)
    return user


def opcoes_por_letra() -> dict:
    """`{(split, letra): número de opções}` com o catálogo ativo de agora.

    Tudo o que esta função cria é desfeito antes de devolver.
    """
    from . import services

    resultado = {}
    try:
        with transaction.atomic():
            for split, dias, preferencia in PERFIS_POR_DIVISAO:
                user = _pessoa_transitoria(split, dias, preferencia)
                plano = services.create_routine(user)
                if plano.split != split:
                    raise RuntimeError(
                        "o perfil de %s produziu a divisão %s" % (split, plano.split)
                    )
                vistas = set()
                for sessao in plano.sessions.order_by("order"):
                    if sessao.label in vistas:
                        continue
                    vistas.add(sessao.label)
                    resultado[(split, sessao.label)] = len(sessao.opcoes)
            raise _Desfazer
    except _Desfazer:
        pass
    return resultado


def letras_com_opcoes(por_letra=None) -> list:
    """As letras `(split, letra)` que saem com duas opções ou mais."""
    por_letra = opcoes_por_letra() if por_letra is None else por_letra
    return sorted(chave for chave, n in por_letra.items() if n >= 2)


def letras_perdidas(por_letra=None) -> list:
    """As letras que produção tem com duas opções e que aqui saem com uma —
    a lista que tem de ser VAZIA para um deploy subir."""
    por_letra = opcoes_por_letra() if por_letra is None else por_letra
    return sorted(
        chave for chave in LETRAS_COM_OPCOES_EM_PRODUCAO if por_letra.get(chave, 0) < 2
    )
