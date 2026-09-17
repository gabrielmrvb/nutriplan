"""`TrocaDeExercicio` (17/09/2026): "outras formas" — a troca de um exercício
da ficha por outro do mesmo padrão, por pessoa, reversível. Tabela nova;
nenhuma linha existente é tocada.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions


class Migration(migrations.Migration):

    dependencies = [
        ("workouts", "0028_equipamento_no_plano"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TrocaDeExercicio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("original", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trocas_como_original", to="workouts.exercise", verbose_name="original")),
                ("substituto", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trocas_como_substituto", to="workouts.exercise", verbose_name="substituto")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trocas_de_exercicio", to=settings.AUTH_USER_MODEL, verbose_name="usuário")),
            ],
            options={
                "verbose_name": "troca de exercício",
                "verbose_name_plural": "trocas de exercício",
            },
        ),
        migrations.AddConstraint(
            model_name="trocadeexercicio",
            constraint=models.UniqueConstraint(fields=("user", "original"), name="uma_troca_por_exercicio_e_pessoa"),
        ),
        migrations.AddConstraint(
            model_name="trocadeexercicio",
            constraint=models.CheckConstraint(condition=models.Q(("original", models.F("substituto")), _negated=True), name="troca_muda_de_exercicio"),
        ),
    ]
