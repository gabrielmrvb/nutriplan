# NutriPlan — como este projeto funciona

PWA de dieta e treino em Django 5.2 + PostgreSQL. Uma pessoa, um plano, sem
conta compartilhada. Em produção: https://nutriplan-xxfn.onrender.com

## Trabalho em missão

Campanha, fase, bloco ou lote que termina em publicação: leia a skill
**`nutriplan-missao`** antes de editar. Ela traz o ciclo (planning →
decomposição → subagentes → integração → testes → browser QA → sabotagem →
suíte → deploy → smoke), quando avançar sozinho, e as condições exatas de
parada humana.

As outras quatro continuam valendo para o que decidem: `nutriplan-product`
(vale construir?), `nutriplan-architecture` (onde a regra mora?),
`nutriplan-ux` (como a tela funciona?) e `nutriplan-qa` (como provar?).

Pergunta pontual e ajuste de uma linha **não** precisam de protocolo.

## Rodar

```bash
.venv/Scripts/python.exe manage.py test          # suíte completa (~20 min)
bash scripts/instalar_hooks.sh                   # liga as travas de git
```

O PostgreSQL é portátil (`C:\Users\biel-\pgsql`, cluster em
`C:\Users\biel-\pgdata\nutriplan`) e **não sobe sozinho depois de reiniciar** —
`pg_ctl start` antes de qualquer coisa.

## Apps

| app | o que guarda |
|---|---|
| `accounts` | usuário, perfil, peso, dias de treino, `SyncedOperation` |
| `catalog` | alimentos e receitas (TACO/IBGE/USDA) |
| `plans` | motor nutricional, cardápio, hidratação, ofensiva, voz |
| `workouts` | ficha, cargas, catálogo de exercícios, exportação de saúde |
| `supplements` | catálogo e checklist |
| `push` | service worker, manifesto, notificações |

## Decisões que já foram tomadas — não refaça sem motivo

**Sem framework de CSS.** Um arquivo, `static/css/app.css`, lido de ponta a
ponta, com seções numeradas. Tokens no topo. Nada de Tailwind, nada de build
step.

**`:has()` é proibido** para CSS estrutural. Já derrubou a navegação uma vez: o
navegador descarta a regra inteira quando não suporta, e o convite de instalação
cobriu a barra de abas. Use classe escrita pelo servidor.

**Alvo de toque: 44px de altura E de largura.** A régua mede as duas — 26px de
largura com 44 de altura já passou despercebido uma vez. Texto de interface
nunca abaixo de 11px.

**Número é `tabular-nums` e vírgula decimal.** O app é pt-BR: "62,50", não
"62.50". Passe por `floatformat` ou `number_format`.

**Nada rola na horizontal.** Todo container de texto leva `min-width: 0`.

**A ficha da semana desenha vários dias; o histórico só sabe de um.**
`load_history` devolve um balde `"hoje"` que é de HOJE. A tela da ficha aplicava
esse balde a TODAS as sessões, e um exercício anotado hoje aparecia como
concluído dentro do card de sexta, com as cargas preenchidas nas séries de lá.
`ExerciseLog` sempre teve a data certa — era a LEITURA que perdia o dia. Ao
mexer nessa tela, lembre: `"anterior"` vale para todos os dias (é o que se
consulta ao abrir outra ficha), `"hoje"` vale só para a sessão de hoje.

**O NutriPlan tem CINCO PILARES, e "Hoje" não é um deles.** Alimentação,
Treino, Corrida, Hidratação e Progresso estão no mesmo nível conceitual —
`accounts.models.Pilar`. Hoje é o orquestrador do dia; Perfil é utilitário. A
navegação DIZIA o contrário: a tela de água acendia a aba "Dieta" e a de
corridas acendia "Treino". Hoje `nav` tem `hydration` e `running`, e nessas
telas NENHUMA aba acende — melhor que acender a errada. Quem orienta é o mapa.

**Uma área, um nome — e o nome mora em `Pilar.label`.** O padrão oficial é
**Alimentação · Treino · Corrida · Hidratação · Progresso**. O produto já teve
TRÊS vocabulários: a barra dizia "Dieta/Treino/Progresso", o mapa e o
onboarding diziam "Alimentação/Musculação/Evolução", e a documentação chamava o
quinto de "Progresso" — com os dois primeiros visíveis AO MESMO TEMPO no
celular. `DETALHES` não escreve mais o nome: ele lê o label, e guarda só o que
o modelo não tem (ícone e frase de apoio). `config/test_nomenclatura.py` compara barra e
mapa POR DESTINO — e onboarding, Perfil e gestão por presença dentro do recorte
da seção, que é mais fraco e está dito aqui para ninguém confiar demais. A capa
do demo escreve os cinco nomes à mão em `demo/views.py` e **não tem teste**;
renomear um pilar deixa ela para trás em silêncio.

O `value` **não** acompanhou o rótulo, e a separação é a prova de que os dois
planos são independentes: `Pilar.DIETA` continua valendo `"dieta"` enquanto a
tela diz "Alimentação". O valor está em banco, no `CheckConstraint`, nas chaves
de `CAMPO_DO_PILAR` e no `name` do formulário — renomear a tela não migra dado
nenhum, e a `0025` é no-op no PostgreSQL.

E a régua protege NOME DE PRODUTO, não palavra: "dieta", "musculação" e
"evolução" continuam livres em texto educativo. Um teste que varresse a página
atrás delas transformaria padronização em censura de vocabulário — o app diz
"sua dieta calculada" na descrição e "não é prescrição" no texto da água.

**A barra de baixo responde FREQUÊNCIA; o mapa responde ESTRUTURA.** São
perguntas diferentes, e por isso não competem pelo mesmo espaço. A barra tem
QUATRO itens e a conta é medida: a 320px, cinco colunas deixam 51,8px úteis por
item e "Hidratação" precisa de 60. O mapa
(`templates/partials/mapa_de_areas.html`, um `<details>` na barra de cima) lista
os cinco pilares, marca a área da vez com `aria-current` e põe um selo na área
principal da pessoa. Ele **não** reordena por pessoa: um mapa que muda de ordem
é um mapa pior, porque existe para mostrar de que o app é feito — e isso é igual
para todo mundo.

Três ausências no mapa são decisão, e as três foram achadas por revisão
adversarial ANTES de virarem defeito em produção:

- **não tem ícone**: o sprite dos cinco desenhos (`partials/icones.html`, 4 KB)
  só é incluído no onboarding, e copiar os desenhos é o que o sprite existe para
  impedir;
- **não entra no shell de offline**: aquela tela é pré-cacheada e servida a quem
  pegar o aparelho depois, e o selo de área principal é identidade — o mesmo
  motivo de `data-usuario` sair de lá. Duas camadas: o `{% if %}` no `base.html`
  e a tag se recusando a ler o perfil;
- **não aparece no onboarding**: a barra de baixo já é desligada lá porque os
  destinos devolvem quem não terminou, e o mapa reintroduzia os mesmos — sendo
  que `workouts:corridas` tem só `LoginRequiredMixin` e era saída DE VERDADE no
  meio do cadastro. O mesmo `sem_tabbar` desliga os dois.

E o endereço sai de `{% url %}` passando por `_endereco()`, que traduz a raiz do
demo: `plans:today` mora em `path("")`, então sob `set_script_prefix("/demo/")`
ele reverte para `/demo/` — que **não** é a tela Hoje, é a capa. O mapa mandava
quem estava avaliando o produto para a página de marketing e ainda anunciava
"você está aqui" ao fazê-lo.

**A Home organiza pela área principal, e o AGORA continua sendo o primeiro
bloco.** A prioridade declarada move UMA seção para o alto da tela de Hoje,
logo abaixo do resumo do dia — e nunca acima do cartão AGORA. Urgência vence
preferência: refeição vencida e treino em andamento têm hora marcada, e a hora
passa; a área preferida continua verdadeira amanhã.

Hidratação é a única que tem para onde subir — as refeições já são a primeira
seção de área. Ela sobe por `{% include "plans/_agua.html" %}`, com DOIS pontos
de chamada e um `{% if %}` em cada: o markup existe uma vez e a página emite uma
vez. Copiar o bloco quebraria de dois jeitos concretos — `id="hidratacao"` é
âncora de link e viraria ambíguo, e a página passaria a ter dois formulários de
registro com os mesmos nomes. **Não é `order` do flexbox**: `.split__main` é
flex, e `order` moveria o cartão na pintura deixando a ordem de leitura e de
foco onde estavam (WCAG 1.3.2 e 2.4.3).

Treino, Corrida e Progresso não têm seção própria na Home — não porque já
estejam no topo, mas porque a tela nunca falou deles. Os três ganham
`plans/_area_promovida.html`, um cartão com um fato real do dia e a porta para a
área. Treino sai de `estado_do_treino`, que a Home já calcula; Corrida e
Progresso custam UMA consulta cada, e só para quem declarou aquela área.

**Quem não declarou nada vê a Home de antes da campanha** — sem selo, sem cartão
de área, na ordem canônica. E ela não infere área de histórico, peso, treino,
água ou frequência: há teste com uma pessoa de histórico cheio provando que ela
continua neutra.

**Declarar interesse numa área nunca pode PIORAR aquela área.** `limiar_de_atraso`
lia só a prioridade, então quem marcava [Alimentação, Hidratação] e elegia
Alimentação recebia 35pp — mais tarde que quem não declarou nada, que recebe 25.
Declarar interesse em hidratação atrasava o aviso de hidratação. Hoje quem marcou
a área sem elegê-la principal fica no valor neutro, e há teste varrendo os cinco
pilares com essa propriedade.

**Interesse ORGANIZA; ele não restringe.** Quem marcou só Corrida continua com
as outras quatro áreas abertas, e há teste varrendo as cinco rotas. Esconder o
que não foi marcado é a simplificação tentadora que transformaria a
personalização em prisão.

**A prioridade é uma pergunta PRÓPRIA, não o primeiro checkbox tocado.** Marcar
várias áreas sem escolher a principal devolve a pergunta explícita; marcar a
principal sem marcar a área acima MARCA a área, porque cobrar essa coerência do
dedo seria devolver à pessoa um erro que o formulário fecha sozinho. Uma área
só dispensa a pergunta.

**A prioridade tem de pertencer aos interesses, e quem garante é o banco.**
`prioridade_pertence_aos_interesses` é o primeiro `CheckConstraint` do
repositório. O padrão até aqui era `UniqueConstraint`, que não expressa
"pertence a" — e a doutrina de `um_primeiro_admin_por_pessoa` já dizia por que
Python não basta: duas transações simultâneas atravessam juntas uma checagem.

**Preferência ≠ urgência contextual.** O pilar entra em `plans/agora.py` como
MAIS UM SINAL: ele move o limiar da regra de hidratação dentro de uma faixa
fechada de 15 a 35 pontos, e abre um ramo para Progresso **só quando
`convidar_a_pesar` já disse que há uma pesagem faltando**. Ele nunca passa na
frente de treino em andamento nem de refeição vencida — aquilo tem hora marcada
e a hora passa; o pilar continua verdadeiro amanhã. E nenhum pilar DESLIGA a
água: o teto de 35 existe para isso.

**Uso não é intenção declarada.** A migration `0024` não infere preferência de
ninguém. Quem já usava o app fica com `prioridade == ""`, que é um estado de
verdade — "ainda não respondeu" — e não um buraco. É o mesmo raciocínio que
`split_preference_confirmada` pagou caro para aprender. O `RunPython` que
existe ali só preserva o `onboarding_step` de quem já tinha terminado, porque o
passo novo moveu `ONBOARDING_DONE` de 6 para 7.

