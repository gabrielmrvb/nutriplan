"""`Profile.equipamento` (17/09/2026): o que a pessoa tem para treinar.

Default constante "completa" — a verdade de toda conta anterior à pergunta,
porque toda ficha até aqui foi montada com o catálogo inteiro. Nenhuma linha
é reescrita (PostgreSQL 11+: default constante é mudança de catálogo), e
nenhuma ficha é remontada: `workouts.0028` dá o mesmo valor ao plano.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0034_completo_volta_a_noventa"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="equipamento",
            field=models.CharField(
                choices=[
                    ("completa", "Academia completa — barra, halteres, máquinas e polias"),
                    ("basica", "Academia básica — halteres, máquinas e polias, sem barra livre"),
                    ("casa_halteres", "Em casa, com halteres"),
                    ("peso_corporal", "Só o peso do corpo"),
                ],
                default="completa",
                max_length=15,
                verbose_name="equipamento disponível",
            ),
        ),
    ]
