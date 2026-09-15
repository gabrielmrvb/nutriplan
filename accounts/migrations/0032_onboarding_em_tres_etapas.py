"""O onboarding passou de seis passos para três etapas (15/09/2026).

`onboarding_step` guarda a PRÓXIMA etapa a fazer. Quem parou no meio do
wizard antigo é remapeado para a etapa nova que contém o que falta:

    1 -> 1   (ainda não gravou os dados corporais)
    2 -> 2   (fez o 1; objetivo/rotina/divisão ficam na etapa 2)
    3 -> 2   (fez 1-2; os dias ainda não — etapa 2)
    4 -> 3   (fez 1-3; divisão era condicional e agora é progressiva na 2 —
              quem chegou aqui com 4+ dias responde a divisão ao voltar
              à etapa 2 pelo Perfil, nunca por bloqueio)
    5 -> 3   (fez 1-4; comida e áreas ficam na etapa 3)
    6 -> 3   (fez 1-5; áreas ficam na etapa 3)
    7 -> 7   (concluído — `ONBOARDING_DONE` não mudou, e é por isso que esta
              migration NÃO escreve em nenhuma conta concluída)

Só `UPDATE` sobre quem está abaixo de 7; a reversa é no-op, porque não há
como saber de qual passo antigo alguém veio.
"""

from django.db import migrations

DE_PARA = {2: 2, 3: 2, 4: 3, 5: 3, 6: 3}


def para_tres_etapas(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    for antigo, novo in DE_PARA.items():
        if antigo != novo:
            Profile.objects.filter(onboarding_step=antigo).update(onboarding_step=novo)


#: NÃO é idempotente, e isso é dito: o 3 antigo (dias de treino) e o 3 novo
#: (personalização) são o mesmo número, então reaplicar depois de reverter
#: mandaria quem está na etapa 3 nova para a 2. O `migrate` normal roda uma
#: vez; a reversa é no-op de propósito (não há como reinventar o passo antigo).
class Migration(migrations.Migration):
    dependencies = [("accounts", "0031_plano_gratis_ou_pro")]
    operations = [migrations.RunPython(para_tres_etapas, migrations.RunPython.noop)]
