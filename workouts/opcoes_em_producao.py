"""Quantas opções cada letra de FICHA NOVA recebe, por divisão — o gate de deploy.

Regra de 16/09/2026, INVERTIDA em 27/09/2026 por decisão do dono ("Fichas
novas com uma variante só"; "letra repetida faz sempre o mesmo treino —
variação é troca por exercício na linha, escolha da pessoa"). Era: nenhum
deploy reduz o número de letras com duas opções, e as 18 letras das seis
divisões tinham de sair com duas. É: nenhuma letra de ficha nova sai com
duas — `LETRAS_COM_OPCOES_EM_PRODUCAO` ficou VAZIO e `letras_a_mais` tem de
devolver lista vazia. As fichas ANTIGAS com opção 2 (12 ativas em
27/09/2026) continuam sendo lidas; este gate não fala delas.

O número não é uma promessa do catálogo; é o que o MOTOR entrega com o
catálogo ATIVO — a montagem por cota, o teto semanal e o relógio incluídos.
Por isso a conta monta uma pessoa transitória por divisão (intermediária,
"Padrão — até 60", a preferência que produz a divisão) e passa pela mesma
`create_routine` que produção usa, dentro de uma transação desfeita ao sair:
nada fica no banco. O teste em `workouts/test_catalogo.py` fica vermelho se
o código local devolver uma segunda opção a qualquer letra — e o pre-push
roda a suíte.
"""
from datetime import date, time

from django.db import transaction

#: As letras que uma ficha nova PODE ter com duas opções. Eram as 18 do
#: catálogo (17/09/2026); desde 27/09/2026, nenhuma.
LETRAS_COM_OPCOES_EM_PRODUCAO = frozenset()

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


def letras_a_mais(por_letra=None) -> list:
    """As letras com duas opções fora de `LETRAS_COM_OPCOES_EM_PRODUCAO` — a
    lista que tem de ser VAZIA para um deploy subir."""
    return sorted(set(letras_com_opcoes(por_letra)) - LETRAS_COM_OPCOES_EM_PRODUCAO)
