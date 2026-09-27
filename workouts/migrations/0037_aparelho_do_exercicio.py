# -*- coding: utf-8 -*-
"""O catálogo passa a dizer o que o exercício exige além do corpo.

`Equipment` não distingue a flexão de braço da barra fixa — as duas são
`bodyweight` —, e por isso a ficha de quem treina em casa só com o peso do
corpo vinha com a letra "Costas e bíceps" INTEIRA em barra fixa: cinco
exercícios, quinze séries, nenhum possível naquela casa (medido em
24/09/2026 com a persona 1).

O preenchimento é POR NOME, como a `0032` fez com o glúteo: o catálogo é
semeado a cada deploy (`seed_workouts` grava o mesmo valor), então a
migration existe para o banco que já está de pé — e para ele ficar igual ao
JSON sem esperar o seed. Reversível: a volta zera a coluna antes de ela sair,
e o que ela guardava continua no `exercises.json`.
"""
from django.db import migrations, models

#: Onze nomes, escolhidos sobre a lista inteira dos 43 de peso do corpo. O que
#: não está aqui não exige nada além do chão — ou exige banco, cadeira ou
#: parede, que toda casa tem e que por isso não viraram valor (a razão está no
#: docstring de `workouts.models.Aparelho`).
APARELHO = {
    "barra_fixa": (
        "Barra fixa com pegada supinada",
        "Barra fixa negativa",
        "Barra fixa pronada",
        "Elevação de joelhos na barra",
        "Suspensão na barra",
        "Encolhimento na barra fixa",
    ),
    "barra_baixa": (
        "Remada invertida",
        "Remada invertida com pés elevados",
        "Rosca invertida na barra baixa",
    ),
    "paralelas": ("Mergulho nas paralelas",),
    "inversao": ("Flexão parada de mão na parede",),
}


def marcar(apps, schema_editor):
    Exercise = apps.get_model("workouts", "Exercise")
    for aparelho, nomes in APARELHO.items():
        Exercise.objects.filter(name__in=nomes).update(aparelho=aparelho)


def desmarcar(apps, schema_editor):
    """A volta zera a coluna antes de ela ser removida.

    Não é `noop`: uma migration que só sobe deixa o banco num estado que o
    código de baixo não sabe ler.
    """
    Exercise = apps.get_model("workouts", "Exercise")
    Exercise.objects.exclude(aparelho="").update(aparelho="")


class Migration(migrations.Migration):

    dependencies = [
        ("workouts", "0036_nota_e_falha_da_serie"),
    ]

    operations = [
        migrations.AddField(
            model_name="exercise",
            name="aparelho",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "nada além do corpo"),
                    ("barra_fixa", "barra fixa"),
                    ("paralelas", "paralelas"),
                    ("inversao", "inversão (parada de mão)"),
                    ("barra_baixa", "barra baixa ou mesa"),
                ],
                default="",
                max_length=12,
                verbose_name="aparelho exigido",
            ),
        ),
        migrations.RunPython(marcar, desmarcar),
    ]
