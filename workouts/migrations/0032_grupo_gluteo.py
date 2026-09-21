# -*- coding: utf-8 -*-
"""O glúteo vira grupo próprio (21/09/2026).

Até aqui a elevação pélvica e as pontes de glúteo eram "posterior de coxa e
glúteo": o maior músculo do corpo não aparecia em conta nenhuma — nem no
volume por grupo, nem no teto semanal, nem no título da sessão. Separar é o
que trapézio e antebraço já fizeram em `0005`.

A reclassificação é POR NOME (identidade), nunca por posição, e mexe só no
`muscle_group` das quatro linhas: `SessionExercise` e `ExerciseLog` apontam
para o `Exercise` pela chave e não sabem de grupo — nenhuma ficha e nenhum
histórico é tocado. A prova de que ficha nenhuma perde exercício está em
`workouts/test_gluteo.py` (uma ficha montada ANTES da migração continua com
as mesmas linhas DEPOIS e não é julgada desatualizada) e no retrato de 540
perfis de `scripts/qa/retrato_das_fichas.py`.

O `seed_workouts` roda a cada deploy lendo `exercises.json`, que já diz
`glutes` para os quatro — a migração existe para o banco não ficar UM deploy
com o rótulo velho até o seed correr, e para o `--reverse` devolver o estado
anterior.
"""
from django.db import migrations, models

GLUTEO = (
    "Elevação pélvica",
    "Elevação pélvica no banco",
    "Ponte de glúteo",
    "Ponte de glúteo unilateral",
)

CHOICES = [
    ("chest", "Peito"), ("back", "Costas"), ("quads", "Quadríceps"),
    ("hamstrings", "Posterior de coxa"), ("glutes", "Glúteo"), ("calves", "Panturrilha"),
    ("shoulders", "Ombros"), ("biceps", "Bíceps"), ("triceps", "Tríceps"),
    ("core", "Abdômen e core"), ("traps", "Trapézio"), ("forearms", "Antebraço"),
]


def para_gluteo(apps, schema_editor):
    Exercise = apps.get_model("workouts", "Exercise")
    Exercise.objects.filter(name__in=GLUTEO, muscle_group="hamstrings").update(muscle_group="glutes")


def de_volta(apps, schema_editor):
    Exercise = apps.get_model("workouts", "Exercise")
    Exercise.objects.filter(name__in=GLUTEO, muscle_group="glutes").update(muscle_group="hamstrings")


class Migration(migrations.Migration):

    dependencies = [
        ("workouts", "0031_merge_20260920_2352"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exercise",
            name="muscle_group",
            field=models.CharField(choices=CHOICES, max_length=12, verbose_name="grupo muscular"),
        ),
        migrations.RunPython(para_gluteo, de_volta),
    ]
