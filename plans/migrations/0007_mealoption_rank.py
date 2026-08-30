"""`MealOption.label` vira `MealOption.rank`.

O cardápio V2 guarda um repertório de quatro opções por horário e mostra duas
por dia. O antigo `label` não comportava isso: era `max_length=1` com escolhas
A e B, e crescer significaria inventar "C" e "D" — texto de tela virando chave
de negócio, que é exatamente o que não se quer.

O caminho é conservador de propósito, em seis passos, porque produção já tem
plano e histórico:

  1. cria `rank` aceitando nulo;
  2. preenche: A vira 0, B vira 1, e qualquer coisa fora disso entra por ordem
     de pk dentro do slot;
  3. fecha `rank` para não-nulo;
  4. tira a unicidade por rótulo;
  5. põe a unicidade por posição;
  6. remove `label`.

A ordem importa. Fechar o campo antes do backfill quebraria em qualquer linha
existente, e trocar as constraints antes de o rank estar preenchido deixaria a
tabela um instante sem unicidade nenhuma.

`MealLog` NÃO é tocado. O histórico aponta para `MealOption` por chave
estrangeira e guarda o próprio retrato (`recipe_name` e os macros); nada aqui
lê ou reescreve o passado.
"""

from django.db import migrations, models


def label_para_rank(apps, schema_editor):
    """A → 0, B → 1. O resto entra por ordem de pk dentro do slot.

    O `else` não é decoração: se algum dia alguém inseriu uma opção fora das
    duas letras — pelo admin, por fixture, por script —, deixá-la sem rank
    faria o passo seguinte estourar com a migration já pela metade. Ordem de pk
    é a ordem em que as opções nasceram, que é o mais próximo de "posição" que
    um dado sem rótulo conhecido tem.
    """
    MealOption = apps.get_model("plans", "MealOption")
    conhecidos = {"A": 0, "B": 1}

    por_slot = {}
    for opcao in MealOption.objects.order_by("slot_id", "pk").iterator():
        por_slot.setdefault(opcao.slot_id, []).append(opcao)

    atualizar = []
    for opcoes in por_slot.values():
        usados = set()
        pendentes = []
        for opcao in opcoes:
            rank = conhecidos.get(opcao.label)
            if rank is None or rank in usados:
                pendentes.append(opcao)
                continue
            usados.add(rank)
            opcao.rank = rank
            atualizar.append(opcao)
        # Os que não tinham rótulo conhecido (ou colidiram) ocupam os buracos
        # que sobraram, na ordem em que nasceram.
        livre = 0
        for opcao in pendentes:
            while livre in usados:
                livre += 1
            usados.add(livre)
            opcao.rank = livre
            atualizar.append(opcao)

    if atualizar:
        MealOption.objects.bulk_update(atualizar, ["rank"], batch_size=500)


def rank_para_label(apps, schema_editor):
    """A volta. 0 → A, 1 → B; posições acima de 1 não cabem no rótulo.

    Reverter esta migration num banco que já tem repertório de quatro
    descartaria as opções 2 e 3, porque `label` só tem duas letras válidas e a
    unicidade por rótulo recusaria as demais. Apagar dado numa reversão é pior
    que falhar nela, então elas são apagadas SOMENTE aqui, no caminho de volta,
    e o comentário existe para que ninguém rode isso achando que é inócuo.
    """
    MealOption = apps.get_model("plans", "MealOption")
    MealOption.objects.filter(rank__gte=2).delete()
    MealOption.objects.filter(rank=0).update(label="A")
    MealOption.objects.filter(rank=1).update(label="B")


class Migration(migrations.Migration):

    dependencies = [("plans", "0006_meallog_recipe_name")]

    operations = [
        migrations.AddField(
            model_name="mealoption",
            name="rank",
            field=models.PositiveSmallIntegerField(
                null=True, verbose_name="posição no repertório"
            ),
        ),
        migrations.RunPython(label_para_rank, rank_para_label),
        migrations.AlterField(
            model_name="mealoption",
            name="rank",
            field=models.PositiveSmallIntegerField(verbose_name="posição no repertório"),
        ),
        migrations.RemoveConstraint(
            model_name="mealoption", name="unique_label_per_slot"
        ),
        migrations.AddConstraint(
            model_name="mealoption",
            constraint=models.UniqueConstraint(
                fields=("slot", "rank"), name="unique_rank_per_slot"
            ),
        ),
        migrations.AlterModelOptions(
            name="mealoption",
            options={
                "ordering": ["rank"],
                "verbose_name": "opção de refeição",
                "verbose_name_plural": "opções de refeição",
            },
        ),
        migrations.RemoveField(model_name="mealoption", name="label"),
    ]
