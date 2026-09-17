"""`TrainingPlan.equipamento` (17/09/2026): o retrato do perfil de equipamento.

Default constante "completa", o mesmo de `accounts.0035`: toda ficha anterior
à pergunta foi montada com o catálogo inteiro, e com o plano e o perfil no
mesmo valor `rotina_invalida` não remonta ninguém. Sem reescrever linha.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workouts", "0027_evento_de_produto"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingplan",
            name="equipamento",
            field=models.CharField(default="completa", max_length=15, verbose_name="equipamento de origem"),
        ),
    ]
