# Prova de campo: a corrida num aparelho de verdade

**Por que só você pode fazer:** o comportamento do GPS depende do sistema
operacional, do navegador e do estado de energia do aparelho. Nada disso
existe aqui. É a diferença entre "o código está certo" e "funciona na rua".

**Tempo:** 10 a 15 minutos, com uma caminhada curta.

**Onde:** rua aberta, não dentro de casa. Perto de prédio alto o GPS erra de
propósito, e é justamente isso que o item 3 mede.

**Não anote nenhuma coordenada.** Nenhum item aqui precisa delas, e escrever a
rua onde você correu num arquivo do repositório é o oposto do que o app faz.

---

## Antes de sair

Preencha:

- Aparelho: `_______________`
- Sistema e versão: `_______________`
- Navegador: `_______________`
- Instalado como app (tela inicial) ou aberto no navegador? `_________`
- Bateria no início: `____%`

Abra `https://nutriplan-xxfn.onrender.com/treino/` e toque em
**Abrir corridas**.

---

## Roteiro

**1. Permissão.** Toque em **Começar corrida**.

Pediu permissão de localização?  ☐ sim ☐ não (já tinha)
Se você RECUSAR, o que a tela diz? `_______________________`

> Esperado ao recusar: uma frase dizendo que sem permissão não dá para
> registrar — e não uma tela travada em "procurando sinal".

**2. Início.** Aceite a permissão e fique parado.

Quantos segundos até a distância sair de 0,00? `____ s`
O aviso "Procurando sinal de GPS" apareceu?  ☐ sim ☐ não

**3. Parado.** Fique parado mais 60 segundos, com o telefone na mão.

Distância depois de 1 minuto parado: `_____ km`

> Esperado: continua 0,00. Se subir, o filtro de ruído está frouxo demais para
> a precisão do seu aparelho — e é esse número que me diz qual limite usar.

**4. Caminhada lenta.** Ande devagar por 2 minutos.

Distância marcada: `_____ km`
Distância real aproximada (passos × 0,7 m, ou o quarteirão): `_____ m`

> É o item que mais me interessa. O filtro tem um piso de deslocamento, e a
> caminhada é o caso que ele quase quebrou.

**5. Ritmo normal.** Ande rápido ou corra por 3 minutos.

Distância: `_____ km` · Pace mostrado: `_____ min/km`
O pace parece plausível?  ☐ sim ☐ não, mostrava: `______`

**6. Pausa.** Toque em **Pausar**. Ande 30 metros. Toque em **Retomar**.

A distância mudou durante a pausa?  ☐ não (esperado) ☐ sim, subiu `___ m`
O cronômetro parou?  ☐ sim ☐ não

**7. Tela apagada — o item central.** Com a corrida rodando, aperte o botão de
bloquear e ande 1 minuto. Destrave e volte ao app.

A tela tinha apagado sozinha antes disso?  ☐ não (o Wake Lock segurou)
☐ sim, depois de `____`

Ao voltar, apareceu o aviso de trecho sem registro?  ☐ sim ☐ não
A corrida continuou contando depois de voltar?  ☐ sim ☐ não

**8. Trocar de app.** Abra outro aplicativo por 30 segundos e volte.

Mesma pergunta: apareceu o aviso?  ☐ sim ☐ não

**9. Encerrar.** Toque em **Encerrar**.

A corrida apareceu na lista?  ☐ sim ☐ não
Distância na lista: `_____ m` · Tempo: `_____ s`
Marcou "com trecho não registrado"?  ☐ sim ☐ não

**10. Persistência.** Feche o app inteiro e abra de novo em
`/treino/corridas/`.

A corrida continua lá com os mesmos números?  ☐ sim ☐ não

**Bateria no fim:** `____%` — em `____` minutos de corrida.

---

## Como eu leio o resultado

**A promoção de Corrida para a quinta aba depende de três coisas juntas:**

1. o número do item 4 bater com a distância real dentro de uns 10%;
2. o item 3 continuar em zero parado;
3. os itens 7 e 8 avisarem da lacuna em vez de inventar distância.

Se o item 3 subir, eu ajusto o limite de precisão — e aí o número que você
anotou vira o limite, em vez do palpite que está no código hoje.

Se o item 7 mostrar que a tela apagou mesmo com Wake Lock, isso não é bug meu:
é o navegador soltando a trava, e a resposta é a interface avisar melhor, não
prometer mais.

**Nada aqui promete rastreamento em segundo plano.** Se o item 7 der "a
corrida parou", está correto — é o limite da plataforma, e a tela já diz isso
antes de começar.
