"""A duração do treino vira FAIXA, e ninguém cai no padrão por acidente.

O campo nasce com `LIVRE`, que é a resposta honesta para quem nunca respondeu.
Mas quem já usa o app RESPONDEU — digitou um número em "Tempo disponível" —, e
deixá-lo cair no padrão apagaria a escolha dele em silêncio. Este `RunPython`
converte cada pessoa a partir do `duration_min` que ela já tem gravado.

RETROCOMPATÍVEL E REVERSÍVEL, e as duas palavras têm consequência aqui:

- `TrainingDay.duration_min` NÃO é tocado. Ele continua sendo o contrato de
  `plans/meal_planner.py`, que soma `start_time + duration_min` para não marcar
  refeição no meio do treino. Mexer nele por causa desta campanha mudaria o
  cardápio de todo mundo;
- a volta é `noop` de propósito, e não um `RunPython` que apaga a coluna: a
  coluna inteira some com o `AddField` revertido, então zerar valores antes
  seria trabalho para destruir o que já vai ser destruído.

A conversão usa `duracao_de_minutos`, a MESMA função que o formulário usa para
abrir com a escolha certa de quem volta ao passo. Uma segunda tabela aqui
divergiria da primeira na primeira borda que alguém ajustasse.
"""
from django.db import migrations, models


def faixa_a_partir_do_numero(apps, schema_editor):
    from accounts.models import duracao_de_minutos

    Profile = apps.get_model("accounts", "Profile")
    TrainingDay = apps.get_model("accounts", "TrainingDay")

    # Uma consulta para todos os dias, e o menor por pessoa em memória. Uma
    # consulta por perfil seria N+1 numa migration que roda em todo deploy.
    #
    # O MENOR e não a média: os dias têm o mesmo número hoje, porque o
    # formulário grava um só para todos. Se algum dia divergirem, o teto que
    # não mente é o do dia mais curto.
    menor = {}
    for user_id, minutos in TrainingDay.objects.values_list("user_id", "duration_min"):
        if minutos and (user_id not in menor or minutos < menor[user_id]):
            menor[user_id] = minutos

    para_salvar = []
    for perfil in Profile.objects.all().only("id", "user_id", "duracao_treino"):
        minutos = menor.get(perfil.user_id)
        if not minutos:
            # Sem dia de treino cadastrado não houve resposta nenhuma, e LIVRE
            # — que já é o padrão do campo — é o que essa ausência significa.
            continue
        perfil.duracao_treino = duracao_de_minutos(minutos)
        para_salvar.append(perfil)

    Profile.objects.bulk_update(para_salvar, ["duracao_treino"], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_alter_profile_prioridade"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="duracao_treino",
            field=models.CharField(
                choices=[
                    ("rapido", "Rápido — até 30 minutos"),
                    ("padrao", "Padrão — 45 a 60 minutos"),
                    ("completo", "Completo — 60 a 90 minutos"),
                    ("livre", "Sem limite rígido — priorizar a ficha completa"),
                ],
                default="livre",
                max_length=10,
                verbose_name="duração do treino",
            ),
        ),
        migrations.RunPython(
            faixa_a_partir_do_numero, migrations.RunPython.noop
        ),
    ]
