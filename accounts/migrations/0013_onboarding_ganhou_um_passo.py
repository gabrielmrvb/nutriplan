"""Quem já terminou o onboarding não volta para dentro dele.

O wizard ganhou um passo (a divisão de treino), então `ONBOARDING_DONE` subiu
de 5 para 6. `onboarding_complete` é `onboarding_step >= ONBOARDING_DONE`: sem
esta migração, todo mundo que estava em 5 — ou seja, todo mundo que TERMINOU —
acordaria incompleto e seria jogado de volta no wizard, para refazer um passo
que já tinha feito.

O caminho de volta desfaz a mesma conta, e é honesto: quem terminou sob a
numeração nova volta a terminar sob a antiga.
"""
from django.db import migrations

ANTES = 5
DEPOIS = 6


def avancar(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.filter(onboarding_step__gte=ANTES).update(onboarding_step=DEPOIS)


def voltar(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.filter(onboarding_step__gte=DEPOIS).update(onboarding_step=ANTES)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_profile_meal_style_profile_split_preference"),
    ]

    operations = [
        migrations.RunPython(avancar, voltar),
    ]
