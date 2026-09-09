"""A experiência de treino entra como pergunta, e o vazio é resposta.

O campo nasce em branco para TODO MUNDO, e isso é a decisão, não uma economia:
ninguém nunca respondeu esta pergunta, então não há nada para converter, e
gravar `intermediario` na base inteira faria a tela afirmar "treino há mais de
6 meses" para gente que nunca disse isso. É a doutrina da `0024` — uso não é
intenção declarada — e a de `prioridade == ""`.

RETROCOMPATÍVEL SEM `RunPython`, e por isso a migration é só o `AddField`:

- o motor não muda de número. `workouts.services.teto_semanal_de` lê o campo
  vazio como 20, que é `TETO_SEMANAL_POR_GRUPO`, o teto que o app já praticava.
  Nenhuma ficha existente deixa de valer, e `routine_is_current` não passa a
  reprovar plano nenhum por causa desta coluna;
- nada é inferido de histórico. Contar treinos gravados para deduzir "avançado"
  seria exatamente o que a `0024` se recusou a fazer com a prioridade.

REVERSÍVEL sem perda: a volta é o `AddField` invertido, que remove a coluna. Só
se perde o que esta migration criou, e quem revert-ar já sabe disso.

Nenhum `default` silencioso altera intenção: o `default=""` do modelo existe
para as linhas antigas ganharem um valor NOT NULL, e "" é justamente a ausência
de intenção.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0027_horario_do_treino_opcional"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="experiencia",
            field=models.CharField(
                blank=True,
                choices=[
                    ("iniciante", "Iniciante — comecei há menos de 6 meses"),
                    (
                        "intermediario",
                        "Intermediário — treino há mais de 6 meses",
                    ),
                    (
                        "avancado",
                        "Avançado — treino há anos, sem interrupções longas",
                    ),
                ],
                default="",
                max_length=15,
                verbose_name="experiência com treino",
            ),
        ),
    ]
