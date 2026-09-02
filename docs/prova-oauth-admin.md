# Prova humana: entrar no Admin pelo Google

**Por que só você pode fazer:** o seletor de contas do Google não responde a
evento sintético, e a janela dele fica fora do alcance das duas pontes de
navegador que eu uso. Tudo o que vem antes e depois do clique já está medido —
falta o clique.

**Tempo:** 3 a 4 minutos.

**Antes de começar:** esteja DESLOGADO do NutriPlan. Se estiver logado, o passo
1 vai direto para o Admin e o teste não mede nada (e isso, aliás, é o item 7).

---

## Roteiro

**1.** Abra `https://nutriplan-xxfn.onrender.com/admin/`

Anote para onde foi: `_______________________`

> Esperado: `/conta/entrar/?next=/admin/`

**2.** Confira a barra de endereço. O `next=/admin/` está lá?  ☐ sim ☐ não

**3.** Clique em **Continuar com Google** e escolha sua conta.

**4.** Depois do callback, onde você parou?  `_______________________`

> Esperado: `/admin/` — e não a tela inicial do app.
> É este passo que prova que o destino atravessou o Google.

**5.** No Admin, abra **Usuários** e clique na sua conta. Confira:

- Aparece o botão ou o aviso de **divisão de treino**?  ☐ sim ☐ não
- A coluna **GOOGLE** na lista mostra o ícone de sim?  ☐ sim ☐ não
- Existe algum campo editável de **superusuário**, **membro da equipe**,
  **grupos** ou **permissões**?  ☐ nenhum ☐ apareceu algum: ______

**6.** Cole na barra de endereço:
`https://nutriplan-xxfn.onrender.com/admin/login/?next=https://exemplo-de-outro-site.com/`

Para onde foi?  `_______________________`

> Esperado: `/conta/entrar/?next=/admin/` — o endereço externo é DESCARTADO.
> Se aparecer `exemplo-de-outro-site` em qualquer lugar, pare e me avise.

**7.** Com a sessão já aberta, abra `/admin/` de novo.

Pediu Google outra vez?  ☐ não (esperado) ☐ sim

**8.** Saia pelo botão **Sair** e abra `/admin/` mais uma vez.

Para onde foi?  `_______________________`

> Esperado: de volta para `/conta/entrar/`.

---

## O que já está provado sem você

Medido em produção por HTTP, sem sessão:

- anônimo em `/admin/` vai para `/admin/login/?next=/admin/`
- o `next` interno é preservado até o formulário do botão do Google
- `/admin/login/?next=https://outro-site/` descarta o endereço externo e usa
  `/admin/`
- o provedor Google continua ligado e a tela de login o oferece

Medido no banco de produção (somente leitura):

- PK 43: `is_staff=true`, `is_superuser=false`, senha inutilizável, tem conta
  Google vinculada, só no grupo Administradores, zero permissões avulsas

O que **não** está provado é a volta do callback — e é isso que o passo 4 mede.

## Se algo sair diferente

Anote o passo e o que apareceu. Não tente consertar: qualquer alteração no
fluxo antes de eu ver o comportamento apaga a evidência.
