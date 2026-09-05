# Prova de campo: a Corrida no app Android

**Por que só você pode fazer:** o requisito é o GPS continuar registrando com a
**tela bloqueada e o telefone no bolso**. Isso depende do sistema operacional,
do modo de economia de bateria do fabricante e do estado real de energia do
aparelho. Nenhuma dessas coisas existe aqui, e emulador não prova nenhuma
delas.

Este roteiro é do **app Android**. O de [`prova-corrida-aparelho.md`](prova-corrida-aparelho.md)
é da PWA e continua valendo para ela — a PWA **não** consegue passar no item 4
abaixo, e não deve ser cobrada por isso.

**Tempo:** 15 a 20 minutos, com uma caminhada de pelo menos 10.

**Onde:** rua aberta. Dentro de casa o GPS erra de propósito.

**Não anote nenhuma coordenada.** Nenhum item precisa delas.

---

## Antes de sair

Preencha:

- Aparelho: `_______________`
- Android versão: `_______________`
- Fabricante tem economia de bateria agressiva (Xiaomi, Samsung, Oppo…)? `____`
- Bateria no início: `____%`

Instale o APK e abra o app. **Entre com sua conta** (é a mesma do site).

Na seção **Diagnóstico**, confirme antes de sair:

- **Geolocalização:** precisa dizer `nativo`. Se disser `navegador`, o plugin
  não carregou e o teste inteiro não vale;
- **Armazenamento:** precisa dizer `nativo`. `navegador` significa que a
  corrida não sobrevive ao app ser morto.

> Se qualquer um dos dois disser `navegador`, **pare**. Não é o teste falhando,
> é o app não estando instalado como deveria — e correr 10 minutos para
> descobrir isso depois seria desperdício do seu tempo.

---

## 1. Permissão

Toque em **Iniciar corrida**. O Android vai pedir localização.

- [ ] Escolhi **"Durante o uso do app"** (e NÃO "o tempo todo")

Isto é parte da prova: o app foi desenhado para funcionar **sem** a permissão
de segundo plano. Se ele só funcionar com "o tempo todo", a arquitetura está
errada e eu preciso saber.

- [ ] Apareceu uma **notificação persistente** dizendo que a corrida está em
      andamento

Essa notificação não é enfeite: é a contrapartida que o Android exige para
continuar entregando posição com a tela apagada.

---

## 2. Com a tela ligada

Ande 1 ou 2 minutos olhando a tela.

- [ ] A distância cresce
- [ ] "Pontos" cresce (mais ou menos 1 por segundo)
- [ ] "Maior intervalo" fica **abaixo de 5 s**

---

## 3. O TESTE QUE IMPORTA — tela bloqueada

- [ ] Bloqueei a tela
- [ ] Guardei o telefone no bolso
- [ ] Caminhei/corri **pelo menos 10 minutos** sem tocar no aparelho
- [ ] (Opcional, e vale a pena) Coloquei música tocando em outro app

Anote a hora em que bloqueou: `____:____`

---

## 4. Ao voltar

Desbloqueie e abra o app.

- [ ] **Maior intervalo:** `______ s`

**Este é o número da prova.** Se ficar abaixo de ~30 s, o GPS continuou
registrando com a tela bloqueada. Se aparecer um buraco de vários minutos, o
sistema suspendeu o app — e aí o resultado é NEGATIVO, o que é uma resposta
legítima e útil.

- [ ] Pontos registrados: `______`
- [ ] Distância provisória: `______ km`
- [ ] A distância bate com o que você caminhou? `____`

---

## 5. Encerrar e sincronizar

Toque em **Encerrar e sincronizar**.

- [ ] O estado mudou para "Sincronizada"
- [ ] O log mostra `oficial do servidor: ____ m`

A distância **mudou** entre o provisório e o oficial? `____`

Mudar é **esperado e correto**: o servidor descarta leituras de precisão ruim
que o aparelho mostrou. O que seria errado é o número não mudar nunca — isso
sugeriria que o servidor não está recalculando.

---

## 6. Idempotência na rua

- [ ] Liguei o **modo avião**
- [ ] Iniciei outra corrida curta (2 minutos), andei, e encerrei
- [ ] O app disse "Guardada no aparelho" em vez de "Sincronizada"
- [ ] Desliguei o modo avião, fechei e reabri o app
- [ ] A corrida guardada aparece e consigo sincronizá-la

---

## 7. Recuperação depois de o app morrer

O caso real: o Android mata o app durante uma corrida longa.

- [ ] Iniciei uma corrida
- [ ] Andei 1 minuto
- [ ] **Forcei a parada** do app (Configurações → Apps → NutriPlan → Forçar
      parada)
- [ ] Reabri o app

- [ ] Ele disse "Havia uma corrida interrompida com ____ pontos"
- [ ] Consegui encerrar e sincronizar o que tinha sido registrado

O app **não** volta a rastrear sozinho, e isso é decisão: o rastreio morreu com
o processo, e retomar em silêncio deixaria um buraco no meio que ninguém
saberia explicar.

---

## Depois

Bateria no fim: `____%` — e quanto tempo de corrida: `______`

Me diga o resultado dos itens **3, 4 e 7**. Os três juntos são o que decide se
a fundação funciona; o resto é detalhe que eu conserto sozinho.
