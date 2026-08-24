"""Move quem estava em "moderadamente ativo" para o nível que sobrou.

O nível MODERATE ("em pé boa parte do dia") deixou de existir na recalibração
de 24/08/2026. Quem estava nele vai para LIGHT, e não para ACTIVE, porque a
recalibração inteira é no sentido conservador: o novo ACTIVE descreve trabalho
braçal o dia todo ou cardio pesado diário, que é bem mais do que "boa parte do
dia em pé". Na dúvida, a meta menor — quem come de menos emagrece um pouco mais
rápido, quem come de mais não emagrece e desiste.

O plano de cada pessoa se recalcula sozinho na próxima visita à tela, porque
`plan_is_current()` compara as entradas do plano com os dados de hoje.
"""
from django.db import migrations


def moderate_to_light(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.filter(activity_level="moderate").update(activity_level="light")


def light_back_to_moderate(apps, schema_editor):
    """Volta atrás não tem como ser exato: quem já era LIGHT também viraria
    MODERATE. Deixamos a reversão sem efeito de propósito — é mais honesto que
    reclassificar gente que nunca esteve em MODERATE."""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_activity_levels_recalibrated"),
    ]

    operations = [
        migrations.RunPython(moderate_to_light, light_back_to_moderate),
    ]
