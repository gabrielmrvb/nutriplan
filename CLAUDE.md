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
| `workouts` | ficha, cargas, assistente de ajuste, exportação de saúde |
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

**Plano é retrato, não referência.** `NutritionPlan` e `TrainingPlan` guardam os
números do dia em que foram criados. Mudou a entrada, nasce plano novo — os
antigos ficam. Nunca edite os números de um plano ativo: `plan_is_current()`
compara com o que o motor calcula hoje e descarta o que não bate.

**Ficha ajustada não é remontada.** `TrainingPlan.customized_at` desliga o
gerador. Sem isso, mudar o horário de terça apaga a troca de ontem.

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

Estado é o que não pode ser enfileirado. O formulário da ficha manda
`series_feitas`, um contador derivado que ela só atualiza no sucesso — offline
ele fica defasado por um, sempre, por construção e não por corrida. E o replay
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
nenhum grupo passar de `TETO_SEMANAL_POR_GRUPO = 20` séries efetivas, e
`escolher_para_o_tempo` corta até a sessão caber no tempo informado. A versão
anterior cobrava do exercício principal e derrubava o supino de quatro séries
para duas.

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

**A ficha da semana continua sendo o cartão inteiro.** Uma tentativa de
09/09/2026 trocou os outros dias pela linha compacta de hoje mirando o tamanho
da página; o tamanho caía pela metade e levava junto registro de série, carga,
repetições, descanso, progressão e histórico. Vinte e um testes reprovaram e
estavam certos. A linha compacta responde "o que eu faço agora"; o cartão
responde "o que tem na terça, e com que carga eu fiz da última vez".

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

**`achievements.resumo` não chama `avaliar`.** O Progresso mostra um resumo das
conquistas, e avaliar as regras ali levou a tela de 15 para 50 consultas, com
crescimento por histórico — 36 contra 54 medidas. `ConquistasView` já
documentava a mesma decisão. O teto do orçamento subiu de 15 para 26 COM a
medição escrita, e a guarda de N+1 continua estrita: teto só se mexe depois de
provar que o custo é constante.

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

**Antes de criar componente novo, procure.** `templates/partials/` tem oito
parciais; `card`, `btn`, `chip`, `pill`, `tile`, `data-list`, `empty-state`,
`hint` e `drawer` já existem e têm regra própria. Uma quarta versão do mesmo
botão é o defeito que esta seção existe para impedir.

**Sobreposição: `<details>` antes de `<dialog>`.** O drawer do exercício é
`<dialog>` porque precisa de foco preso; o mapa de áreas é `<details>` porque um
menu de cinco links não precisa. `<dialog>` traz `inert` e foco preso de graça —
e traz o custo que o convite de instalação pagou, com 68 controles alcançáveis
por trás quando o papel estava errado.

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

- **Node/npm/npx não estão instalados.** Nada de `npx`, Lighthouse, Playwright.
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