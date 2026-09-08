"""Aposenta `Remada curvada com barra` e conserta o que já foi gerado com ela.

A DECISÃO É DO PRODUTO, e é mais ampla que a de `0017`. Aquela migração
aposentou a linha LEGADA `Remada curvada` — sem vídeo, com `muscle_group`
inválido, fora de todo modelo — e registrou que a versão viva do movimento
continuava valendo. Essa parte deixou de valer: a versão ativa também sai do uso
ativo.

O QUE ESTA MIGRAÇÃO NÃO FAZ, e é o mais importante: **não apaga nada**.
`ExerciseLog.exercise` é CASCADE (`models.py:843`), então um `delete()` no
exercício levaria junto todo o histórico de carga de quem já treinou com ele, em
silêncio. Desativar é o mecanismo que o modelo tem para aposentar sem tocar em
dado, e é o que a geração de treino consulta.

TRÊS ALVOS, e cada um com regra própria:

1. **o catálogo** — `is_active=False`. O exercício continua existindo, com o
   vídeo e o nome, para o histórico poder mostrá-lo;

2. **os modelos** (`WorkoutTemplateItem`) — a linha é substituída por
   `Remada baixa na polia`, escolhida por COMPATIBILIDADE: mesmo grupo primário
   (`back`), também composta, e o mesmo padrão de puxada HORIZONTAL. Trocar por
   uma vertical deixaria o dia B com duas verticais e nenhuma horizontal.

   A associação é por NOME, que é a identidade estável do catálogo (`name` tem
   índice único e é a chave que o seed usa) — nunca por posição na lista, que
   muda quando alguém reordena a ficha.

   Quando o substituto JÁ está no modelo, duplicar violaria
   `unique_exercise_per_template`: a linha aposentada sai e o substituto herda a
   dose dela se for maior, mantendo a própria faixa e o próprio descanso;

3. **as fichas já geradas** (`SessionExercise`) — só as de planos **NÃO
   INICIADOS**. Plano iniciado é aquele em que a pessoa já registrou série
   depois de o plano nascer; nesse caso a ficha fica como está, porque mudar o
   exercício por baixo de um treino em andamento é reescrever o que a pessoa
   está fazendo. O histórico continua acessível nos dois casos.
"""
from django.db import migrations

APOSENTADO = "Remada curvada com barra"
SUBSTITUTO = "Remada baixa na polia"


def aposentar(apps, schema_editor):
    Exercise = apps.get_model("workouts", "Exercise")
    WorkoutTemplateItem = apps.get_model("workouts", "WorkoutTemplateItem")
    SessionExercise = apps.get_model("workouts", "SessionExercise")
    TrainingPlan = apps.get_model("workouts", "TrainingPlan")
    ExerciseLog = apps.get_model("workouts", "ExerciseLog")

    velho = Exercise.objects.filter(name=APOSENTADO).first()
    novo = Exercise.objects.filter(name=SUBSTITUTO).first()
    if velho is None:
        return

    # ------------------------------------------------------------ catálogo
    Exercise.objects.filter(pk=velho.pk).update(is_active=False)

    if novo is None:
        # Sem substituto no catálogo não há troca possível. Desativar já impede
        # que ele entre em plano novo — e é melhor parar aqui que inventar um
        # exercício de reposição.
        return

    # -------------------------------------------------------------- modelos
    for item in WorkoutTemplateItem.objects.filter(exercise=velho):
        irmao = WorkoutTemplateItem.objects.filter(
            template_id=item.template_id, exercise=novo
        ).first()
        if irmao is None:
            WorkoutTemplateItem.objects.filter(pk=item.pk).update(exercise=novo)
        else:
            if item.sets > irmao.sets:
                WorkoutTemplateItem.objects.filter(pk=irmao.pk).update(sets=item.sets)
            WorkoutTemplateItem.objects.filter(pk=item.pk).delete()

    # -------------------------------------------- fichas de planos não iniciados
    for plano in TrainingPlan.objects.filter(sessions__exercises__exercise=velho).distinct():
        exercicios_do_plano = SessionExercise.objects.filter(
            session__plan=plano
        ).values_list("exercise_id", flat=True)
        iniciado = ExerciseLog.objects.filter(
            user_id=plano.user_id,
            exercise_id__in=list(exercicios_do_plano),
            date__gte=plano.created_at.date(),
        ).exists()
        if iniciado:
            continue

        for linha in SessionExercise.objects.filter(
            session__plan=plano, exercise=velho
        ):
            irmao = SessionExercise.objects.filter(
                session_id=linha.session_id, exercise=novo
            ).first()
            if irmao is None:
                SessionExercise.objects.filter(pk=linha.pk).update(exercise=novo)
            else:
                if linha.sets > irmao.sets:
                    SessionExercise.objects.filter(pk=irmao.pk).update(sets=linha.sets)
                SessionExercise.objects.filter(pk=linha.pk).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workouts", "0017_desativa_remada_curvada_legada"),
    ]

    operations = [
        # A volta é no-op pelo mesmo motivo de `0017`: reverter não pode
        # ressuscitar um exercício aposentado dentro de fichas ativas.
        migrations.RunPython(aposentar, migrations.RunPython.noop),
    ]
