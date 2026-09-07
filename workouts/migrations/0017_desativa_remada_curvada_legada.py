"""Desativa o exercício legado `Remada curvada` — e conserta o grupo dele.

DE ONDE ELE VEIO. O catálogo do seed tem 36 linhas e nunca teve esta. Ela é
sobra de uma versão anterior, de quando o `muscle_group` ainda era escrito em
português: o valor gravado é `"costas"`, que NÃO existe em `MuscleGroup` —
`full_clean()` recusaria a linha hoje. Ela está sem vídeo, fora de toda
`WorkoutTemplateItem`, e a versão viva do movimento é `Remada curvada com
barra`.

POR QUE NÃO APAGAR — e a razão é o CONTRÁRIO da que este arquivo dizia.

A primeira versão afirmava que `ExerciseLog.exercise` é `PROTECT` "justamente
para que ninguém leve o histórico junto". Falso, e uma revisão adversarial
pegou: `PROTECT` são `WorkoutTemplateItem.exercise` e `TrainingSession.exercise`
(`models.py:709` e `:808`); `ExerciseLog.exercise` é **CASCADE**
(`models.py:843`). Um `Exercise.objects.filter(...).delete()` no shell ou no
admin APAGA o histórico de carga junto, em silêncio.

Ou seja: não apagar não é excesso de cuidado com uma trava que existe — é a
única coisa que separa o histórico de sumir. Desativar é o mecanismo que o
modelo tem para aposentar exercício sem tocar em dado, e é o que a geração de
treino consulta.

E O GRUPO É CORRIGIDO JUNTO porque desativar não tira a linha da tela: o
histórico ainda a lê, e `get_muscle_group_display()` sobre um valor fora da
taxonomia devolve a própria string crua. Deixar `"costas"` seria manter um
valor inválido em banco por conveniência.
"""
from django.db import migrations

LEGADO = "Remada curvada"


def desativar(apps, schema_editor):
    Exercise = apps.get_model("workouts", "Exercise")
    Exercise.objects.filter(name=LEGADO).update(is_active=False, muscle_group="back")


class Migration(migrations.Migration):

    dependencies = [
        ("workouts", "0016_exercise_secondary_muscles_and_more"),
    ]

    operations = [
        # A volta é no-op de propósito: reverter esta migração não pode
        # RESSUSCITAR um exercício legado no catálogo ativo.
        migrations.RunPython(desativar, migrations.RunPython.noop),
    ]
