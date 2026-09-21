# -*- coding: utf-8 -*-
"""O retrato das fichas de 540 perfis — para medir ANTES e DEPOIS de uma
mudança no motor ou no catálogo (nasceu com o grupo glúteo, 21/09/2026).

    .venv/Scripts/python.exe scripts/qa/retrato_das_fichas.py gravar antes.json
    # ... a mudança ...
    .venv/Scripts/python.exe scripts/qa/retrato_das_fichas.py gravar depois.json
    .venv/Scripts/python.exe scripts/qa/retrato_das_fichas.py comparar antes.json depois.json

`NUTRIPLAN_SETTINGS=scratchpad_settings_x` aponta para um banco de teste
próprio quando há mais de uma sessão na máquina (regra do B9).

`gravar` monta a ficha para uma matriz de perfis — nível × dias × preferência
de divisão × faixa de tempo × equipamento — num banco vazio (o de teste), e
escreve, por sessão e opção, os exercícios com a dose. `comparar` diz, por
perfil e sessão, o que SAIU, o que ENTROU e o que mudou de dose. A régua da
missão é "nenhuma ficha existente perde exercício": a lista de SAIU tem de
estar vazia.

Roda dentro do runner de teste do Django (banco de teste criado e destruído
na hora), então não toca em banco nenhum de verdade.
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.environ.get("NUTRIPLAN_SETTINGS", "config.settings"))
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402

NIVEIS = ("iniciante", "intermediario", "avancado")
DIAS = (2, 3, 4, 5, 6)
PREFERENCIAS = ("one", "two", "three")
DURACOES = ("rapido", "padrao", "completo")
EQUIPAMENTOS = ("completa", "basica", "casa_halteres", "peso_corporal")


def _retrato():
    from accounts.models import TrainingDay
    from plans.tests import create_complete_user
    from workouts import services

    saida = {}
    n = 0
    for nivel in NIVEIS:
        for dias in DIAS:
            for pref in PREFERENCIAS:
                for duracao in DURACOES:
                    for equipamento in EQUIPAMENTOS:
                        n += 1
                        user = create_complete_user(
                            email="g%d@exemplo.com" % n, experiencia=nivel, split_preference=pref,
                            split_preference_confirmada=True, duracao_treino=duracao, equipamento=equipamento,
                        )
                        TrainingDay.objects.filter(user=user).delete()
                        for d in range(dias):
                            TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
                        plano = services.create_routine(user)
                        chave = "%s/%dd/%s/%s/%s" % (nivel, dias, pref, duracao, equipamento)
                        sessoes = {}
                        for s in plano.sessions.prefetch_related("exercises__exercise").order_by("order"):
                            if s.label in sessoes:
                                continue
                            por_opcao = {}
                            for item in s.exercises.all().order_by("opcao", "order"):
                                por_opcao.setdefault(str(item.opcao), []).append([item.exercise.name, item.sets])
                            sessoes[s.label] = {"nome": s.name, "split": plano.split, "opcoes": por_opcao,
                                                "principais": list(s.main_groups)}
                        saida[chave] = sessoes
                        if n % 50 == 0:
                            print(n, chave, flush=True)
    return saida


def gravar(arquivo):
    runner = DiscoverRunner(verbosity=0, interactive=False)
    setup_test_environment()
    old = runner.setup_databases()
    try:
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        retrato = _retrato()
    finally:
        runner.teardown_databases(old)
        teardown_test_environment()
    Path(arquivo).write_text(json.dumps(retrato, ensure_ascii=False, indent=1), encoding="utf-8")
    print("perfis:", len(retrato))


def comparar(antes, depois):
    a = json.loads(Path(antes).read_text(encoding="utf-8"))
    d = json.loads(Path(depois).read_text(encoding="utf-8"))
    saiu = entrou = dose = principais = 0
    for chave in a:
        for letra, sa in a[chave].items():
            sd = d.get(chave, {}).get(letra)
            if sd is None:
                print("SESSÃO SUMIU", chave, letra)
                saiu += 1
                continue
            for opcao, itens in sa["opcoes"].items():
                itens_d = {n: s for n, s in sd["opcoes"].get(opcao, [])}
                for nome, sets in itens:
                    if nome not in itens_d:
                        print("SAIU  ", chave, letra, opcao, nome)
                        saiu += 1
                    elif itens_d[nome] != sets:
                        print("DOSE  ", chave, letra, opcao, nome, sets, "->", itens_d[nome])
                        dose += 1
                for nome in itens_d:
                    if nome not in {n for n, _ in itens}:
                        print("ENTROU", chave, letra, opcao, nome)
                        entrou += 1
            if sa["principais"] != sd["principais"]:
                principais += 1
    print("\nsaiu=%d entrou=%d dose=%d principais_diferentes=%d perfis=%d" % (saiu, entrou, dose, principais, len(a)))
    return saiu


if __name__ == "__main__":
    if sys.argv[1] == "gravar":
        gravar(sys.argv[2])
    else:
        sys.exit(1 if comparar(sys.argv[2], sys.argv[3]) else 0)
