"""Quem nunca respondeu a duração passa a valer "Padrão — 45 a 60 minutos".

ELA É REDE, E NÃO O CONSERTO — e eu escrevi o contrário aqui primeiro. O
conserto de verdade é a `0030`, que troca o DEFAULT do campo de `livre` para
`padrao`: `duracao_treino == ""` não acontece pelo ORM, porque o campo sempre
teve default. Medido no banco de desenvolvimento antes de escrever isto: 165 em
`padrao`, 48 em `rapido`, 42 em `completo` e ZERO em branco — a `0026` já tinha
convertido todo mundo a partir do `duration_min`.

O que esta migration cobre é linha escrita FORA do ORM (fixture, SQL à mão,
carga de dados antiga). Custa uma consulta indexada e não faz mal nenhum; o que
faria mal é alguém ler o parágrafo anterior e achar que o buraco estava tapado.

POR QUE UMA MIGRATION, E NÃO UM PADRÃO EM TEMPO DE LEITURA. O campo saiu da
interface em 10/09/2026: a pergunta "rápido, padrão, completo ou sem limite?"
pedia uma calibração que ninguém consegue fazer antes de ver uma ficha. Um
estado que a pessoa não pode mais mudar precisa de um valor, não de um buraco.

Escrever o valor aqui, uma vez, é diferente de trocar o padrão dentro de
`teto_de_minutos`. O padrão em tempo de leitura mudaria a resposta de toda
consulta futura sem deixar rastro; a migration deixa o dado explícito, e quem
abrir o admin vê o que a pessoa tem.

O QUE ELA NÃO FAZ, e cada limite importa:

  - **não toca em quem já respondeu.** O filtro é `duracao_treino=""`, então
    quem escolheu "rápido" continua em rápido e quem escolheu "sem limite"
    continua sem limite. O motor segue capaz de processar as quatro faixas;
    o que saiu foi a pergunta, não as regras;
  - **não remonta ficha nenhuma.** Ela grava um campo do `Profile` e para.
    A ficha é remontada pelo caminho de sempre — `routine_is_current` compara
    a prescrição de hoje com a gravada, na próxima visita à tela.

A CONSEQUÊNCIA REAL, dita porque é real: quem estava em `""` treinava sem teto
de tempo e passa a ter um de 60 minutos. Na próxima visita a ficha dessa pessoa
é remontada mais curta. É a mudança que a decisão de produto pede — "para
novos perfis ou valores ausentes, adote Padrão" —, e ela não é silenciosa: a
nota do plano passa a dizer que a ficha foi ajustada ao tempo (`aviso_de_tempo`).

Reversível: a volta devolve `""` só a quem esta migration tocou, e isso não é
recuperável linha a linha — quem já estava em "padrão" antes dela permaneceria.
Por isso a reversa é `noop` declarada, e não uma tentativa de adivinhar.
"""
from django.db import migrations


def padrao_para_quem_nao_respondeu(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    Profile.objects.filter(duracao_treino="").update(duracao_treino="padrao")


def nao_desfaz(apps, schema_editor):
    """Sem volta: não dá para saber quem estava em `""` antes desta migration.

    Devolver `""` a todo mundo que está em "padrao" apagaria a resposta de quem
    escolheu padrão na tela, quando ela ainda existia. Um `noop` honesto é
    melhor que uma reversa que perde dado.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0028_experiencia_de_treino"),
    ]

    operations = [
        migrations.RunPython(padrao_para_quem_nao_respondeu, nao_desfaz),
    ]