**O onboarding tem TRÊS etapas, e `ONBOARDING_DONE` continua 7.** Eram seis
passos (`/conta/onboarding/1/` a `/6/`, "Passo 1/6 · 16%", CTA "Salvar"), e
sete perguntas passavam antes de qualquer consequência. Desde 15/09/2026 são
três rotas reais — Sobre você · Seu objetivo e rotina · Sua personalização —,
e a tela só diz "Etapa N de 3". `ONBOARDING_LAST_STEP` é 3; o 7 de DONE
ficou de propósito, porque é o valor gravado em toda conta concluída e mudá-lo
custaria uma migration de dado para trocar um número por outro. A `0032` faz o
único remapeamento que importa: quem estava no meio (2-6) cai na etapa que
contém o passo antigo.

As etapas 2 e 3 são formulários COMPOSTOS (`EtapaCompostaView`): os cinco
`ModelForm` antigos continuam existindo com a validação e o `save()` de cada
um — e é isso que faz três etapas sem reescrever regra nenhuma. Duas coisas
custaram caro ali: **os formulários compostos compartilham UMA instância de
`Profile`** (com instâncias separadas, o último `save()` sobrescrevia o
objetivo gravado pelo primeiro — a etapa 3 mostrava "Emagrecer" sumido), e a
ordem dos saves é objetivo → divisão → rotina, porque `TrainingForm.save()`
relê o perfil. A divisão é PROGRESSIVA: aparece a partir de
`MINIMO_DE_DIAS_PARA_DIVISAO` dias marcados (a régua é
`preferencia_muda_a_divisao`, a mesma do antigo passo 4), e sem JavaScript o
servidor reabre a tela com o bloco visível e o erro no campo.

**"Criar meu plano" monta os DOIS planos e devolve JSON quando é XHR.** A
tela de montagem envia o último POST por `fetch` e SEGUE o redirect — o que
consumia a mensagem "Seu plano está pronto" antes de a Home ser aberta pelo
navegador. Com `X-Requested-With` o servidor responde `{"destino": url}` e o
JavaScript navega; sem JavaScript continua sendo o 302 de sempre.

**Plano é retrato, não referência.** `NutritionPlan` e `TrainingPlan` guardam os
números do dia em que foram criados. Mudou a entrada, nasce plano novo — os
antigos ficam. Nunca edite os números de um plano ativo: `plan_is_current()`
compara com o que o motor calcula hoje e descarta o que não bate.

**Ficha ajustada não é remontada.** `TrainingPlan.customized_at` desliga o
gerador. Sem isso, mudar o horário de terça apaga a troca de ontem.

