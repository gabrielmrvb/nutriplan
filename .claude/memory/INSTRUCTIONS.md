# Memória do NutriPlan — regras

Adaptado do memory-bootstrap do toolkit em 27/09/2026. Duas camadas: este
diretório (`.claude/memory/`) é a camada RÁPIDA, lida no começo da sessão;
a camada de LONGO PRAZO é o próprio `CLAUDE.md` da raiz. Não há Obsidian
nem wiki: o que sai daqui vai para lá.

## O que vale salvar — o teste estreito

Salve só quando a resposta for sim: **uma sessão futura ficaria surpresa e
grata de saber disto ANTES de começar, em vez de descobrir do jeito caro?**

- Deriva-se lendo o código, o git ou o `CLAUDE.md` sem esforço → não salve.
- Prazo, motivação do momento, qualquer coisa temporária → não salve.
- Receita de depuração que cabe numa mensagem de commit → não salve.
- Erro que uma sessão cometeu e teve de corrigir, regra espalhada que
  ninguém acha num lugar só, armadilha medida do ambiente, onde fica algo
  fora do repositório → salve.

Na dúvida, não salve. Índice pequeno e lido vence índice grande e ignorado.

## REPOSITÓRIO PÚBLICO

Este repositório é público desde 21/09/2026. Aqui NUNCA entra: segredo
(chave, token, URL de banco, senha — nem parcial), dado pessoal de quem usa
o app, nem estratégia de negócio (pesquisa, preço, canal, leitura jurídica).
Estratégia mora no repositório PRIVADO `gabrielmrvb/nutriplan-docs`.

## Formato

Um arquivo por fato, `<slug>.md`, com frontmatter:

```
---
name: kebab-case-slug
description: uma linha — é por ela que a sessão futura julga relevância
metadata:
  type: feedback | architecture | business-rule | reference
---
```

Corpo de 3 a 8 linhas em prosa medida, com a data e o PORQUÊ, e uma linha
`Fonte:` com `arquivo:linha` conferida no repositório no dia da escrita.
No `MEMORY.md`, uma linha por entrada: `- [Título](slug.md) — gancho`.

## Política de crescimento

Teto do índice: **130 linhas não em branco** no `MEMORY.md`. Antes de
acrescentar, conte. Passou do teto, sanear primeiro:

1. Pontue cada entrada: recência × especificidade × chance de evitar um
   erro real.
2. Para cada entrada de nota baixa, MIGRE — nunca só apague —, nesta ordem:
   1. **Dedup**: procure no `CLAUDE.md` a seção do mesmo assunto e
      ESTENDA-a em vez de criar outra;
   2. **Siga o molde** do `CLAUDE.md`: parágrafo com a regra em negrito, a
      data e a razão medida;
   3. **Escreva** a seção (avisando pelo ledger antes, como qualquer
      edição de arquivo comum);
   4. **Confirme** relendo o trecho do `CLAUDE.md`. Sem leitura de volta,
      sem apagar;
   5. **Só então** apague a linha do índice e o arquivo do tópico.
3. Reescreva o índice com o que sobrou; depois acrescente a entrada nova.

Apagar antes da leitura de volta é perda de dado, não faxina. Na dúvida se
uma entrada ainda merece o lugar, deixe-a.