**Ficha que o CATÁLOGO deixou para trás também não é remontada — a Home
pergunta (17/09/2026).** O painel remontava a ficha na entrada sempre que a
prescrição do catálogo divergia da gravada; o deploy que ativou 28
exercícios trocaria a ficha de todo mundo no meio da semana, sem ninguém
pedir. Hoje `sync_active_routine` só remonta a ficha INVÁLIDA
(`rotina_invalida`: sem sessão, exercício aposentado, divisão que não
corresponde à frequência, dias/horários diferentes — e nível ou faixa de
duração diferentes dos que a ficha guarda, porque aí foi a pessoa que mexeu
na própria entrada). Prescrição diferente é `rotina_desatualizada`, e a
resposta é um aviso único e dispensável na Home, depois do AGORA: "Seu
treino pode ficar mais completo — regenerar?". Regenerar é `POST
/treino/regenerar/`; "Agora não" grava `aviso_dispensado_em` NO PLANO, não
no navegador. O plano virou retrato também das ENTRADAS (`catalogo`,
`nivel`, `duracao`): `catalogo` é a impressão digital de `exercises.json` +
`splits.json` + `TREINO.md` (`versao_do_catalogo`), e com ela igual à de
hoje a Home responde "nada mudou" com ZERO consultas — a conferência exata
(represcrever a semana, onze consultas) só roda para ficha nascida de outro
catálogo ou de antes da migration `0023`, que ficou com os três em branco.
Em branco é desconhecido, e desconhecido não invalida nada. O demo é
fixture de que o seed é dono: `seed_demo` regenera sozinho quando a
prescrição mudou.

**O CICLO DA DIVISÃO RODA CONTÍNUO, e a letra de hoje sai da POSIÇÃO, não
do dia da semana (17/09/2026).** Em 5 dias com ABC o ciclo fixo A B C A B
recomeçava toda segunda, peito e costas caíam 2× e "Pernas e ombros" 1× —
quadríceps em 7 diretas por semana, para sempre. O desequilíbrio era do
calendário. Hoje a semana seguinte continua de onde a anterior parou (C A B
C A, depois B C A B C; em 3 semanas cada letra cai 5 vezes), e a média do
ciclo está medida no `TREINO.md`. Como funciona: `TrainingPlan.
inicio_do_ciclo` é a posição zero (o primeiro dia de treino da semana em que
o plano nasce — a primeira semana é a de sempre, a rotação começa na
segunda); as linhas de `sessions` continuam UMA POR DIA DA SEMANA, com a
letra da primeira semana — são o retrato de dias, horários e durações que
`rotina_invalida` compara —; `services.sessao_do_dia(plan, dia)` devolve a
linha da LETRA da posição vestindo o dia da semana (`_no_dia`: horário,
duração e `weekday` do dia, `pk` da letra — a escolha e a ficha apontam
para a letra); `sessoes_da_semana` é a semana de hoje que o painel, a ficha
e a leitura desenham. A posição é do CALENDÁRIO: treino pulado conta, como
o quadro da academia. Toda letra recebe o teto e o número de opções da PIOR
semana (`ocorrencias_das_letras`: 2× para A, B e C em 5 dias). Plano de
antes da rotação (`inicio_do_ciclo` em branco) segue preso ao dia da semana,
não é remontado, e a Home pergunta. NUNCA volte a resolver "a sessão de hoje"
por `weekday=hoje.weekday()`: era isso que prendia o ciclo.

**A ofensiva mede aderência AO PLANO, e o denominador vem do plano.** Não do
que a pessoa marcou — essa era a regra antiga, e ela invertia o incentivo do
app: três refeições feitas mais duas marcadas como "comi outra coisa" davam
60% e quebravam a sequência, enquanto três feitas e duas SEM MARCAR NADA davam
100% e a mantinham. Registrar honestamente custava caro; omitir saía de graça.
A propriedade que governa isso agora tem teste próprio em `plans/test_streaks.py`:
**omitir nunca pode produzir resultado melhor que registrar**. Ela vale por
construção, porque qualquer denominador independente da marcação a satisfaz.

**Dois lados abrem o mesmo IndexedDB, e eles têm que concordar.**
`static/js/fila.js` e `templates/pwa/sw.js` abrem `nutriplan-fila`. O service
worker abria sem `onupgradeneeded`; quando ele chegava primeiro — num evento
`sync` —, o navegador criava o banco COM ZERO STORES, e daí em diante toda
gravação offline morria com `NotFoundError`, para sempre, porque a versão nunca
subia. Hoje os dois criam a store e declaram a MESMA versão; `push/tests.py`
compara os dois arquivos. Subir a versão é o que migra quem já tem o banco
quebrado — `deleteDatabase()` "resolveria" o console e jogaria fora a água que
alguém registrou no metrô.

**A fila offline drena na ORDEM DOS TOQUES, e ela não vem de graça.** A chave da
store é `op_id`, que é um `crypto.randomUUID()`, e o `getAll()` do IndexedDB
devolve por ordem de CHAVE — medido em navegador, 51,7% de inversão com duas
operações e 85,7% com três. Como somar, zerar e desfazer não comutam, isso muda
o resultado: `+500 → +500 → desfazer` termina em 500 e, drenado ao contrário, em
1.000. A ordem hoje vem de `seq`, um contador calculado como `maior + 1` DENTRO
da transação de escrita — 60 gravações concorrentes, zero empates, sem lock.
**Não use o `em: Date.now()` para isso**: 199 de 200 chamadas seguidas caem no
mesmo milissegundo, e com empate o `sort` estável devolve a ordem do UUID.
`emOrdemDeToque` e `corpoDoItem` existem IDÊNTICAS nos dois arquivos, e um teste
compara as duas.

**A drenagem PARA no primeiro item que ficou na fila.** Seguir em frente com o
anterior preservado desordena de um jeito que ordenar não conserta e que
sobrevive à drenagem. `fila.js` para seco porque `meus()` já filtrou um dono; o
`sw.js` trava POR DONO, porque drena fila de várias contas e um item estrangeiro
recusado com 503 não pode travar quem está logado — é por isso que
`push/test_replay.py` proíbe `break;` lá.

**A captura guarda PARES, não um objeto, e inclui o botão que enviou.**
`new FormData(form)` não traz o `<button>` do submit: o "Pulei" da refeição
mandava só o token e sumia em silêncio. E objeto colapsa chave repetida: "Comi
outra coisa" ia de três alimentos para um — o vazio, porque o último vence.

**Idempotência tem de cair junto com o efeito.** Este projeto não liga
`ATOMIC_REQUESTS`, então `ja_aplicada` commitava o `op_id` antes da escrita. Uma
falha no meio queimava o identificador sem aplicar nada, e o reenvio era
respondido com "já aplicada" — a fila apagava o item e o registro sumia.
`LogHydrationView.post` é transacional por isso.

**Água soma NO BANCO, não em Python.** `registro.ml = registro.ml + ml` seguido
de `save()` é leitura-modificação-escrita: dois toques rápidos leem o mesmo
valor e o segundo sobrescreve o primeiro. Tocar +250, +500 e +750 em sequência
dava 1000 em vez de 1500. Nenhum debounce no JavaScript conserta — o servidor
precisa estar certo com pedidos concorrentes, e a fila offline reenvia
exatamente assim, em rajada, quando a rede volta. Hoje é
`Least(F("ml") + ml, Value(10000))`, e há teste com threads reais.

**O total do dia e a composição dele são duas tabelas, e uma só é a fonte.**
`HydrationLog` guarda o total — é dele que leem a ofensiva, o histórico e a
tela Hoje. `GoleDeAgua` guarda a COMPOSIÇÃO, e só daqui para frente: não houve
backfill porque inventar de quantos goles os totais antigos foram feitos seria
fabricar dado. A consequência aparece na tela e está escrita nela: no dia da
virada a lista mostra uma linha "sem horário" com a diferença, para a soma
fechar com o painel. As duas escritas andam juntas dentro de `transaction`, nos
três caminhos — somar, desfazer e zerar. **Zerar apaga os goles do dia também**;
quando não apagava, a tela mostrava "Registrado 0 ml" com a lista cheia embaixo,
e "desfazer" continuava oferecido sem mover número nenhum.

**A água sobe no AGORA por ESTADO, não por relógio.** Ela era prioridade 4 —
aparecia depois de todas as refeições e do treino, ou seja, quando o dia já
tinha acabado. Hoje um ramo intermediário mede quanto a pessoa está atrás do
esperado PARA A HORA, e a janela do esperado é a do próprio plano: da primeira
refeição à última. Não há horário escrito à mão, e isso é a decisão — quem come
às 5h30 e às 19h tem outra janela, e um "7h às 22h" fixo estaria errado para
essa pessoa todos os dias. Beber **desliga o cartão na hora** — e só na hora: o
esperado cresce com o relógio mais depressa do que 500 ml movem o real, então
quem continua atrás o vê de novo umas duas horas depois. Medido numa janela de
7h às 20h com meta de 3 L, bebendo 500 toda vez que ele pede: **cinco aparições
no dia**. A primeira versão desta seção afirmava que ceder DESLIGAVA a regra, e
a simulação desmentiu — cadência de duas horas não é o mesmo que aparecer uma
vez. E ela não passa na frente de treino em andamento nem de refeição vencida:
aquilo tem hora marcada; sede não.

**O campo que diz para onde voltar é uma lista fechada.** `LogHydrationView`
aceita POST de qualquer sessão autenticada, e `?next=` livre seria
redirecionamento aberto. O pedido manda o NOME da tela, `DESTINOS` resolve, e o
que não estiver lá cai no destino padrão.

**Idempotência é requisito da fila offline.** Água SOMA e suplemento ALTERNA —
as duas precisam de `op_id`. Marcação de refeição usa `update_or_create` e já é
segura; se alguém a trocar por contador, a fila quebra em silêncio.

**A carga de treino entra na fila offline como EVENTO, e a rota da FICHA
continua fora.** As duas frases são a mesma decisão, e separá-las é o que
resolveu o problema.

Estado é o que não pode ser enfileirado. O formulário da ficha mandava
`series_feitas`, um contador derivado que ela só atualizava no sucesso — offline
ele ficava defasado por um, sempre, por construção e não por corrida. **Nenhum
template emite mais esse campo**: aquele formulário saiu com o cartão da ficha
em 10/09/2026, e há teste varrendo `templates/` para ele não voltar. A rota e o
descarte na drenagem continuam, porque item gravado por versão antiga do app
ainda pode chegar. E o replay
desse corpo não é escrita inofensiva: a view envolve `record_load` num laço mais
um `DELETE ... set_number__gt=N`. Medido em
`workouts/test_carga_fora_da_fila.py`: três séries a 40 kg mais uma quarta a 50
com o contador antigo terminam em TRÊS séries a 50 — a quarta some e o peso das
anteriores é reescrito; com o contador em zero, o dia daquele exercício é
apagado. Aquela rota (`/treino/exercicio/<id>/carga/`) segue fora de `ROTAS` nos
dois lados, e item já gravado por versão antiga é DESCARTADO na drenagem.

Evento é o que pode. `/treino/agora/serie/` manda "fiz mais uma série" e **não
manda número nenhum**: quem decide o `set_number` é o servidor, na hora de
aplicar, procurando o primeiro número livre — a mesma conta que
`_primeira_serie_livre` já fazia na tela online, e igualá-las é o que faz a
sequência offline terminar idêntica à online. Não é `maior + 1`: quem anotou a
série 3 e deixou a 1 em branco recebe a 1 nos dois caminhos.

**A identidade é do TOQUE offline e da PÁGINA online**, e isso é um par, não uma
inconsistência. O HTML renderiza um `op_id` por renderização, e é ele que faz
toque duplo e botão voltar corrigirem em vez de duplicar — era o papel do
`update_or_create` no `set_number`. Offline a página não recarrega entre um
toque e outro, então `fila.js` DESCARTA o `op_id` do formulário e sorteia um por
captura; sem isso os três toques sairiam com o mesmo identificador, o servidor
recusaria os dois últimos como repetição, e a pessoa terminaria o treino com uma
série de três que fez. O descarte precisa acontecer na captura porque
`corpoDoItem` mantém o PRIMEIRO `op_id` que encontra, e o do HTML vem antes.

**Desfazer também é idempotente.** Ele entra na mesma fila, e a fila reenvia
quando a resposta se perde no meio: sem `op_id`, um único toque reproduzido
apagaria DUAS séries — a que a pessoa desfez e a anterior, que ela queria
manter.

**O `IntegrityError` concorrente é retentado, e a medição é o motivo.** Duas
threads leem o mesmo "primeiro número livre" e as duas tentam gravá-lo; o
`UniqueConstraint`, que está certo em existir, derruba a segunda.
`select_for_update` não resolve — com o dia vazio não há linha para travar. Oito
`append_set` simultâneos gravavam CINCO e perdiam três; hoje o serviço aceita a
colisão e tenta de novo com o conjunto de ocupadas RELIDO, e grava oito. O teste que guarda
isso precisa de `threading.Barrier`: sem ela, cada thread paga o handshake da
própria conexão, as oito se escalonam, a corrida nunca acontece e o teste passa
**mesmo sem o retry** — foi o que a sabotagem mostrou.

**O DIA viaja com o evento, e o servidor não confia cego.** A fila drena quando
a rede volta, e isso pode ser noutro dia: quem fecha a última série às 23h50 e
só recupera sinal ao sair da academia via o treino inteiro cair no dia
seguinte — sumia do dia certo e virava sessão fantasma no outro, e
`estado_do_treino`, a ofensiva e o histórico leem por DATA, então os três
passavam a mentir juntos. A tela escreve a data no formulário e ela viaja no
corpo como qualquer campo. O servidor recusa o que não faz sentido: data
ilegível, FUTURA (relógio adiantado escreveria num dia que ainda não existe, e
aquele registro ficaria invisível para toda tela que pergunta "e hoje?") ou mais
velha que sete dias cai em hoje. Sete porque a fila drena na primeira abertura
com rede — mais que isso é aparelho esquecido, e escrever um treino de mês
passado seria pior que descartar a data.

Provado no navegador em 08/09/2026, com a rede desligada pelo CDP: três toques
sem rede não navegam, viram três itens com `op_id` distintos e sem contador no
corpo, e drenam para as séries 2, 3 e 4 com os pesos de cada toque. O `getAll()`
do IndexedDB devolveu os três fora de ordem (2, 3, 1) — é a inversão que o `seq`
existe para consertar, vista ao vivo.

**A dose do catálogo vale POR SESSÃO, e a semana é aparada depois.**
`splits.json` diz quantas séries cada exercício pede numa sessão; repetir a
letra A duas vezes na semana soma o peito duas vezes. A resposta NÃO é reduzir
a dose — quem repete a letra quer a frequência maior. `prescrever_semana` monta
a dose cheia e só então apara: `aparar_volume_semanal` remove ISOLADORES até
nenhum grupo passar do teto semanal de séries efetivas — até 16/09/2026
`TETO_SEMANAL_POR_GRUPO = 20` para todo grupo; desde 17/09 o teto é do NÍVEL
e da FREQUÊNCIA com que o grupo é treinado na semana (`TREINO.md`, tabela B;
`services.tetos_da_semana`) —, e `escolher_para_o_tempo` corta até a sessão
caber no tempo informado. A versão anterior cobrava do exercício principal e
derrubava o supino de quatro séries para duas.

**Série secundária não é série direta**, e é por isso que o teto fala em
efetivas: `volume_efetivo` conta 1,0 para o grupo trabalhado e
`PESO_SECUNDARIO = 0,5` para cada `secondary_muscles`. Um tríceps de supino não
substitui um tríceps de tríceps.

**PRINCIPAL é o composto de MAIOR DOSE de cada grupo, um por grupo por
sessão.** Duas versões anteriores foram medidas e reprovadas: "o primeiro
composto do grupo" rebaixava a remada só por vir depois da puxada; "quatro
séries = principal" tornava intocáveis os DOIS pressões de peito do mesmo dia, e
o peito fechava a semana com 27 efetivas contra o teto de 20 sem nada que o laço
pudesse ceder. E não use `secondary_muscles` como proxy de importância: ele dá
três secundários para "Flexão de braço", que é acessório, e um para
"Leg press 45°", que é principal.

**O aparo tem TRÊS TRAVAS, e as três vieram de medição.** Só sai quem treina o
grupo DIRETAMENTE — senão o laço apagava a prancha para resolver um excesso de
core que vinha de agachamento e stiff; nunca o último exercício direto de um
grupo — senão antebraço saía inteiro da semana; e cede sempre a sessão mais
cheia. Uma primeira versão esvaziou a sexta-feira até dois exercícios e onze
minutos.

**Tempo disponível é TETO, não cota a preencher.** Noventa minutos informados
não obrigam a montar noventa; o perfil de referência (homem, 27, 102 kg, 1,85 m,
segunda a sexta) recebe sessões de 39 a 66 minutos, e isso está certo. Reduzir
um principal a duas séries só é aceitável com razão calculada — nunca para
encaixar o relógio.

**A pergunta do tempo é uma FAIXA, e o topo dela é teto duro.** Era um inteiro,
"Tempo disponível", com a ajuda prometendo que o treino cabia nele — e a
promessa era falsa e estava medida: 30 informados entregavam 32, 45 entregavam
48, 60 entregavam 61. A culpa não era do corte, era da pergunta: o mesmo número
servia de ALVO e de TETO, e `_teto_em_segundos` somava até 5 minutos de folga
para uma sessão não ser rejeitada por trinta segundos. Com faixa, o piso é o
alvo e o topo é o limite — Rápido até 30, Padrão até 60, Completo até 65, e
"sem limite rígido", que é `None` e não corta nada. A folga saiu.
`Profile.duracao_treino` é o dono da resposta; `TrainingDay.duration_min`
continua gravado porque `plans/meal_planner.py` precisa dele, e deixou de ser a
pergunta.

**O RÓTULO SÓ DIZ O TETO — Rápido 30, Padrão 60, Completo 90 — e desde
17/09/2026 a sessão CHEGA lá.** "Padrão — 45 a 60" e "Completo — 60 a 90"
prometiam pisos que o gerador não garantia: medido em 16/09, com teto 60 a
sessão ia de 14 a 59 minutos, e com 90 o treino era IDÊNTICO ao de 65 em 54
combinações, porque a faixa de séries do nível (no máximo 16–20) e o
catálogo de 35 ativos limitavam a sessão antes do relógio. `Completo` valeu
65 por um dia, para o rótulo ser verdade por construção. Com os 63 ativos e a
doutrina do `TREINO.md` ele voltou a 90 (`accounts.0034`, só rótulo), e
"Sem limite rígido" continua "o mesmo que Completo", fora de todo formulário
(`DuracaoTreino.escolhas_visiveis`; segue no `choices` e no banco para quem
já tem). O seletor da ficha diz a faixa CALCULADA da rápida ("~19–24 min"), e
não "até 40". Medido em 17/09 na letra A do intermediário de cinco dias:
Padrão 25 séries em 59 minutos; Completo 27 em 62–63.

**A DOUTRINA DO TREINO MORA EM `docs/briefs/treino/TREINO.md`, e os testes
LEEM o arquivo (17/09/2026).** É o contrato do gerador por nível × tipo de
dia — `um_grupo`, `dois_grupos`, `tres_grupos`, `inferior`, `superior`,
`full` —: exercícios por grupo (grande/pequeno), séries por exercício,
séries diretas por sessão, semanal por frequência do grupo, descanso
(composto 80 s, isolador 60 s) e duração esperada, com Schoenfeld, Helms e
Israetel citados onde o número vem deles. `workouts/doutrina.py` lê as
tabelas do disco uma vez (`lru_cache`) e o mapa "Tipos de dia" diz o tipo de
cada letra de cada modelo; `workouts/test_treino_md.py` reprova o gerador
contra o documento, e `workouts/test_ficha_de_verdade.py` é o TESTE DOURADO
do dono, imutável: intermediário, 5 dias, `abc2`, Padrão → A com ≥ 6
exercícios (≥ 4 peito, ≥ 2 tríceps), 21–28 séries diretas, 55–65 min, nas
DUAS opções; Completo 60–80 min; o mesmo para 4 dias e 3 dias em ABC; os
outros níveis com os valores do `TREINO.md`. Se não passar com o catálogo,
ajusta-se o motor ou pede-se catálogo — nunca se afrouxa o teste. Antes da
missão: 4 exercícios, 13 séries, ~36 minutos.

Cinco decisões da doutrina que custaram medição, e o motivo de cada uma:

- **a faixa de séries é do TIPO DE DIA e do nível, e o preenchimento vai até
  o TOPO dela** (`preencher_ate_a_faixa`): parar no piso deixava "Peito e
  tríceps" em 22 séries e 54 minutos com o catálogo inteiro. O que segura é
  o relógio, o teto semanal e o teto por exercício do nível — e para o
  iniciante (2–3 por exercício) a mesma função DESCE até o topo antes de
  subir: o supino de quatro do catálogo vira três para ele, e "Peito,
  tríceps e ombro" com oito exercícios fecha em 18–20;
- **`tres_grupos` tem o grande em 4 e os pequenos em 2, com a MESMA faixa de
  `dois_grupos`**: o teste dourado vale para "Peito, tríceps e ombro" de 3 e
  4 dias, e três pequenos em 3 dariam dez exercícios e 31 séries antes do
  preenchimento. Os modelos de `abc` foram redesenhados para isso (peito 8,
  tríceps 4, ombro 4; costas 8, bíceps 4, antebraço+trapézio 4; quadríceps
  4, posterior 4, panturrilha 4, core 2);
- **a frequência da tabela B conta o grupo TREINADO — direto ou como
  secundário de composto** (`grupos_treinados`): contando só o anunciado, o
  ombro de "Pernas e ombros" caía uma vez (teto 23) com vinte séries
  efetivas vindas dos supinos e das remadas, e o aparo tirava um dos três
  exercícios de ombro do dia que se chama "Pernas e ombros". A tese da
  tabela — mais sessões, mais recuperação, mais volume — vale para o
  estímulo secundário do mesmo jeito;
- **a margem de secundários do teto efetivo é ABSOLUTA (8 a 2×, 9 a 3×), a
  mesma em todo nível**: o secundário vem do catálogo, não do nível; com a
  margem proporcional (25%) o iniciante a 2× perdia o terceiro peito;
- **o avançado é igual ao intermediário em Completo na sessão de dois
  grupos** (27–28 séries, 62–63 min): sete exercícios a quatro séries são 28,
  o máximo físico da linha; o que separa os níveis hoje é a tabela B (o
  avançado fecha "Costas e bíceps" em 28, o intermediário em 26). Cinco de
  peito para o avançado é dívida de CATÁLOGO, escrita no documento.

A duração da tabela A foi MEDIDA em 17/09 com Completo, todas as letras de
todos os modelos, e não estimada: onde a medição discordou da primeira
versão, a medição venceu, e a lista de ajustes está no documento.

**E a pergunta saiu da TELA em 10/09/2026, sem sair do motor.** Ela pedia uma
calibração que ninguém consegue fazer antes de ver uma ficha — "rápido, padrão,
completo ou sem limite?" é resposta que depende de já conhecer o resultado. O
motor continua processando as QUATRO faixas, e quem já respondeu continua com
o que respondeu; o que mudou é que `duracao_treino == ""` deixou de ser "ainda
não respondeu" e virou "não tem como responder". Um estado que a pessoa não
pode mais mudar precisa de um VALOR, não de um buraco: a migration `0029`
escreve "padrão" (até 60) para quem estava em branco, uma vez, deixando
rastro — em vez de um padrão em tempo de leitura, que mudaria toda consulta
futura sem ninguém ver.

**E voltou para a TELA em 16/09/2026 — na área de Treino, onde a ficha está.**
A avaliação daquele dia (D4) mostrou que "escolha da área de Treino" era
frase sem porta: a ficha oferecia só a "Versão rápida" do dia, "Dados do
cálculo" dizia "até 60 min" fixo, e o Completo de 90 — a ficha inteira —
não tinha onde ser escolhido. Hoje "Seu programa" no painel tem
Rápido · Padrão · Completo com o teto de cada um (`DuracaoDoTreinoView`,
`POST /treino/duracao/`, lista fechada em `escolhas_visiveis`); "Aplicar"
grava `Profile.duracao_treino`, deriva `TrainingDay.duration_min` como
`TrainingForm.save` já fazia, e `sync_active_routine` remonta — faixa
diferente da que a ficha guarda é `rotina_invalida`. As travas continuam e a
tela diz qual valeu: série registrada hoje, a ficha muda amanhã; ficha
ajustada à mão não é remontada. Medido no intermediário de cinco dias:
Padrão 23–26 séries/~58 min; Completo 26–28 séries/58–68 min.

**O horário do treino é OPCIONAL, e a ausência é um estado de verdade.** Ele
nunca participou da montagem da ficha — `create_routine` jamais leu
`start_time` —, e exigi-lo fazia todo mundo sair do passo 3 com o padrão de
19:00, que a tela então repetia em cada cartão como se fosse a rotina da
pessoa. Sem horário, `_training_end_for` devolve `None` e o cardápio volta a
ser distribuído pela janela de sono: o mesmo caminho de quem não cadastrou dia
de treino. O que não se faz é inventar um padrão para completar a conta.

**Em 10/09/2026 ele saiu da INTERFACE inteira** — do passo 3 e do Perfil —,
porque exibir um valor que não participa de nada e não dá para editar faz
procurar o botão que não existe. **O dado permanece no banco**: `save()` relê
os horários gravados e os devolve no `update_or_create`, senão `start_time=None`
nos defaults apagaria em silêncio o que o cardápio de quem já usa o app lê. Há
teste postando `start_time=06:30` num formulário que não tem o campo e provando
que o 19:00 gravado sobrevive.

**A experiência move o TETO SEMANAL POR GRUPO e a dose por exercício, e não
a lista.** `Profile.experiencia` valia 12, 20 ou 24 séries efetivas até
16/09/2026; desde 17/09 `TETO_POR_EXPERIENCIA` vem da tabela B do `TREINO.md`
para o grupo que cai UMA vez (15, 23, 28), e o grupo que cai duas ou três
vezes tem teto maior (`tetos_da_semana`). Vazio, que é "ainda não respondeu",
vale intermediário. Ninguém tem a ficha reescrita por uma pergunta nova, e a
tela não afirma um nível que a pessoa não declarou. Ela não mexe em QUAIS
exercícios entram: rebaixar o agachamento por ser "complexo demais para
iniciante" seria o app tirar sozinho o movimento que mais interessa a quem
está começando — o iniciante faz os mesmos movimentos com 2 a 3 séries.

E **o teto semanal é de APARO, não promessa** — vale para os três níveis e para
o 20 de sempre. `aparar_volume_semanal` só remove isolador que treina o grupo
diretamente, e nunca o último deles, então excesso que vem de secundário de
composto principal fica onde está: medido, o ombro fecha em 14,5 com o teto em
12, porque baixá-lo exigiria derrubar o supino. O que o número move de verdade
é o volume da SEMANA — 65 séries contra 88, no perfil de quatro dias. Quem
tratar o teto como garantia vai "consertar" as travas e esvaziar um treino.

**O catálogo cobre o contrato de variedade, e `abc B` foi o último buraco.**
Quatro peitos, quatro costas, três tríceps e três bíceps por semana é o que o
produto pede para o intermediário de 45 a 60 minutos. O modelo `abc B` listava
TRÊS dorsais com quatro no catálogo; `Barra fixa assistida` entrou em
10/09/2026, com a mesma dose que já abre `abcd B` e `abcde B`.
`Remada curvada com barra` continua aposentada e não volta por essa porta.

**Personalização por LOCAL e EQUIPAMENTO está bloqueada pelo CATÁLOGO, não por
escopo — e a medição de 10/09/2026 diz exatamente quanto falta.**

O erro de leitura a evitar é achar que basta filtrar. A prescrição não SELECIONA
exercícios: `prescrever_semana` copia MODELOS curados de `splits.json`, com os
nomes escritos. Filtrar por equipamento não troca de exercício — abre BURACO no
modelo. Medido nos 15 modelos: em "casa + halteres" oito perdem grupo sem
substituto e `abcde-C` termina com ZERO exercícios; em "peso corporal" são treze
modelos e sete zerados.

**Varridos os 31 recortes possíveis de equipamento, UM era viável em 10/09: o
conjunto completo** — ou seja, nenhuma restrição, que é o comportamento de
hoje. A causa era estrutural, três monopólios: **core** 3 de 3 em peso do
corpo, **antebraço** 2 de 2 em barra, **panturrilha** 2 de 2 em máquina. Com
os 63 ativos de 17/09/2026 sobrou o core, e **casa + halteres virou PARCIAL**:
nenhum grupo sem substituto, nenhuma sessão abaixo do piso, e três grupos
sem folga (panturrilha, posterior, trapézio).

O que destrava, medido: **casa + halteres precisava de DEZ exercícios em
10/09, e precisa de TRÊS desde 17/09** — e não de "três" no sentido de
10/09. Aquele três era a conta da COBERTURA — todo grupo com pelo menos uma
opção —, e ela engana: com exatamente três, sete dos onze grupos ficariam
com UM exercício, a semana cairia de 26-29 movimentos distintos para 13-14
com o mesmo número de séries, e o teto por experiência pararia de funcionar,
porque `aparar_volume_semanal` nunca remove o último exercício direto de um
grupo. O piso real é a FOLGA (duas opções por grupo usado): eram dez, e
quatro variantes com halteres entraram com foto conferida (stiff,
panturrilha em pé, rosca de punho, agachamento goblet) — faltam a
panturrilha sentado, a elevação pélvica e a remada alta com halteres, com
mídia curada. A tabela está no `BACKLOG.md`; a régua, em
`workouts/test_capacidade_de_ambiente.py`.

**EXERCÍCIO ATIVO TEM DEMONSTRAÇÃO, e são quatro contratos com nove guardas.**
`video_url` embutível, `clip_kind` não vazio, `tem_anatomia` verdadeiro e
presença em `media_map.json`. Isso não é burocracia: foi o que bloqueou a
expansão de Casa + Halteres em 10/09/2026. Nove variantes com halteres foram
cadastradas, mediram bem — sete grupos sem folga viraram um, variedade de 13-14
para 18-19 movimentos por semana — e voltaram atrás, porque escolher vídeo exige
assistir e este ambiente não assiste. Quatro delas entraram em 17/09/2026 pela
porta certa — foto conferida pelo dono num mosaico de veto, licença
registrada em `curadoria` no `exercises.json` —, junto com outros 24; o veto
é `manage.py desativar_exercicio <nome>` (reversível com `--reativar`), e
ele desativa no JSON e no banco. O que falta para os cinco restantes é
curadoria de MÍDIA, não decidir o que cadastrar.

**COBERTURA NÃO É QUALIDADE**, e a régua cobra as duas. Como efeito colateral, o
catálogo virou contrato: aposentar um dos dois exercícios de panturrilha derruba
o veredito da própria academia, porque o grupo fica com opção única — e a suíte
diz qual capacidade se perdeu.

E NÃO EXISTE CAMPO DE AMBIENTE NO PERFIL, de propósito. Guardar a preferência
antes de o motor poder obedecê-la é criar preferência que não vira nada — o
mesmo defeito de veracidade que `prioridade == ""` evita do outro lado.
`workouts/test_capacidade_de_ambiente.py` guarda as duas metades: o veredito
congelado de cada ambiente, que fica VERMELHO quando o catálogo passar a
sustentar, e a proibição de a tela oferecer a escolha enquanto isso não
acontece.

**`Equipment` é dado de catálogo sem consumidor no motor**, e isso está dito no
próprio modelo. O campo nasceu para o assistente de troca ("a máquina está
ocupada"), que entrou em `7819b30` e saiu em `d86d9c7`; `DISPUTADOS` e
`disputa_equipamento` sobreviveram à remoção como código morto por três
campanhas e saíram em 10/09/2026, junto com dois helpers de teste que chamavam
um módulo `assistant` inexistente. **Não há sistema de substituição de
exercício no app.**

**A área de Treino são TRÊS telas, e cada uma responde UMA pergunta.**

    painel   (`/treino/`)              -> "como é a minha semana"
    ficha    (`/treino/ficha/<id>/`)   -> "o que eu vou fazer hoje"
    execução (`/treino/agora/`)        -> "estou fazendo, e agora"

O painel mostra o treino de hoje e um cartão por sessão, e cada cartão é um
link. Ele NÃO lista exercício: "Começar treino" abre a ficha. A ficha é uma
lista numerada — nome, séries × repetições, músculo e o marcador do movimento
principal —, e cada linha é uma porta para a execução. O selo "Principal" é o
PRIMEIRO composto de cada grupo anunciado da opção
(`services.marcar_quem_abre_o_grupo`, 17/09/2026), não todo composto: com
quatro pressões de peito por opção ele aparecia em cinco de sete linhas. A execução mostra UM
exercício: o vídeo dele, a carga, as repetições, o descanso, o desfazer e a
carga da última vez.

A divisão é por PERGUNTA, e não por tamanho de página — mas o tamanho conta a
mesma história. Medido no perfil de seis dias quando a ficha ganhou rota
própria: 259,1 kB para 72,2 kB, 22 formulários para 1, 141 botões para 8, 266
controles alcançáveis para 30. Medido em 10/09/2026, com as três telas: painel
28,9 kB e zero exercício listado; ficha 8,9 kB (2 exercícios) e 11,7 kB (7);
execução 20,0 kB com DOZE controles alcançáveis.

**Nada que se use DURANTE a série mora na ficha.** Nem vídeo, nem campo de
carga, nem cronômetro, nem histórico detalhado — a ficha é tela de preparação,
para quem ainda não decidiu o que vai fazer. `_exercicio.html`, `_drawer.html`
e `_cronometro.html` saíram do repositório em 10/09/2026 por isso.

A guarda antiga era a RELAÇÃO — botão que abre precisa de gaveta que abre —, e
ela nasceu de um defeito real: quando o cartão mudou para a ficha, a página
ficou com nove botões de vídeo e nenhum `<dialog>`. A relação continua sendo a
régua, satisfeita agora com ZERO dos dois: a ficha não tem botão de vídeo
porque o vídeo mora na execução, onde nasce inline e não precisa de gaveta. O
teste mede as duas pontas.

**A ficha de OUTRO dia não executa.** A execução lê e grava `ExerciseLog` de
HOJE; um link "fazer" na ficha de sexta, numa terça, prometeria registrar série
num treino que não está acontecendo. Fora do dia a linha é `<div>`, não `<a>`.

**Escolher exercício é ESTRITO.** `/treino/agora/?exercicio=<id>` com id
inexistente, ilegível, negativo, repetido, de outra sessão ou de outra conta
responde 404 — e não abre outro exercício. O fallback silencioso (`pedido or
atual`) mascarava link quebrado e podia tocar o vídeo errado, e um link
quebrado que "funciona" nunca é consertado. Sem o parâmetro, a tela continua
abrindo sozinha o próximo pendente. `services.ExercicioForaDaSessao` cobre os
quatro casos num lugar só, porque `estado_do_treino` só enxerga a sessão de
hoje do próprio usuário — e "não está aqui" é a mesma resposta para todos.

**Texto da ficha só afirma o que aconteceu.** Três frases já mentiram, e as três
mentiam por comparar com a coisa errada:

- *"A ficha foi ajustada para caber no tempo que você informou"* aparecia para
  quem respondeu "sem limite rígido". `aviso_de_tempo` media o corte contra o
  MODELO do catálogo e creditava ao relógio o que o teto de volume tinha
  tirado. A régua agora é `prescrever_semana` com `teto=None` — a mesma
  prescrição, sem o relógio —, e a diferença é, por construção, o que o tempo
  cortou;
- *"as duas passagens trazem exercícios diferentes"* valia num caso auditado e
  não como regra: em quatro dias a segunda passagem de A é SUBCONJUNTO da
  primeira, e em sete as três são IDÊNTICAS. O que é sempre verdade é o teto
  semanal, e é isso que a frase diz agora;
- *"85 séries no total"*, ao lado do cartão do treino de hoje, convidava a
  entender 85 séries num dia. É o total da SEMANA, e duas palavras resolveram.

**A letra repetida vira A1 e A2 na TELA, nunca no banco.**
`TrainingSession.label` é a identidade que liga a sessão ao modelo do catálogo;
"A1" gravado ali quebraria `templates_for`, a conferência de prescrição e o
histórico. `nomear_ocorrencias` calcula `rotulo` por OCORRÊNCIA — nunca por
posição na lista —, e leva junto a contagem, porque em sete dias a letra A
aparece três vezes e o template dizia "duas" para todo mundo.

**"2 grupos por dia" é ABC, e o quarto dia não existe.** A preferência
entregava ABCD, cujo quarto dia se chama "Complementares" e é trapézio,
antebraço, panturrilha, glúteo e core — não são dois grupos principais, são o
resto, e quem treinava cinco dias recebia A-B-C-D-A com o dia D no meio da
semana. Hoje ela pede TRÊS dias e produz `Split.ABC2`: peito e tríceps, costas
e bíceps, pernas e ombros, repetindo a partir do quarto dia (A-B-C-A,
A-B-C-A-B, A-B-C-A-B-C, A-B-C-A-B-C-A).

Os complementares não sumiram — foram para dentro de B e de C, e é
`repartir_ocorrencia` que os distribui: B1 leva o encolhimento, B2 leva a remada
alta; C1 leva a panturrilha em pé, C2 a sentada. **A objeção de que integrar os
complementares obrigaria sessões de onze exercícios está medida e é falsa**:
`abc2 B` tem onze itens e `abc2 C` tem doze, e a maior sessão da semana tem
SETE no tempo padrão e QUATRO no rápido. Doze só chega a quem escolheu
"Completo" ou "sem limite rígido", em 88 minutos contra um teto de 90 — ali a
pessoa pediu a ficha inteira.

**UMA LETRA, ATÉ DUAS OPÇÕES — e "A1/A2" deixaram de ser dias obrigatórios
(15/09/2026).** Medido em produção: intermediário, cinco dias, dois grupos
por dia recebia A1 com 4 exercícios/13 séries/~36 min e A2 com 4/13/~29 — a
mesma letra com conteúdos diferentes em dias diferentes, cada sessão curta, e
o nome dizendo "dois treinos". `repartir_ocorrencia` já repartia o modelo
entre as passagens; o que faltava era tratar as metades como VERSÕES da
mesma letra. Hoje (`workouts/opcoes.py`, `services.prescrever_opcoes`):

- o calendário só diz letras (A · B · C · A · B); a ocorrência de segunda e
  a de quinta carregam EXATAMENTE as mesmas linhas (`SessionExercise.opcao`
  1 e 2); `nomear_ocorrencias` só numera quando os conteúdos diferem de
  verdade — plano antigo ajustado à mão, que continua legível;
- as duas opções são equivalentes por construção: mesmos grupos anunciados,
  volume DIRETO por grupo com diferença ≤ 1 série, duração ≤ 5 min de
  diferença, metade dos exercícios próprios. A régua é o volume direto, e
  não o efetivo: a flexão de braço tem três secundários e desequilibraria
  ombro e core sem ser exercício de ombro;
- o teto semanal vale para o PIOR CASO — cada ocorrência da letra fazendo a
  opção mais pesada no grupo —, nunca para a soma das duas: ninguém faz os
  dois treinos no mesmo dia. `services.volume_da_semana(plan)` é a conta
  oficial; somar `session.exercises.all()` conta um treino que não existe;
- sem catálogo para duas opções distintas, a letra sai com UMA — o modelo
  inteiro, e não a metade que sobrou. É o caso do "Superior" de dois dias;
- **tantas opções quantas ocorrências (mínimo duas)**: com a letra três
  vezes na semana (7 dias em ABC), duas opções de meio modelo dariam, no
  pior caso, 1,5 modelo por semana, e o teto esvaziava as duas até sobrar um
  exercício de peito. Com três opções de um terço, repetir a preferida três
  vezes é exatamente a dose do modelo. Preço medido: a 7 dias o peito fica
  com TRÊS exercícios distintos na semana (o crucifixo compartilhado não
  cabe no teto em nenhuma das três) — o contrato 4/4/3/3 vale de 3 a 6 dias;
- a repartição por grupo COMEÇA PELA OUTRA OPÇÃO a cada grupo, e a
  concessão num exercício compartilhado é ESPELHADA nas irmãs: sem as duas
  regras, uma opção ficava com três compostos e a outra com um (doze minutos
  de diferença) e o teto tirava o crucifixo de uma opção só;
- a faixa de séries por sessão é do NÍVEL e do TIPO DE DIA (`TREINO.md`,
  tabela A: 21–28 para "Peito e tríceps" do intermediário; 14–18 para o
  iniciante), e o preenchimento vai até o topo dela — até 16/09/2026 era só
  do nível (12–15 / 15–18 / 16–20) e parava no piso;
- a pessoa escolhe qual faz (`EscolhaDeTreino`, uma por dia); a recomendada
  é a menos usada recentemente e é um selo, nunca uma obrigação; a
  primeira série grava a escolha; trocar depois da primeira série pede
  confirmação e não apaga nada (`ExerciseLog` é por exercício e data);
- Completo/Rápido é escolha da área de Treino, não do cadastro: a rápida é a
  opção escolhida passando por `escolher_para_o_tempo` a 40 min — não é uma
  terceira ficha, e a linha diz o que ficou de fora.

**TODO EXERCÍCIO TEM `padrao`, E AS OPÇÕES COBREM OS MESMOS PADRÕES
COMPOSTOS (16/09/2026).** `Padrao` são 22 valores de um nível só — ângulo e
pegada ficam no nome (reto e inclinado são a mesma `pressao_de_peito`;
lateral e frontal a mesma `elevacao`); se um dia precisar distinguir, é um
campo `variante`, não um padrão novo. `PADROES_COMPOSTOS` (oito) marca os
compostos, e `is_compound` tem de concordar com ele (há teste).
`equipment` já existia com os cinco valores e foi REUSADO, não duplicado.
O banco recusa exercício sem padrão ou sem equipamento (`CheckConstraint`),
e a `0022` preencheu os 36 pelo nome.

A régua nova de `equivalentes`: em cada grupo ANUNCIADO, as opções cobrem
os MESMOS padrões compostos; isolador pode diferir. Três supinos contra três
crucifixos passavam nas réguas de volume e de minutos — e treze das
dezesseis letras com duas opções eram assim (crucifixo numa, mergulho na
outra; stiff numa, mesa flexora na outra). Para a régua ser satisfazível,
`montar_opcoes` reparte o grupo anunciado por bloco de padrão composto
(`_partes_por_padrao`) e COMPARTILHA o padrão composto de exercício único; o
empréstimo do grupo ímpar continua no nível do grupo. Preço com o catálogo
ativo de hoje: **16 letras com duas opções viram 12** — `ab B`, `abcd C`,
`abcd D` e `abcde D` só tinham a segunda por acidente, e voltam quando o
modelo tiver uma segunda extensão de quadril, pressão vertical ou remada
alta ATIVA.

E `aparar_opcoes` cede EM LOCKSTEP, ensaiando numa cópia: a irmã acompanha
pelo volume DIRETO (a régua de equivalência), não pelo efetivo (a régua do
teto) — os dois divergem quando uma opção carrega mais secundário, e a
flexão de braço tem três; a concessão que a irmã não consegue acompanhar
NÃO acontece — o excesso fica, teto de aparo. E com duas opções o
PENÚLTIMO exercício direto de um grupo só sai quando o excesso é GRANDE:
mais de um quinto do teto POR OCORRÊNCIA da letra
(`FRACAO_DE_EXCESSO_QUE_DESTRAVA`), e com a própria letra repetida já
acima do teto no grupo. Sem isso a irmã seguia e a semana ficava com UM
tríceps distinto (abc2, seis dias: corda e testa saíam por um excesso de
uma série); com "nunca" o iniciante (teto 12) fechava a semana com o
mesmo volume do intermediário (73 contra 74) e o nível deixava de valer;
e sem "a própria letra" o ombro de "Pernas e ombros" pagava o secundário
dos pressões de "Peito e tríceps" a seis e sete dias. Consequência
escrita: o volume DIRETO pode ficar UMA série acima do teto (a 7 dias, A
três vezes, peito 21) — `excesso_e_irredutivel`, em `workouts/tests.py`, é
a régua dos testes e diz exatamente quando o excesso é legítimo. O custo
visível: "Pernas e ombros" tem OITO exercícios por opção (o único
desenvolvimento é compartilhado), 24–26 séries em 54–58 minutos, dentro
do teto de 60.

**GATE PERMANENTE, POR LETRA: nenhuma letra que produção tem com duas opções
pode perder a segunda.** `workouts/opcoes_em_producao.py` conta com o MOTOR
e o catálogo ATIVO (uma pessoa transitória por divisão, desfeita ao sair), e
`LETRAS_COM_OPCOES_EM_PRODUCAO` é o CONJUNTO de letras que produção tem com
duas — 16 pares em 16/09/2026, TODAS as 18 desde o deploy de 17/09. Por
letra, e não por contagem (17/09): `abcd C` perdendo a segunda enquanto
`full A` ganha uma dá "16 = 16" e é regressão para quem treina quatro dias. O teste em
`workouts/test_catalogo.py` fica VERMELHO enquanto o código local tirar a
segunda opção de qualquer letra do conjunto, e o pre-push roda a suíte: para
subir, ou o catálogo ativado devolve a letra, ou a decisão de reduzir é
tomada em voz alta, tirando a letra do conjunto com a razão escrita. O
conjunto só cresce depois do deploy que provou a letra nova. O relatório de
deploy mostra "antes / depois" por letra: `manage.py opcoes_por_letra` no
commit de produção e no candidato.

**O CATÁLOGO CRESCEU INATIVO ATÉ SUSTENTAR DUAS OPÇÕES CHEIAS (16/09/2026),
E FOI ATIVADO EM 17/09 COM FOTO CONFERIDA.** 28 exercícios novos (64 no
total) entraram com `active: false`, padrão, equipamento, dica,
articulações, secundários, chave CONFERIDA na free-exercise-db (The
Unlicense) e `candidatos` de mídia achados por BUSCA — não por visualização.
No dia seguinte entraram ativos (63; "Remada curvada com barra" continua
aposentada): cada foto conferida — mesma pessoa, mesmo movimento, sem marca
d'água, licença — e registrada em `curadoria` no `exercises.json`, com um
mosaico de veto para o dono. A régua dos modelos é a tabela A do
`TREINO.md`: cada opção é metade do modelo, então o modelo lista o DOBRO da
cota de exercícios por grupo anunciado (`CatalogoDimensionadoTests` cobra
isso com `_cotas` do `test_treino_md`) — peito 8, tríceps 6 em "Peito e
tríceps".

E os modelos também ganharam exercícios que JÁ ERAM ATIVOS onde faltava um
segundo do mesmo padrão composto (elevação pélvica em `ab B`, barra fixa
assistida em `full A`, stiff em `abcd D`...): com isso o gate fechava em 16
sem ativar nada. Medido em 16/09: ativar só "Desenvolvimento na máquina" dá
17 (`abcd C` volta); com os 28 ativos, 18 de 18 — e é o estado de produção
desde 17/09, com as sessões em 55–60 minutos no Padrão.

**O que o catálogo NÃO deixava fazer, medido em 15/09:** "peito e tríceps"
tinha 4 exercícios por opção porque o catálogo tinha 4 peitos e 3 tríceps —
duas opções distintas de 3+3 pediam 6 e 6 —, e com a letra duas vezes na
semana o teto de 20 séries efetivas deixava ~10 por sessão para o tríceps.
Sessões de 13–22 séries e 30–52 minutos eram o número daquele dia; desde
17/09/2026, com 8 peitos e 6 tríceps no modelo e o teto da frequência (40 a
2×), são 7 exercícios por opção, 24–26 séries e 57–60 minutos no Padrão
(`workouts/test_opcoes.py`), e o teste dourado cobra a letra A. A
equilibragem PRIMEIRO DÁ série à opção mais leve e só depois tira da mais
pesada: tirar primeiro deixava as duas com o tríceps em duas séries.

**O modelo declara os grupos que o NOME promete, e o resto é COMPLEMENTAR.**
`WorkoutTemplate.main_groups` é curadoria, não dedução: "grupo com poucos
exercícios" chamaria o ombro de complementar no `abcd C`, que se chama "Pernas e
ombros", e "grupo de isoladores" chamaria o trapézio de complementar no
`abcd D`, que existe para ele. A lista decide três coisas concretas —

- **o EXCEDENTE do complementar cede primeiro** quando falta tempo — a segunda
  panturrilha antes da terceira rosca. Sem essa distinção o corte protegia o que
  ninguém prometeu: medido, "Costas e bíceps" a 60 minutos saía com bíceps=1 e
  trapézio=1, porque bíceps era o grupo mais cheio entre os isoladores e o
  trapézio, com um exercício só, estava travado. Com a regra, o perfil de
  referência — cinco dias, 45 a 60 minutos — fecha a semana com costas=4 e
  bíceps=3. E o ÚLTIMO exercício de um grupo complementar só sai depois de a
  redução de série se esgotar — ver a ordem em cinco camadas, abaixo;
- **o título só nomeia grupo anunciado**, então tirar a panturrilha não torna o
  nome mentira;
- **a ficha separa as duas listas** — "Complementares desta sessão" —, e
  `TrainingSession.main_groups` é cópia congelada do modelo, pela mesma razão
  que `name` e `focus` são: plano é retrato.

**O título é MONTADO, então ele tem de caber na coluna — e a folga não basta.**
`TrainingSession.name` é `varchar(60)`, e o PostgreSQL RECUSA o que não cabe em
vez de truncar: um nome longo não seria feio, seria a montagem da ficha
estourando. Medido sobre todos os subconjuntos dos onze grupos, a pior
combinação possível dá 94 caracteres; a pior combinação REAL do catálogo de
hoje dá 51. Nove de folga é o tipo de margem que a próxima divisão gasta sem
ninguém perceber. `_frase_que_cabe` lê o limite do próprio campo do modelo e,
quando estoura, NOMEIA MENOS e conta o resto — "Quadríceps, peito e mais 4" —,
nunca cortando no meio de uma palavra.

**O título da sessão é escrito DEPOIS da prescrição, e diz só o que ela tem.**
`titulo_honesto` reescreve `name` quando um grupo anunciado não sobreviveu —
"Corpo inteiro" com três exercícios vira "Quadríceps, peito e costas", e
"Costas, bíceps, antebraço e trapézio" sem antebraço vira "Costas, bíceps e
trapézio". Três frases mentiram em produção por causa disso, e uma delas nem era
culpa do relógio: `aparar_volume_semanal` só protege o último exercício do grupo
na SEMANA, então ele pode tirar a rosca inversa de B1 e deixá-la em B2.

**O tempo curto tem UMA ordem de concessão, e ela codifica UMA prioridade:**

    grupos principais e variedade contratada -> movimentos compostos ->
    redução equilibrada de séries -> complementares -> aviso do que não coube

`escolher_para_o_tempo`, em cinco camadas: (1) sai o EXCEDENTE do complementar —
a segunda panturrilha, o segundo abdominal; (2) **reduz série**, do degrau mais
BAIXO para o mais alto, até o piso — três num composto, duas num isolado; (3)
sai o ÚLTIMO exercício de um grupo complementar; (4) sai o excedente do
anunciado, do grupo mais CHEIO; (5) só então um anunciado cai inteiro, e o
título acompanha. E no fim a série VOLTA enquanto couber, na ordem inversa.

**A camada 2 já esteve depois da 4, e a redução já foi sem grau. As duas coisas
eram defeito.** Removendo o excedente anunciado antes de reduzir série, o dia de
puxar perdia dois bíceps para caber o trapézio. Reduzindo por "quem tem mais
série", o primeiro a cair era o composto PRINCIPAL — o agachamento perde série
antes da rosca, porque é ele que tem quatro.

**E a devolução existe porque concessão cobrada sem razão é defeito.** A redução
acontece para caber; se depois dela um exercício sair, o espaço aberto fica
vazio e a ficha paga o preço sem o motivo. Medido: o dia de puxar a 30 minutos
terminava com 24 de 30, com tudo no piso.

**Série reduzida também é ajuste, e o aviso demorou a enxergar isso.**
`aviso_de_tempo` contava EXERCÍCIO removido, que era a única forma de ajuste
até a redução subir na ordem. Passou a existir ficha fortemente encolhida com
zero remoções — três dias com 55 minutos cabem inteiros baixando série —, e a
nota ficava muda enquanto a pessoa via números menores que os do catálogo.

A ordem resolve duas queixas que puxavam para lados opostos: "a ficha de 30
minutos virou agachamento e supino" é a camada 5 sem a reescrita do título, e "o
supino caiu para duas séries num perfil normal" é a camada 3 acontecendo onde a
camada 2 ainda tinha o que ceder. Medido: no perfil de 45 a 60 minutos o supino
mantém quatro séries em todas as divisões.

**A camada 1 já foi "sai o complementar inteiro", e isso também estava errado**
— pelo motivo oposto. Com ela, panturrilha e abdômen ficavam órfãos da SEMANA em
três, quatro e cinco dias: a letra C cai uma vez só nessas frequências, e o que
saía dela não voltava. Eu registrei isso como limitação aritmética e não era.

**O COMPLEMENTAR ÓRFÃO PROCURA VAGA NA SEMANA, e não só na letra dele.**
`realocar_complementares_orfaos` é a terceira coisa que eu tinha dado por
impossível e não era. Medido que o abdômen não cabia no dia de perna como
DÉCIMO exercício, escrevi que ele não cabia na semana — tratando a capacidade
de uma sessão como a capacidade das cinco. A diferença estava à vista: com
quatro dias, `A2` fecha em 24 minutos de 60, trinta e seis ociosos ao lado de
uma prancha descartada.

Abdômen não pertence ao dia de perna; ele só estava listado ali. O modelo diz
onde o complementar CABE melhor, não onde ele PODE estar. A função procura a
sessão de MAIOR FOLGA, reduz série de isolador e acessório para abrir espaço —
nunca do composto principal, nunca abaixo do piso, nunca acima do teto — e
desiste quando nenhuma sessão comporta.

Ela não mexe no volume da semana **por construção**: o candidato é um item que
já passou por `aparar_volume_semanal` e foi descartado pelo RELÓGIO, então
mudá-lo de sessão preserva o total. E não inventa nada — é o item do catálogo,
com o nome e a dose dele.

Medido no `abc2` a 45 minutos ou mais: **zero grupo órfão de três a sete
dias**. Com três dias a prancha entra em `A1`, com quatro e cinco em `A2`, e a
partir de seis a própria repartição resolve. Em "até 30 minutos" ainda sobra
órfão, e aí — só aí — `aviso_de_tempo` NOMEIA o músculo.

**Consequência que a ficha passou a ter: um exercício pode aparecer numa letra
que não o lista.** A ordem do modelo continua valendo para o que veio do
modelo; o realocado entra no fim, e a tela o mostra em "Complementares desta
sessão" como qualquer outro.

E "mais cheio" conta os exercícios que o grupo tem NA SESSÃO, não quantos deles
estão no degrau que cede. Contando o degrau, o quadríceps — três exercícios,
sendo dois compostos intocáveis — parecia o grupo mais magro da sessão e a ficha
"Pernas e ombros" terminava com UM ombro.

**O contrato de variedade 4/4/3/3 vale de TRÊS dias para cima, e o complementar
NÃO entra às custas dele.** Houve uma versão, em 10/09/2026, que removia dois
exercícios de bíceps do dia de puxar para caber trapézio e antebraço — a semana
fechava com bíceps=1 —, e eu cheguei a escrever um teste que media essa
concessão e a dava por boa. Estava congelando o defeito.

A saída não foi abrir mão do complementar: foi **reduzir SÉRIE em vez de remover
exercício**, e reduzir na ordem certa. Medido no dia de puxar a 60 minutos com
três dias: quatro costas, três bíceps, trapézio e antebraço cabem em 60 exatos,
com as roscas em duas séries e as costas intactas.

**Preferência de divisão que cede, cede EM VOZ ALTA.** `split_for` cruza
preferência com frequência e a frequência manda — quem pede "1 grupo por dia" e
treina quatro vezes recebe ABCD, porque uma divisão maior deixaria parte do
corpo sem treinar nenhuma vez. A regra está certa; o que estava errado era a
tela mostrar ABCD e o Perfil continuar dizendo "1 grupo por dia".
`divisao_explicada` devolve o pedido, o aplicado e o motivo, e a ressalva só
aparece quando os dois divergem.

**A ADAPTAÇÃO DA CARGA É LEITURA, e mora em `workouts/adaptacao.py` — um
módulo PURO com o estado nomeado (T2.1, 17/09/2026).** Ele não abre consulta,
não olha o relógio e não fala com a rede (`workouts/test_adaptacao.py` lê o
texto do módulo e tem controle positivo); recebe o que `load_history` já
carregou — `sessoes` (≤ 10 datas) e `ultimo_registro`, do MESMO laço, sem
consulta a mais — e devolve `Progressao(estado, valor, razao)` com `Estado`
em `SUBIR`/`MANTER` e `MUDA_CARGA = {SUBIR}` dizendo quem muda o número do
campo. É o que permite simular um ano de treino em memória para calibrar
RETOMAR e ESTAGNADO (T2.3) antes de publicar. A regra é a dupla progressão
de 13/09 com UMA correção: fechar a faixa é fechar NA MESMA carga — 60/60/55
com todas as reps no topo era SUBIR para 62,5, e virou MANTER 60, com a frase
dizendo "a série 3 foi a 55 kg". E **frase == campo**: com `Progressao` o
campo abre com `valor` em toda série (antes a terceira abria com 55 — a
mesma série da última vez — enquanto a frase falava de 60). `services.
proxima_carga` é o alias que continua servindo os testes de b14efff.

**Duração tem UMA conta, e ela é `workouts.models.segundos_da_sessao`.**
Existiam duas cópias, uma sobre linhas gravadas e outra sobre tuplas, com um
teste prendendo as duas; prender duas cópias é pior que ter uma.
`DurationMixin.estimated_minutes` e `services._segundos_da_sessao` chamam esta.
A conta é série a série porque o descanso domina, e inclui o que a versão
anterior ignorava: aquecimento geral (300 s), aproximação nos compostos (130 s),
e a troca entre exercícios como o MAIOR entre o descanso e a caminhada — quem
descansa 80 s não troca de aparelho em 45. Nada é contado depois do último
exercício: ali a pessoa vai embora. Medido: 31 séries saíram de 52 para 66
minutos, e os 66 são os verdadeiros.

**Exercício aposentado NUNCA é apagado.** `ExerciseLog.exercise` é `CASCADE`:
`delete()` no `Exercise` levaria junto todo o histórico de carga de quem já o
treinou. Aposentar é `is_active=False` mais a troca nas linhas de prescrição, e
`prescrever_semana` filtra por `is_active` como guarda estrutural. A substituição
é por IDENTIDADE — nome validado, nunca posição na lista.
`Remada curvada com barra` saiu em 09/09/2026 e `Remada baixa na polia` herdou a
dose onde ela já existia.

E o **seed também precisa saber**: `seed_workouts` roda a cada deploy e
ressuscitava o aposentado toda vez, porque `exercises.json` continuava dizendo
que ele valia. A aposentadoria mora nos dois lugares — na migration e no
`"active": false` do catálogo — e há teste rodando o seed DEPOIS da migration.

**"Treino iniciado" é evidência comportamental, não data.** A migration precisa
saber se pode trocar o exercício de um plano, e `TrainingPlan.created_at` não
responde isso: plano criado não é treino começado. A prova é `ExerciseLog` DA
SESSÃO — alguém anotou carga em algum exercício daquele dia depois que o plano
nasceu. Data atual, horário previsto, abertura da página e presença do exercício
no plano não provam nada sozinhos.

**O cartão completo saiu da ficha — e a razão pela qual ele ficou uma vez
continua valendo.** Em 09/09/2026 alguém trocou os outros dias pela linha
compacta de hoje mirando o TAMANHO da página, e aquilo apagou registro de
série, carga, repetições, descanso, progressão e histórico. Vinte e um testes
reprovaram e estavam certos: nada daquilo tinha para onde ir.

Em 10/09/2026 tem. A execução ganhou tela própria com todos os seis recursos, e
aí a ficha pôde virar lista. A diferença entre as duas mudanças não é de
opinião: uma removia o detalhe, a outra o MUDA DE ENDEREÇO, e é por isso que a
segunda passou. Quem for encolher tela neste app, a pergunta é essa —
"para onde vai o que estou tirando?".

**A lista de compras pede o que se COMPRA.** O cardápio calcula em grama de
alimento pronto, e ninguém compra arroz cozido nem meio ovo.
`plans/compra.py` tem três tabelas chaveadas por `Food.name` — `FATOR_CRU` (cozido→cru),
`POR_UNIDADE` (ovo, banana, pão) e `EMBALAGEM` (lata, pacote, litro) — e toda
conversão sai marcada com `~`, porque ela É aproximada. Dúzia só quando divide
exato. E `to_integral_value()` devolve `Decimal`, que imprime
`5.0E+2 g de macarrão`: a humanização passa por `int()`.

**A marcação da lista é ESTADO ABSOLUTO, e a chave é o alimento.** O pedido diz
`marcado=1` ou `marcado=0`, nunca "alterne" — assim ele é idempotente por
construção e dispensa `op_id`, e um reenvio da fila não desfaz o que a pessoa
fez. A chave é `(pessoa, alimento, opção, semana)`: a lista é recalculada a cada
visita e não tem identidade estável; o alimento tem. Marcação de alimento que
saiu do cardápio fica órfã e sem efeito, que é como a troca de plano se invalida
sozinha sem migration destrutiva.

**O JavaScript da página mora em `pwa.js`.** `static/js/app.js` NÃO é servido —
`app_js_url` aponta para `pwa.js`. Código posto lá passa em teste de endpoint e
não roda no navegador; foi assim que a marcação da lista "funcionou" sem salvar
nada. E o ouvinte de mudança é delegado no `document`: pendurá-lo no
`[data-lista-compras]` não pega as caixas, que não são filhas dele.

**`achievements.resumo` não chama `avaliar` — ele desbloqueia SÓ a regra que
chegou a 100 %.** O Progresso mostra um resumo das conquistas, e avaliar as
regras ali levou a tela de 15 para 50 consultas, com crescimento por
histórico — 36 contra 54 medidas. `ConquistasView` já documentava a mesma
decisão. O teto do orçamento subiu de 15 para 26 COM a medição escrita, e a
guarda de N+1 continua estrita: teto só se mexe depois de provar que o custo
é constante. A consequência que essa decisão tinha apareceu em produção em
16/09/2026 (avaliação, B35): "Desbloqueadas 0" com a barra "Primeiro treino
1/1" cheia na mesma caixa. Hoje `resumo` grava a regra a 100 % com os dados
que já reuniu (`_gravar`, duas consultas, uma vez) e anuncia na mesma tela;
a visita seguinte custa o mesmo que a de quem não tem nada a 100 %.

**A conquista é avaliada na PRIMEIRA SÉRIE DO DIA e no recorde, e anunciada
onde nasce.** Até 16/09/2026 o POST da série só avaliava quando
`supera_recorde` dizia sim — e estreia não é recorde, então "Primeiro
treino" nunca nascia na hora (B5): dez das onze regras dependem de um dia
de treino passar a existir, e ele passa a existir na primeira série. A
segunda em diante paga UMA consulta ("é a primeira?") e nada mais
(`workouts/test_recorde_na_hora`, 20); reenvio da fila (`criada=False`) não
avalia. E `ConquistasView` anuncia o que desbloqueia — antes a medalha
aparecia na lista sem "Conquista desbloqueada" ter sido vista uma vez.

**A SECRET_KEY não é gerada pela plataforma.** `generateValue: true` do Render
entrega 256 bits em base64 — 44 caracteres —, e o Django exige 50. Isso deixou
`security.W009` aceso em produção desde o primeiro deploy sem travar nada,
porque W é *warning* e o build reprova só em ERROR. Hoje é `accounts.E005`, e
derruba. A chave é definida à mão no painel; `DJANGO_SECRET_KEY_FALLBACKS`
existe só para a janela de troca, e sai da lista assim que as sessões antigas
expiram.

**Monitor externo bate em `/saude/vivo/`, nunca em `/saude/`.** As duas rotas
existem por causa desta diferença: `/saude/` é o readiness — consulta o
catálogo, e é o healthcheck do deploy. `/saude/vivo/` responde com ZERO
consultas. O banco no Neon hiberna após 5 minutos parado, e o plano gratuito dá
100 CU-horas por mês; a 0,25 CU sem hibernar dá 182, e a cota estoura por volta
do dia 16. Um monitor de 5 em 5 minutos em `/saude/` manteria o banco acordado
para sempre — o serviço que existe para melhorar a disponibilidade derrubaria o
banco no meio do mês. Em `/saude/vivo/` ele acorda o serviço web (que é o que
resolve o cold start de 50 s) e deixa o banco dormir.

**Log não guarda segredo nem dado de saúde.** `config/observabilidade.py` redige
token de redefinição (que anda **na URL**, e o logger de request grava caminho),
parâmetro de OAuth, chave de SMTP e URL de banco. `django.db.backends` fica em
WARNING até em DEBUG: consulta com parâmetro carrega e-mail e peso. Toda linha
leva o identificador do pedido, que também volta no cabeçalho `X-Request-ID` —
sem ele, "deu erro" e "fulano reclamou" nunca se encontram.
## Design: o que já existe, e o que não inventar de novo

**O sistema visual já existe, é enforcado por teste, e a primeira coisa a fazer
antes de criar componente é procurar o equivalente.** Auditado em 05/09/2026:
70 tokens no `:root` — oito degraus de texto, sete de espaçamento, quatro de
quina, três de sombra e seis de camada, mais as cores e as receitas. (O número
já foi escrito como 64 aqui: era a contagem de ANTES dos seis tokens de camada,
no mesmo parágrafo que os anunciava.) `config/test_design_system.py` congela a
dívida de valor cru no número atual — ela não pode crescer.

**A escala de empilhamento é vocabulário, e a ordem é regra de produto.** De
baixo para cima: `--camada-conteudo` → `--camada-barra-topo` →
`--camada-flutuante` → `--camada-navegacao` → `--camada-aviso` →
`--camada-bloqueio`. As duas barras
**não** ficam no mesmo degrau: nada pode cobrir a barra de baixo — o convite de
instalação cobriu a navegação uma vez, e `push/tests.py` guarda isso desde
então. A barra de cima pode ser coberta por um flutuante. Colapsar as duas num
degrau só inverte esse par, e foi o que a primeira versão da escala fez.

E `z-index` alto não vence contexto de empilhamento: o painel do mapa declarava
40 "acima da tabbar, que é 30" e perdia, porque é filho da barra de cima, que é
`sticky` com camada própria. Quem resolveu foi `max-height`, medido.

**Espaçamento não volta para dentro do HTML.** Havia 23 `style=` estáticos em
13 templates, com seis valores para cinco intenções — três deles fora da
escala. Cada intenção ganhou nome: `.form__nota`, `.acao-solta`,
`.chip-row--conteudo`, `.chip-row--inicio`, `.acoes-empilhadas`,
`.nota-do-botao`. Não são utilitárias genéricas (`.mt-4` e parentes): utilitária
só muda o lugar onde o número arbitrário é escrito. Duas exceções continuam
válidas e têm teste: valor calculado pelo servidor (`style="width: {{ pct }}%"`)
e template de **e-mail**, onde cliente não lê CSS externo.

**O que este app deliberadamente NÃO faz** — medido, não afirmado: zero
gradiente roxo; seis gradientes em 6.700 linhas; vidro em três cartões do topo e
no cartão de entrada, com `@supports` de contraste e a razão escrita (desfocar
cor chapada custa quadros para produzir a mesma cor chapada); 89% das sombras
usando token.

**O movimento tem UMA linguagem, e ela mora nos tokens `--mov-*` (15/09/2026).**
Toque `.1s`, estado `.18s`, expansão `.25s`, tela `.2s`, modal `.28s`,
sucesso `.5s`, passo 6 px, passo longo 12 px, degrau de lista 35 ms — e
`config/test_movimento.py` conta as durações escritas à mão em
`transition`/`animation` (o teto é ZERO; `.01ms` da saída de movimento
reduzido é a única exceção). Antes dos tokens o app tinha `.12s`, `.15s`,
`.16s`, `.22s`, `.32s`, `.5s`, `.7s` e `.9s` espalhados: uma segunda
linguagem nasce de um valor solto. Quatro decisões medidas:

- **`<details>` anima por JavaScript, abrindo E fechando** (`pwa.js`,
  "MOVIMENTO"): o navegador troca `open` de uma vez, e a refeição saltava de
  44 para 422 px. O animador mede as duas alturas, anima com `overflow:
  clip` e limpa os estilos ao terminar; `grid-template-rows: 0fr → 1fr` só
  animava a abertura e saiu da `.fora__corpo` porque a medida era tirada no
  meio da transição. Quem pedir `data-sem-animacao` fica nativo, e com
  `prefers-reduced-motion` TUDO fica nativo — o JS consulta `matchMedia`.
- **`view-transition-name` é ÚNICO por documento, e o teste lê os nomes do
  CSS.** Duplicado, o navegador PULA a transição inteira sem erro. O cartão
  AGORA da Home **não** leva nome de propósito: ele muda de slot ao ser
  marcado, e um nome faria o cartão A morfar no B. O número da série leva
  `display: inline-block`, porque elemento sem caixa derruba a transição
  da execução inteira.
- **Uma escala de toque, `.96`, e uma lista só** (seção 8 do CSS, três
  listas que `config/tests.py` confere serem a mesma). O brief pedia
  .97–.99; uma segunda escala no mesmo gesto é o que aquele teste existe
  para impedir. `.sessao-cartao` entrou na lista — e perdeu a `transition`
  própria, que sobrescrevia a da lista e afundava sem transição.
- **A memória de um toque entre páginas é `sessionStorage`, lida UMA vez.**
  O app é multi-página: o número da água conta do valor de ANTES do POST ao
  de agora, o cartão marcado celebra na página seguinte, o onboarding entra
  da direita ao avançar e da esquerda ao voltar. Nada disso afirma sucesso
  antes do servidor — a página nova É a confirmação. Enfileirado sem rede,
  a memória é apagada: um almoço marcado no metrô não pode "celebrar"
  horas depois.

**Antes de criar componente novo, procure.** `templates/partials/` tem oito
parciais; `card`, `btn`, `chip`, `pill`, `tile`, `data-list`, `empty-state` e
`hint` já existem e têm regra própria. Uma quarta versão do mesmo botão é o
defeito que esta seção existe para impedir.

`drawer` esteve nesta lista e saiu em 10/09/2026 com o redesenho do Treino: era
o `<dialog>` de vídeo do exercício, e a execução virou tela em vez de gaveta.
Não há mais sobreposição modal no app fora do `.modal`.

**Sobreposição: `<details>` antes de `<dialog>`, e TELA antes das duas.**
O mapa de áreas é `<details>` porque um menu de cinco links não precisa de foco
preso. O vídeo do exercício foi `<dialog>` por precisar — e deixou de precisar
quando a execução virou tela própria: navegar resolve foco, histórico e botão
voltar sem código nenhum, e uma gaveta que some ao trocar de exercício era
trabalho para reimplementar o que o navegador já faz.

`<dialog>` traz `inert` e foco preso de graça, e traz o custo que o convite de
instalação pagou, com 68 controles alcançáveis por trás quando o papel estava
errado.

**Estado vazio é convite, e os deste app já foram auditados.** Dos 16, quatro
parecem só constatar — e os quatro têm o motivo escrito no template: dois têm a
saída ao lado (botão ou campo na mesma tela) e dois são ramos defensivos que
ninguém alcança. Acrescentar texto ali seria ruído.

## Testes

Nome descreve o comportamento, não o método. Docstring diz **por que** aquilo
importa — de preferência com o caso real que motivou o teste.

Armadilha recorrente neste repositório: **o seletor do JavaScript e o marcador
do HTML são a mesma string.** `assertNotIn("data-x", html)` passa por acidente
porque `data-x` também está dentro do `<script>`. Ancore na classe
(`class="card resumo"`) ou no texto visível.

Contraste é medido, não julgado: `config.tests` recalcula a razão WCAG a partir
dos tokens, inclusive contra os fundos tingidos (`--brand-soft` e companhia).

## Limites reais deste ambiente

- **Node 24 e npm 11 estão instalados desde 12/09/2026** (WinGet), e com eles
  o `agent-browser` 0.37.1 da Vercel, com Chrome 153 próprio em
  `~/.agent-browser/browsers`. É a ferramenta de QA de navegador: sessão
  própria (`AGENT_BROWSER_SESSION`), saída sempre para arquivo e `stdin`
  fechado — o daemon herda o stdout, e um pipe espera um EOF que nunca vem.
  Lighthouse e Playwright continuam de fora por decisão, não por falta de
  Node: o `agent-browser` cobre o que eles cobririam aqui. O Capacitor da
  Corrida continua bloqueado por Android Studio/Xcode, não por Node.
- **PWA não escreve no Apple Saúde nem no Health Connect** — não existe API web.
  `workouts/health_export.py` gera TCX para importar.
- **Background Sync não existe no Safari do iPhone.** O evento `online` é o
  mecanismo principal; o sync em segundo plano é bônus.
- **O serviço web gratuito do Render bloqueia saída SMTP nas portas 25, 465 e
  587.** O e-mail de produção usa a Brevo na **2525**, que negocia STARTTLS
  normalmente (TLSv1.3 confirmado no handshake). Isso custou caro para
  descobrir: o Django **captura** a falha de envio em `PasswordResetForm.save()`
  e registra `Failed to send password reset email` — a tela devolve 302 e diz
  "verifique seu e-mail" como se tivesse dado certo. Só o log denuncia, e antes
  de `config/observabilidade.py` não havia log. Se a recuperação de senha parar
  de novo, o primeiro lugar a olhar é o `TimeoutError` do socket, não o Django.
- **O banco saiu do Render e foi para o Neon em 01/09/2026.** Provado em 04/09
  pelo cabeçalho do dump daquele dia: servidor 16.9, e o Render rodava 18.4 —
  um cliente 16.9 não despeja um servidor 18.4. O banco do Render **é apagado
  por volta de 23/09/2026** (verbo do painel: *deleted*), e continua declarado
  no `render.yaml` de propósito: ele é o rollback. Se o plano gratuito do Neon
  tem prazo próprio, ninguém verificou — é uma olhada no painel dele.
  Ver **Backup e restauração** e [`docs/infra-recuperacao.md`](docs/infra-recuperacao.md).
## Deploy

`git push` dispara o Render. `scripts/build.sh` roda collectstatic →
`check --deploy` → migrate → os três seeds, com `errexit`: build que passa
prova que a migração rodou. Confira em `/saude/`.

O `check --deploy` vem **depois** do collectstatic e é um portão, não um aviso:
ele importa a URLconf, que resolve `static()` para o favicon em tempo de import,
e sem o manifesto isso estoura com um erro que não tem nada a ver com o que a
verificação veio checar. Com `--fail-level ERROR`, o que reprova ali não sobe —
hoje são e-mail de produção (`accounts.E001`–`E003`) e força da SECRET_KEY
(`accounts.E004`–`E006`).

**O PRE-PUSH TESTA O COMMIT QUE SOBE, NÃO A ÁRVORE DE TRABALHO (17/09/2026).**
Incidente: o push de 15/09 (terça) passou "3044 OK" e o mesmo `main`
reprovava `plans.test_stress` na quarta. Duas causas, e as duas eram do
hook: (1) o teste de orçamento de consultas media a Home e o painel NO DIA
EM QUE A SUÍTE RODAVA — 36/21 consultas num dia de descanso do fixture,
41/27 num dia de treino com série registrada —, e o teto (40/25) tinha sido
medido numa terça; (2) o hook rodava `manage.py test` na árvore de
trabalho, que não é o que sobe: arquivo não commitado entra na conta e não
no push, e vice-versa. Hoje o teste congela a data no PIOR estado (quarta,
com série registrada) e o orçamento da Home é 41 com as consultas únicas
listadas; o painel ficou em 25 porque `resumo_da_sessao` passou a receber a
sessão e a escolha que o painel já tinha (27 → 24). E o hook exporta o SHA
do push num `git worktree` descartável, copia o `.env` e testa lá
(`scripts/hooks/pre-push`; `config/test_b9_disciplina.py` cobra). Não era
N+1: nenhuma consulta cresce com o histórico
(`test_o_custo_da_tela_nao_cresce_com_os_registros`); era estado e
calendário. E `/saude/` passou a devolver `commit` (`RENDER_GIT_COMMIT`,
sete caracteres): a prova de deploy deixou de depender de a mudança ter
superfície visível.

## Backup e restauração

Procedimento completo, incluindo o que fazer se produção desaparecer, em
[`docs/infra-recuperacao.md`](docs/infra-recuperacao.md).

```bash
DATABASE_URL='...' scripts/backup.sh ~/backups-nutriplan   # tira e valida
BACKUP_PASSPHRASE='...' scripts/guardar.sh ~/backups-nutriplan/xxx.dump
BACKUP_PASSPHRASE='...' scripts/restaurar.sh ~/backups-nutriplan/xxx.dump.gpg
```

`guardar.sh` cifra em AES-256 e **decifra de volta conferindo o sha256** antes
de apagar o arquivo em claro. Sem isso um cifrado quebrado sobe verde e só se
revela inútil no dia em que alguém precisa dele.

`backup.sh` **recusa** gravar dentro de um repositório git: este repositório é
público, e o `.gitignore` registra duas vezes em que um `git add -A` trouxe
pasta inteira que não era para vir. E ele apaga o arquivo pela metade quando o
despejo falha — `pg_dump` cria o arquivo antes de terminar de escrevê-lo.

O `pg_dump` precisa ser **18 ou mais novo** — o cliente se recusa a despejar um
servidor mais novo que ele. No Windows os binários ficam em
`C:\Users\biel-\pg18\pgsql\bin`; os do 16 que vêm com outras ferramentas geram
um arquivo de zero byte.

`restaurar.sh` se recusa a apontar para qualquer host que não seja local, porque
ele começa apagando o banco de destino. Ele varre **toda** chave estrangeira
procurando órfã — não uma lista escrita à mão, que envelheceria na primeira
migration — e conta linhas sem nunca ler conteúdo: o dump tem e-mail, peso e
histórico de treino de gente real.

Um dump que ninguém restaurou é uma esperança, não um backup. Restaurar os 12 MB
deste banco leva 0,3 s: não há desculpa para pular o drill.

Para trocar de provedor de banco, `scripts/migrar.sh` faz dump, restore e
conferência tabela a tabela **num comando só** — o que importa aqui é o tempo
entre o dump e a troca da `DATABASE_URL`, porque tudo escrito na origem nessa
janela se perde. Ele conta linha de verdade, e não `n_live_tup`: num banco
recém-restaurado a estatística ainda é zero, e a comparação passaria comparando
nada com nada.

Nos três scripts a string de conexão vai em `-d`, nunca como argumento
posicional: posicional exige vir por último, e `pg_dump "$URL" -Fc` morre com
"too many command-line arguments" em cliente mais velho — no meio de uma janela
de manutenção, que é o pior momento para descobrir isso.

O destino precisa ser **PostgreSQL 17 ou mais novo**: o `pg_dump` 18 emite
`SET transaction_timeout`, parâmetro que só existe a partir do 17.