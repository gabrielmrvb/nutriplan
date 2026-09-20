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

## Autonomia

**DECIDA E REGISTRE (regra permanente, 17/09/2026).** Uma sessão só para e
pergunta quando UMA das quatro condições vale:

1. **gasta dinheiro novo** — plano do Render, serviço pago, API cobrada;
2. **apaga ou altera dado de usuário real em produção**;
3. **muda direção visual ou de produto que ainda não está escrita** em
   `DESIGN.md` / `TREINO.md`;
4. **precisa de credencial que não existe no ambiente**.

Tudo o mais — escolha técnica, ordem de execução, defaults de infra,
tolerância de teste, rótulo de texto, nome de campo, parâmetro de motor —
decide com o melhor padrão, registra em **"Decisões que tomei sozinha"** com
uma linha de razão, e segue. Vetos vêm depois, no relatório; nunca antes.

**Padrões já decididos — não perguntar de novo:** superpowers em toda missão
· TDD + sabotagem 100 % vermelha + revisão adversarial + suíte · o gate é o
CI, fluxo branch → PR → FILA (`scripts/github.py enfileirar`: a fila
local desta máquina, porque a do GitHub só existe em organização; merge
commit; `strict` intacto)
· deploy provado por `/saude/` + smoke + QA em produção com conta descartável
pelo signup público, conta apagada pela tela, demo intacto — **a conta de QA
descartável é do AGENTE (decisão do dono, 18/09/2026): a sessão cria pelo
signup público, com e-mail claramente de QA (`qa-<sessão>-<data>@nutriplan.invalid`),
senha só para aquela conta, nunca no relatório; obrigação de APAGAR pela
tela ao terminar e provar que sumiu (login recusado). Nunca a conta pessoal
do dono. Sessão cujo ambiente proíba criar conta ou digitar senha diz isso
no relatório e prova o que der pelo `/demo/`** · `scripts/qa/
nav.py` (CDP) para navegador, inclusive sites de terceiros na sessão logada do
dono (Render, GitHub, claude.ai) · mídia de exercício ativa com curadoria e
mosaico para veto posterior · plano ativo antigo nunca remonta sozinho · o
teste dourado da ficha nunca afrouxa · spec (`DESIGN.md` / `TREINO.md`) vence
proposta externa, e a divergência vai para "recomendo rever" · segredo nunca
no repositório nem no relatório.

**Relatório:** "O que preciso de você" só lista itens que caem nas quatro
condições. Lista vazia se escreve "nada" — e a sessão vai para o próximo item
do plano mestre sem esperar.

**Coordenação entre sessões:** antes de tocar arquivo em comum, a sessão
avisa as outras pelo ledger compartilhado — `C:\Users\biel-\nutriplan-ledger.md`,
fora de qualquer worktree, uma linha por aviso (`data hora · sessão · arquivo
· o que vai fazer`), lido antes de editar e escrito antes de commitar. Conflito
de merge é resolvido por quem faz o rebase.

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
Em branco é desconhecido, e desconhecido não invalida nada. E quando a
conferência exata diz "igual", o plano recebe a impressão digital de HOJE
(uma escrita, uma vez): sem isso todo deploy que reescreve prosa do
`TREINO.md` — a doutrina entra na impressão — cobrava as onze consultas de
toda ficha antiga em toda visita à Home, para sempre. Prescrição divergente
NÃO carimba: o aviso continua até a pessoa decidir. O demo é fixture de que
o seed é dono: `seed_demo` regenera sozinho quando a prescrição mudou.

**O CICLO DA DIVISÃO RODA CONTÍNUO, e a letra de hoje sai da POSIÇÃO, não
do dia da semana (17/09/2026).** Em 5 dias com ABC o ciclo fixo A B C A B
recomeçava toda segunda, peito e costas caíam 2× e "Pernas e ombros" 1× —
quadríceps em 7 diretas por semana, para sempre. O desequilíbrio era do
calendário. Hoje a semana seguinte continua de onde a anterior parou (C A B
C A, depois B C A B C; em 3 semanas cada letra cai 5 vezes), e a média do
ciclo está medida no `TREINO.md` — peito 25,0 no Padrão contra o alvo de
24, ACEITO pelo dono em 17/09 com tolerância de ± 2 (26 é o teto da média;
ficha real de academia faz 26–28), lida do documento pelo teste. O golden
não baixa. Como funciona: `TrainingPlan.
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

**O EQUIPAMENTO ESTÁ NO PERFIL DESDE 17/09/2026 (tarde), E O MOTOR OBEDECE
POR SUBSTITUIÇÃO — nunca por filtro.** `Profile.equipamento`
(`accounts.models.Equipamento`: completa · básica · casa com halteres · só
peso do corpo; pergunta na etapa 2 do onboarding e no Perfil), o mapa de
cada resposta para `Exercise.equipment` no `TREINO.md` ("Mapa de
equipamento", lido por `doutrina.equipamentos_de`), e
`services.substituir_por_equipamento` ANTES de `prescrever_opcoes`: o item
do modelo fora do perfil é trocado por exercício ativo do MESMO `padrao` e
grupo dentro do perfil que ainda não esteja no modelo, com a dose do item
trocado; sem substituto, sai. `TrainingPlan.equipamento` é retrato; mudar
no perfil torna a ficha inválida e remonta, como nível e faixa. **O default é
"completa" nos dois lados e NÃO é vazio**, ao contrário de `experiencia`:
toda ficha anterior à pergunta nasceu do catálogo inteiro, então "completa"
é a verdade dela, e ninguém foi remontado pela pergunta nova. "Completa"
custa zero consultas (o filtro nem roda); perfil restrito custa UMA consulta
ao catálogo por prescrição — e a conferência (`_prescricao_bate` +
`_prescricao_confere`) refaz a conta COM o perfil, inclusive na
pré-conferência de reps e descanso, senão o afundo que substituiu o
agachamento reprovava e a Home oferecia "regenerar" para sempre a quem
treina em casa.

Por que substituição e não filtro — a medição de 10/09/2026, que continua
valendo: a prescrição não SELECIONA exercícios, `prescrever_semana` copia
MODELOS curados de `splits.json`, com os nomes escritos; filtrar por
equipamento não troca de exercício — abre BURACO no modelo (em "casa +
halteres" oito modelos perdiam grupo sem substituto e `abcde-C` terminava
com ZERO exercícios). E os modelos já listam quase todas as alternativas: em
"básica" o `abc2 A` perdia os três itens de barra SEM repor, porque todas as
pressões de peito sem barra já estavam nele — a letra fechava em 6
exercícios e 50–52 min, dourado vermelho. Os **cinco de peito e tríceps sem
barra** (supino declinado com halteres, crucifixo inclinado com halteres,
flexão com pés elevados, flexão fechada, tríceps coice) entraram FORA de
todo modelo, de propósito, para serem exatamente esse substituto: a ficha
de "completa" ficou idêntica (ninguém recebeu "regenerar?") e básica E casa
com halteres fecham o dourado da letra A (7 exercícios, 25 séries, 59 min
no `abc2`). "Só peso do corpo" continua `expectedFailure` nomeado no
dourado: B tem um exercício e C dois, e a lista do que falta está no
`BACKLOG.md`. **E nesse perfil a versão rápida NÃO aparece — por regra,
não por falta (decisão de 18/09/2026, opção "manter ausente")**: "Menos
tempo hoje?" só existe onde a rápida CORTA alguma coisa (`hoje.rapida_muda`
em `preparar_dia`), e a letra A de só peso do corpo tem 3 exercícios em ~30
minutos — cabe inteira nos 40 da rápida. Gerar uma "rápida com menos
séries" ali seria o mesmo treino com outro nome, o defeito de veracidade
que o app recusa desde a faixa de duração. Provado em produção com conta
descartável (18/09, casa com halteres oferece; peso do corpo não) e
guardado em `workouts/test_rapida_por_perfil.py`, com controle positivo.

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

O campo de ambiente NÃO existiu no perfil até o motor poder obedecê-lo, de
propósito: guardar preferência que não vira nada é o mesmo defeito de
veracidade que `prioridade == ""` evita do outro lado. Quando o motor passou
a obedecer (17/09, tarde), `workouts/test_capacidade_de_ambiente.py` virou
ao contrário — o perfil TEM a pergunta, o formulário a FAZ, o motor LÊ
`equipment` — e os ambientes medidos passaram a ser os QUATRO PERFIS do mapa
(completa e básica SUPORTADO; casa PARCIAL; peso do corpo NAO_SUPORTADO).

**`Equipment` tem UM consumidor no motor: `substituir_por_equipamento`.** O
campo nasceu para o assistente de troca ("a máquina está ocupada"), que
entrou em `7819b30` e saiu em `d86d9c7`; `DISPUTADOS` e `disputa_equipamento`
sobreviveram à remoção como código morto por três campanhas e saíram em
10/09/2026. A substituição por PERFIL acontece antes de prescrever; a
troca por EXERCÍCIO é a de baixo.

**"OUTRAS FORMAS" É A INTERAÇÃO PRINCIPAL DA FICHA (17/09/2026, noite).** A
pessoa não escolhe mais entre opção 1 e 2; escolhe COMO fazer cada
movimento. `TrocaDeExercicio(user, original, substituto)` (migration
`workouts.0029`) é customização POR EXERCÍCIO — vale em toda letra, toda
semana e toda opção em que o original apareça — e NÃO toca em
`SessionExercise` nem em `customized_at`: a ficha continua retrato, a
rotação continua, `rotina_invalida`/`_prescricao_bate` não a enxergam. A
aplicação é EM MEMÓRIA (`services.aplicar_trocas`, uma consulta por tela,
logo depois de carregar as linhas do plano — painel, ficha, execução e
leitura passam pelo mesmo ponto): o item passa a apontar para o substituto
com a MESMA dose, então trocar não altera séries nem volume (diferença 0).
`ExerciseLog` grava no exercício FEITO; a linha do original responde pelo
substituto na prescrição de hoje por JOIN (`_linha_do_exercicio`), na
consulta que já existia — o orçamento do POST da série continua 20. As
alternativas (`alternativas_de`) são do mesmo `padrao` e grupo, dentro do
equipamento do perfil, FORA DA MESMA LISTA (sessão + opção — duplicata só
é problema no mesmo treino; a outra opção é outro dia), o equipamento mais
próximo primeiro; a ficha só anuncia "outras formas" onde a leitura lista
alguma (`contar_outras_formas`, a mesma régua — o QA achou a linha
anunciando e a leitura vazia quando as réguas divergiam). A lista mora na
LEITURA do exercício, com foto (o primeiro quadro da free-exercise-db) e
"Trocar"; a leitura do substituto diz "No lugar de X", mostra o histórico
de X e tem "Voltar ao original". `POST /treino/trocar/` é estado absoluto
(trocar de novo atualiza, `desfazer=1` apaga, sem `op_id`), volta para a
leitura com a mesma volta (`?de=`), e recusa original fora da ficha ou
substituto que não é forma do movimento no equipamento. A leitura passou a
TER formulários, e a régua "ver não é executar" virou POR DESTINO: todo
`<form>` do `<main>` aponta para a troca, nunca para a série. Custos
medidos: leitura 9 → 11 (trocas + alternativas; o perfil vem do
`dispatch` e as linhas vêm sem o exercício), ficha 15 → 17 (trocas +
contagem), Home 43 (no teto), painel 20.

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

**A FAIXA DE REPETIÇÕES É ALVO, NÃO TETO — e quem tem 65 anos ou mais nunca
lê "falha" (T2.2, 17/09/2026).** `instrucao_de_esforco(item, serie,
experiencia, cauteloso=False)` diz, na ÚLTIMA série de composto com
`rep_max` até 12 (`REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO`), "1 a 2 sobrando,
mesmo passando de 10": quem chega em 10 com 1 a 2 na reserva faz 11 — o RIR
governa, o número orienta (Helms 2016). Com faixa longa (15, 20) o aviso não
entra: seria ruído. `cauteloso` é `perfil.age >= IDADE_CAUTELOSA` (65,
Fragala 2019/NSCA), lido em `services` no mesmo ponto que a experiência,
do perfil já carregado — zero consulta a mais —, e tira a falha até do
isolador ("Última série: 1 na reserva, técnica limpa."). Toda frase cabe
numa linha a 320px, e a régua foi MEDIDA, não só contada: "Pare com 1–2
sobrando, mesmo passando de 10." tem 44 caracteres — o teto do teste — e
quebrava em duas linhas a 320 e 360; a de 37 cabe. A tela não mudou:
`agora.html` já lia `atual.esforco`.

**RETOMAR E ESTAGNADO FALAM; NUNCA BAIXAM NÚMERO (T2.3, 17/09/2026).** Dois
estados a mais em `workouts/adaptacao.py`, na mesma leitura pura, com
precedência fixa — hoje manda > sem anilha > sem referência completa nas 4
datas > RETOMAR > SUBIR > ESTAGNADO > MANTER:

- **RETOMAR**: 21 dias ou mais sem NENHUMA série do exercício
  (`DIAS_PARA_RETOMAR`; o intervalo conta do último registro, de qualquer
  série — parcial há 5 dias com a completa há 20 não é pausa). Mesma carga
  (`valor` = a maior da referência, nunca × 0,9), SUBIR suspenso mesmo com
  a faixa fechada, reps no piso (`REPS_NO_PISO = {SUBIR, RETOMAR}`; a
  `_sugestao_de_reps` lê esse conjunto, não `MUDA_CARGA`), e a frase pede
  para confirmar; de 28 em diante acrescenta "comece mais leve se
  precisar". 21 e não 15: Hwang 2017 dá duas semanas sem perda e Bosquet
  2013 diz "significativo a partir da terceira semana"; frear antes disso
  era freio sem evidência.
- **ESTAGNADO**: três sessões completas seguidas (≤ 27 dias entre elas) na
  mesma carga máxima, nenhuma fechou a faixa, e o total de repetições da
  última não passou o da primeira por mais de 1 (Mitter 2022: uma rep é
  ruído). "Manter e dizer": o campo abre com a mesma carga, a tela mostra o
  verbo **manter** (`Progressao.rotulo`; "estagnado" não é verbo e não
  aparece) e a frase diz "três treinos em 60 kg sem ganhar repetição".
  `ESTAGNADO_PERSISTENTE` é a trava escrita ANTES de existir RESET: o mesmo
  platô depois de um recomeço (sessão mais leve seguida da volta à mesma
  carga em ≤ 56 dias) é só frase, nunca outro RESET em cadeia.

Os quatro negativos que congelam o veto ("a adaptação é leitura") têm
teste em `workouts/test_retomar_estagnado.py`: a ficha da semana 8 é igual
à da semana 1 com sete semanas de registro no meio; a série de ontem não
muda a prescrição de hoje; treinar em dia não declarado não altera dias,
teto nem divisão; o módulo não escreve em `SessionExercise` (controle
textual, e o retrato das linhas antes e depois das telas). Medido sobre o
ano sintético de `seed_stress` (1.254 aberturas, 50 exercícios): manter
71,9 %, retomar 21,7 %, sem sugestão 4,0 %, subir 1,8 %, estagnado 0,7 % —
o retomar alto é do GERADOR, que sorteia 6 de 50 exercícios por dia e
deixa intervalos de 3+ semanas em 22 % das aberturas; o gatilho de
recalibrar era "estagnado > 30 %" e está longe. Os dias (21, 28, 27, 56) e
o "+1" são calibração [HIPOTÉTICA] do brief de 13/09, e é o
`medir_progressao` (T2.4) que vai revê-los com dado de produção.

**O INSTRUMENTO (T2.4, 17/09/2026): medir e limpar sem mudar o que a
pessoa vê.** Quatro peças, e a natureza comum é essa:

- `manage.py medir_progressao [--dias 365]` é SÓ LEITURA — duas consultas
  fixas (as linhas de prescrição ativas e os registros da janela), nunca
  uma por pessoa — e conta, por abertura de exercício, o estado que a
  adaptação daria, a distribuição de `reps − rep_max` na última série do
  dia, a fração que PAROU EXATAMENTE em `rep_max` (a faixa lida como teto),
  os "retomar" sem pausa (a pessoa treinou outros exercícios no intervalo)
  e o intervalo em semanas. `workouts/test_instrumento.py` cobra que
  nenhuma consulta começa por UPDATE/INSERT/DELETE e que o custo não
  cresce por exercício;
- `RecordLoadView` (a rota da ficha, fora da fila) avalia conquista só na
  PRIMEIRA série do dia ou no RECORDE — a guarda que `ConcluirSerieView`
  já tinha. A rota antiga pagava o catálogo inteiro em toda carga anotada;
  abaixo do recorde, no meio do treino, nenhuma regra muda de resposta;
- o Progresso CONVIDA quem se declarou iniciante (ou não respondeu) a
  atualizar o nível depois de 180 dias e 24 datas com série
  (`progresso.convidar_a_atualizar_experiencia`): o app não infere nível —
  "uso não é intenção declarada" — mas depois de meio ano a pergunta cabe,
  porque o teto por grupo do iniciante é o menor (TREINO.md, B). UMA
  consulta para qualquer nível — o nível entra no `WHERE` pela junção com
  o perfil, porque `user.profile` não está em cache nessa tela e lê-lo à
  parte custava a segunda (medido: 28 contra o teto de 26; o teto foi para
  27 com a razão escrita);
- `manage.py podar_operacoes` roda no build, por último, e apaga
  `SyncedOperation` com mais de `VALIDADE_DIAS` (30). O método `podar`
  existia desde a fila offline e ninguém o chamava. Trinta é MAIOR que os
  7 dias que a fila reenvia — a poda nunca alcança um `op_id` que um
  reenvio ainda traria, senão a água somaria duas vezes; há teste.

E a medição L08, feita no navegador com rede lenta emulada (`nav.py rede
3g`: 400 ms de latência, 400 kbps): "Concluir série" é um POST→302→GET
de 31 KB que custa 180–330 ms de `load` no Wi-Fi e ~550 ms no 3G lento
(redirect ~460 ms) — e o iframe do vídeo que a pessoa abriu MORRE com a
recarga (1 → 0): a cada série, tocar "ver vídeo" de novo. É o insumo da
fatia E "fetch sem recarga", que continua fora até alguém decidir com
esse número.

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

## Design / Onda 3

Seção da campanha Mesa & Ferro (branch `design/mesa-e-ferro`, 15–16/09/2026).
Tudo aqui foi MEDIDO no `app.css` real; onde uma frase de outra seção deste
arquivo ficou velha, a verdade nova está aqui e a velha não foi editada — as
duas sessões da campanha só escrevem nesta seção para não brigar no merge.

**Ferro é escrito UMA vez, e dois gatilhos o ligam.** A paleta escura mora em
36 tokens `--ferro-*` no `:root`; `@media (prefers-color-scheme: dark)` e
`body.modo-foco` (classe que o servidor escreve na execução do treino) só
fazem `--x: var(--ferro-x)`. Antes, a mesma cor estava escrita em dois blocos
e divergia sem ninguém ver. `config/test_ferro.py` guarda a estrutura — todo
`--ferro-x` tem um `--x` de Mesa, os dois gatilhos mapeiam o mesmo conjunto
e nada além de `var(--ferro-…)` entra neles — e `config/tests.py` resolve o
`var()` antes de medir contraste. Os pilares têm cor nomeada: `--agua`,
`--brasa`, `--terra`, `--chama`, `--folha`; `--accent`/`--warm`/`--border`
saíram de vez.

**Foco é `--brand` em todo controle, e o `--glow` virou anel de 1 px.** Cinco
controles pintavam o foco com `--agua` — a cor do pilar Hidratação num
formulário de perfil —, e o campo em foco tinha um brilho difuso de 26 px. O
anel de 1 px somado à borda que já vira `--brand` dá os 2 px do DESIGN.md. O
NOME `--glow` ficou porque `workouts/tests.py` lê `var(--glow)` no foco do
campo e proíbe token órfão; a receita é que mudou. `config/tests.py` conta o
anel de marca por DEFINIÇÃO de token ({`--halo`, `--glow`, `--ferro-glow`}) e
exige zero fora delas. E o campo inválido FALA: `.field-input[aria-invalid]`
pinta a borda de `--danger`, e `partials/field.html` escreve os ids
`{{ auto_id }}_error` / `_helptext` que o `aria-describedby` do Django 5.2 já
apontava sem alvo. `config/test_foco.py`.

**O sprite entra em toda página, uma vez, pela base — e não no shell
offline.** A frase "só é incluído no onboarding" do bullet **não tem
ícone** das "Três ausências no mapa" (seção "Decisões") era verdade até
16/09/2026 — e a decisão dali continua de pé por outro motivo: `/areas/`
segue sem `<use>` porque o mapa é lista de nomes, não de desenhos. Hoje `base.html` inclui `partials/icones.html`
dentro do mesmo `{% if not shell_offline %}` do `data-usuario`; onboarding e
vitrine deixaram de incluir por conta própria. Medido: ficha +2 939 bytes
(sprite 2 946 B brutos, 849 B gzip, 13 símbolos) — abaixo do teto de +4 KB do
plano mestre; `/offline/` zero símbolos. E o `stroke-width="2"` está em CADA
`<symbol>`, não na raiz: o clone do `<use>` herda do consumidor, e com o
atributo só na raiz o cartão de escolha desenhava traço 1 (1 397 px de tinta
contra 2 789). `config/test_sprite.py` lê os 13 símbolos e fecha a lista de
traços do consumidor em {2, 2.8 (o visto do cartão marcado)}.

**Keyframe sem consumidor é linguagem morta, e a catraca está em zero.**
`serie-ok`, `serie-anel`, `esqueleto` e `descanso-acabando` foram escritos
para a execução e nunca ganharam a classe que os dispara; `varrer` fazia o
anel de progresso varrer do zero a cada abertura — movimento que não confirma
ação nenhuma. Os cinco saíram (23 → 18 keyframes), e
`config/test_movimento.py` exige que toda `@keyframes X` tenha `animation: X`
ou `animation-name` em algum lugar. Se a onda 6 os quiser, nascem com o
consumidor no mesmo commit. `font-weight: 760` (dois números) virou 750, o
peso de todo tile — pesos distintos 12 → 11.

**Todo botão diz qual botão é, e a variante é lista fechada.** {`btn--primary`,
`btn--ghost`, `btn--quiet`, `btn--perigo`, `btn--google`, `btn-link`};
`btn--block`, `btn--sm` e `btn--hoje` são tamanho e posição, não decisão.
Eram cinco botões nus (500.html, "Minhas conquistas" no Perfil, três na
gestão); hoje zero, e `config/test_design_system.py` varre `templates/`. O
`.mapa__area:active` entrou na lista única de `:active` da seção 8 em vez de
ter escala própria. E o `<a class="btn">` que leva a outra tela avisa que
está indo: `pwa.js` marca `is-carregando` + `aria-busy` no clique (mesma
receita visual do `[aria-busy]` do `<button>`), e o `pageshow` limpa ao
voltar pelo bfcache. Fica de fora quem não troca de página: `target`,
`download`, `#`, `mailto:`, `tel:`, `sms:`, `javascript:`, clique com
modificador — e **`data-arquivo`**, a marca dos dois links que exportam o TCX:
a resposta é `attachment` e a página não troca, mas a view pode responder 302
com mensagem quando não há treino, e `download` faria o navegador SALVAR
aquele HTML. Sem a guarda de `#`, o CTA da Home (`acao.url = "#slot-N"`)
ficaria com o anel para sempre.

**A vitrine mora em `/gestao/vitrine/`** (mesma permissão do painel de
gestão): toda parcial e componente em todo estado, nos dois regimes
(`?regime=ferro` escreve `body.modo-foco`), coberta por um teste que lê a
pasta `templates/partials/` e exige cada arquivo lá ou nos dois `base.html`.
É onde se fotografa antes de mexer em token.

**Contraste: 274 pares medidos no CSS real, zero reprovados.** Todo texto ×
todo fundo a 4,5:1 e todo gráfico × superfície a 3:1, Mesa e Ferro
(`scripts/qa/auditar_contraste.py`, mesma régua da suíte). Quatro passam
raspando, todos gráficos em Mesa: `--folha` sobre `--surface-3` (3,03),
`--brand-soft` (3,14) e `--surface-2` (3,15); `--chama` sobre `--surface-3`
(3,29). Quem mexer em `--surface-2`/`--surface-3` roda o script antes.

**O export do Claude Design ainda não chegou, e o terreno está pronto.**
`scripts/inventariar_export.py` classifica a árvore extraída (tolerante a
pasta desconhecida; `--estrito` falha nomeando cada arquivo incerto) e
`scripts/tokens_do_export.py` compara os tokens do export com o `:root` de
Mesa (CSS custom properties e JSON W3C/plano; nomes e cores normalizados).
Os dois estão testados contra árvores sintéticas com a estrutura documentada;
o primeiro uso real é a Task 12 do plano do design system.

**O que a onda 3 NÃO fez, e por quê** (plano da noite de 16/09,
`docs/superpowers/plans/2026-09-16-onda-3-noite.md`): famílias de cartão
(T3.3 — 114 cartões e três decisões de direção abertas), variantes novas de
botão (T3.4 — `--tonal`/`--texto`/`--icone`), o renome
`.choice-list--dias → .segmented--envolve`, emoji → glifo nas conquistas (3
desenhos novos e o cartão de compartilhar desenha o emoji), a fonte própria
(T3.2 — download externo e decisão do dono). Cartão dentro de cartão foi
MEDIDO e é zero em sete rotas (`config/test_cartoes.py`, catraca em 0).

**CORTE: o Ferro é a BASE e o Papel o derivado (T3.1′, 16/09/2026).** A
direção escolhida em `docs/briefs/design/DIRECAO-ESCOLHIDA.md` (veto do dono
pendente) inverteu quem é a base: os valores moram UMA vez em `--ferro-*` e
`--papel-*` no `:root`; o próprio `:root` liga o Ferro (`--bg:
var(--ferro-bg)`), `@media (prefers-color-scheme: light)` liga o Papel e
`:root.modo-foco` liga o Ferro de volta. A classe `modo-foco` vai no
`<html>`, e NÃO no `<body>`: `--glass`, `--glow` e `--halo` são receitas
de `var(--bg)`/`var(--brand)` declaradas no `:root`, e uma custom property
resolve o `var()` onde é declarada — com a classe no `<body>` a execução em
Ferro saía com a barra de abas clara e o anel de foco oliva (visto na
captura). E a execução (`ModoTreinoView`) passou a ESCREVER a classe: o
contrato dizia isso desde a Mesa & Ferro e nenhuma view cumpria — só a
vitrine, por parâmetro (`workouts/test_foco_na_execucao.py`). `config/
tests.py` lê os dois regimes por `REGIME_FERRO`/`REGIME_PAPEL` e o leitor
`_tokens` resolve o `var()` do próprio `:root`; `config/test_tema_claro.py`
virou a trava de "o Ferro é a base". Paleta da tabela do DESIGN.md com
quatro ajustes MEDIDOS: `--ferro-surface-2` #292d25 e `--surface-3`
#33382d (a direção dava 1,11 e 1,14 sobre a superfície; a régua U28 pede
1,2), `--ferro-terra` #da9169 (a argila da direção ficava a 4,44 sobre a
própria tinta em `--surface-2`) e os cinco `--dia-*` movidos 1–12 % para
passar a 4,5 sobre a própria tinta nos fundos novos. 274 pares no CSS real,
zero reprovados; raspando só `--brasa` (4,59) e `--terra` (4,72) sobre
`--surface-3` no Ferro. `--corte`/`--corte-g`/`--corte-p` e
`--mov-recompensa` NASCEM com o consumidor, nos PRs dos componentes e da
execução (`test_no_css_variable_is_declared_and_never_used` recusou os
quatro órfãos no pre-commit); `--shadow-*`/`--edge` valem `0 0 0 0 transparent` — não `none`, que não entra em lista de
`box-shadow` e derrubaria o `--halo`. Manifesto e `theme-color` seguem a
base (`PWA_THEME_COLOR` #10120e; `PWA_LIGHT_COLOR` na meta com `media`).

**Duas fontes próprias, e a display só em herói (T3.2, 16/09/2026).**
Bodoni Moda (display; `wght` 400–900, `opsz` 6–96) e Karla (texto; `wght`
400–800), os dois `.woff2` do Google Fonts para o subconjunto latin,
auto-hospedados em `static/fonts/` com a OFL ao lado: **70 580 bytes** no
total contra o gate de 260 KB (`config/test_fontes.py`), `font-display:
swap`, pré-cacheados pelo service worker, `font/woff2` registrado no
`mimetypes` para o servidor local (o Windows não o conhece). A itálica da
Bodoni ficou de fora: o mockup a usava a 13–19 px, abaixo do piso de 20 da
display — sem consumidor, sem arquivo. Medido com fontTools, as duas têm
`tnum`; a nota de `DIRECAO-ESCOLHIDA.md` ("didone não tem numeral
tabular") valia para o mockup e foi corrigida. A display aparece em DEZ
regras e só nelas — `h1` (28 px, 600; era 40/800), `.hoje__nome`,
`.agora__titulo` e `.agora__nome` (os nomes, 22,7 px), `.ring__value`,
`.curva__valor`, `.modulo__valor`, `.balance__value`, `.tile__value`,
`.pesagem__media`, `.entrada__wordmark`, `.corrida-numero__valor` — e o
teste cobra que toda regra com `var(--font-display)` tenha tamanho de
herói. Os pesos são QUATRO (400 · 500 · 600 · 700): os oito degraus
sintéticos (550/620/650/680/720/750/780/800) foram mapeados (550 → 500,
620/650 → 600, o resto → 700), e `b, strong { font-weight: 700 }` porque
`bolder` de 600 é 900 e a Karla para em 800 — o "2100 kcal" do resumo
saía sintetizado. Catraca de `font-size` cru desceu 119 → 117 (o `h1` do
desktop perdeu o `1.9rem`).

**A quina é a folha, e nada clicável é pílula (T3.3 + T3.4, 16/09/2026).**
Três tokens de QUATRO valores substituem a escala 24/16/12/8: `--corte-g:
0 40px 0 40px` (o prato — `.card.agora-card`, o painel de hoje do treino,
a ofensiva, a água, a barra de abas), `--corte: 0 20px 0 20px` (cartão de
lista, botão, campo, mídia, modal, `.meal`, a aba ativa) e `--corte-p: 0
12px 0 12px` (chip, célula, selo de opção, filho de caixa). Ordem sup-esq
· sup-dir · inf-dir · inf-esq: ponta em cima à esquerda e embaixo à
direita, como a folha do logo. A migração foi de TOKEN, não de regra —
`var(--radius-xl)` → `var(--corte-g)` etc., 82 declarações —, e o único
lugar que precisou de decisão foi o raio "de dentro" do segmented
(`calc(var(--radius-sm) - 3px)`): `calc()` não entra num token de quatro
valores, então é `--corte-p` direto. `--pill` ficou em 14 usos, todos
barra, trilha, ponto ou selo; sete clicáveis saíram dela (`.chip`, os
links da barra de cima, "Fazer" da ficha, o avanço do wizard, o fechar do
demo, as abas da gestão, o rótulo dos dias) e `config/tests.py` prende as
duas coisas — a identidade dos quatro tokens e a lista de clicáveis que
não podem ser pílula. O cartão continua sem sombra e sem borda: a
superfície é o que separa, e é por isso que o contrato o chama de FAIXA.

**A folha de recompensa, e os três momentos que se movem (T3.5 + T3.6,
16/09/2026).** A última série do treino abre o placar DENTRO da folha-lima
(`.recompensa`: `--brand` cheio, `--on-brand`, `--corte-g`): a carga total
de hoje em Bodoni — peso × repetições, série a série, `services.Placar`,
CONTAGEM sobre o `item.load` que a tela já tinha, zero consulta nova —,
"vs. a última vez" (a mesma conta sobre a última vez de cada exercício;
some sem passado), o recorde (a série mais pesada de hoje acima de
qualquer data, a régua de `achievements`), séries e minutos; "Ver o treino
completo" primário (a ficha da sessão — o mockup dizia "Ver resumo do
treino", e um verbo por destino venceu) e "Voltar para Hoje" contorno. O
movimento: `folha-sobe` em `--mov-recompensa` (.45 s) a partir do canto
inferior direito, o número conta do ZERO em `--mov-sucesso` depois de a
folha subir (`data-conta="zero"`, `pwa.js`), os números pequenos em
cascata de `--mov-cascata` (80 ms), os botões chegam parados a .95 s; com
`prefers-reduced-motion` o quadro final aparece pronto
(`workouts/test_recompensa.py`). Os outros dois momentos: `corte-abre` na
refeição recém-marcada (`.meal.is-recem` — as duas pontas viram curva por
um instante, `--corte-aberto`) e `corte-desdobra` ao CRUZAR a meta de água
(`.agua-card.is-meta`, só no toque que cruza — `pwa.js` compara o valor de
antes com o de agora contra `data-agua-meta`). O Chrome headless desta
máquina responde `prefers-reduced-motion: reduce` por padrão — `scripts/qa/
nav.py movimento normal|reduzido` emula os dois, junto com o tema, na
mesma chamada. `.choice-list--dias` virou `.segmented--envolve` e o visto
do cartão de escolha virou folha pequena. O que a onda 3 ainda NÃO fez:
emoji → glifo nas conquistas (três desenhos e o `card.js` desenha o
emoji) e a corrida em andamento em Ferro — os dois ficam para a próxima
onda, com o consumidor.

**VETO: a direção principal é a NERVURA · ANDAIME (17/09/2026).** O dono
escolheu por gosto, sobre as capturas, e a pontuação de 16/09 (CORTE 25 ×
NERVURA 23) ficou como histórico em `DIRECAO-ESCOLHIDA.md`; o `DESIGN.md`
foi reescrito a partir do `Direcao1-a`, e do `1-b` entrou só o que pontua
em identidade e em execução/recompensa, item a item (tabela naquele
arquivo). O que mudou de VALOR, sem mexer em estrutura (PR dos tokens):
a paleta — chão #0b140f, `--surface` #121e17, verde-neon #43df7a, laranja
#e8a33d para a carga; no claro, verde-floresta #106632 — com a segunda e a
terceira superfícies vindas da régua U28 (a direção só tem dois degraus)
e quatro valores do claro escurecidos 1–5 % pelo vizinho que passa
(`artifacts/paleta_nervura.py`; 274 pares, zero reprovados; pior par
`--danger`/`--surface-3` 4,65 no Ferro); as fontes — Big Shoulders
Display (display, caixa alta 800 nos títulos e nomes, 900 nos números) e
Archivo (texto), 70 364 bytes; **a Big Shoulders NÃO tem `tnum`** (dígitos
proporcionais, medido com fontTools), então a display fica para o número
SOLTO e toda coluna de números — a lista de pesagens — é Archivo tabular
(`config/test_fontes.py` prende as duas regras); a quina — ZERO
`border-radius` em 390 declarações do mockup — virou três SLOTS com o
mesmo valor (`--quina-g`/`--quina`/`--quina-p: 0`), `--pill` saiu e todo
`border-radius` do arquivo é slot, `50%` (o anel) ou `inherit`; o
movimento — `--mov-nervura: .6s` e `nervura-acende` (a régua que risca da
esquerda para a direita) no lugar de `corte-abre`/`corte-desdobra`, como
`::after` da refeição registrada e do bloco da meta batida. A régua
diagonal (`--nervura`), o traço de 2 px (`--traco`), o CTA inclinado
(`--inclinado`) e a ponta de folha (`--ponta`) nascem com o consumidor,
no PR dos componentes.

**O andaime nos componentes (NERVURA 2/3, 17/09/2026).** `--traco: 2px`
é a borda de contorno, quieto, campo e chip (e transparente no primário,
para os três botões terem a mesma altura empilhados); o primário é
INCLINADO por `clip-path: var(--inclinado)` num `::before` de fundo — o
botão em si continua retângulo, porque `clip-path` no botão cortaria o
anel de foco e a área de toque (`isolation: isolate` + `z-index:
var(--camada-fundo)` põem o fundo atrás do texto sem sair de trás do
botão); o texto do primário é a display em caixa alta a `--texto-xl`, e
o primário pequeno (`btn--sm`, 44 px) volta ao texto porque a display
nunca desce de 20 px; o halo de hover/foco FICA (decisão do dono de
16/09) — o anel traça o retângulo inteiro, inclusive onde o preenchimento
foi cortado, e é o preço de ter o toque inteiro. A nervura
(`--nervura: -14deg`) é `::after` decorativo atrás do texto (`z-index:
var(--camada-fundo)`): no prato (`.today-hero`) nasce no canto inferior
esquerdo, e no título (`.page-head h1`) nasce no canto SUPERIOR esquerdo e
sobe para o respiro acima — a primeira versão nascia na base do `h1` e
cruzava as letras, e nem "atrás" salva legibilidade de um título
riscado. A ponta de folha (`--ponta`) é o `::after` do preenchido da
barra de progresso, na cor da própria barra (`background: inherit`), com
`overflow: visible` na trilha. A aba ativa é `--brand` sem preenchimento,
com a régua de `--traco` em cima. O chip é caixa de contorno em caixa
alta .06em. `config/test_nervura.py` prende tudo isso; a regra
`.page-head h1,
.today-hero` está nessa ORDEM porque `GymReadyTests`
âncora na primeira ocorrência de `
.today-hero,` para achar a régua do
fio de pilar.

**As telas da execução e do placar (NERVURA 3/3, 17/09/2026).** Os dois
heróis da execução são display em caixa alta: o nome do exercício
(`.agora__nome`, já da 1/3) e "SÉRIE 2 DE 4" (`.series__titulo`, `--texto-xl`
800 com o número em `--texto-3xl` 900); o campo de carga (`.registro__carga`)
virou só um sublinhado de `--traco` em `--terra`, com o número em display
900 a `--texto-2xl` e centrado — o foco troca o sublinhado por `--brand`
(`box-shadow: 0 var(--traco) 0`), sem anel em volta, porque a caixa não
existe mais. A régua "a display nunca desce de 20 px" tem um caminho que o
teste das REGRAS não vê: HERANÇA — `.series__faixa` ("6-10 reps", 12,8 px)
mora dentro do herói e saiu na captura em Big Shoulders; `config/test_fontes`
cobra que o filho pequeno declare `var(--font)` de volta. O placar deixou de
ser a folha-lima cheia: `.recompensa` é transparente, sem borda, texto em
`--text`, e a recompensa é a NERVURA que risca — um `::before` só, 14 px de
altura, `clip-path` que desenha a régua de `--traco` E a ponta de folha no
fim, `rotate(var(--nervura)) scaleX(0 → 1)` em `--mov-nervura` (`nervura-
risca`); o número herói (`--texto-heroi`, 72 px, 900, `--brand`) conta do
zero em `--mov-nervura` (`pwa.js` lê o token) e reserva `min-width: 4ch`
porque a Big Shoulders é proporcional e a contagem sacudia a linha; os
pequenos entram em cascata DEPOIS da nervura (`--mov-cascata` × i +
`--mov-nervura`) e os botões chegam parados a 1 s (`aparece`, `steps(1)`).
O `h1` do placar é o nome da sessão + "fechado" (o mockup tinha um
"TREINO FECHADO" genérico; o nome da sessão é o que a pessoa acabou de
fazer). Com `prefers-reduced-motion` a lista é `.recompensa::before` e
`.recompensa .btn` — não `.recompensa`, que já não se move.
Os tempos foram medidos ao vivo por `getAnimations()` no CDP (nervura
600 ms, cascata +600/+680, botões +1000); `nav.py` re-emula a cada comando, então captura
estática de movimento é sempre com `movimento reduzido`.

**Dois achados do QA em produção (18/09/2026), os dois MEDIDOS na tela e
não na tabela.** (1) A barra da semana do Progresso é `--folha` sobre a
TRILHA — `--fio`, uma tinta translúcida composta na superfície —, e esse
par não está na auditoria (que mede gráfico × superfície): no Papel dava
2,97:1; `--papel-folha` foi de #1d833f para #1b7c3b (3,26 sobre a trilha,
3,6 sobre `--surface-3`), e `config/tests.py` passou a compor o fio e
medir o par. (2) A nervura do título sobe ~24 px acima do `h1`; no
`/demo/` a faixa "Ambiente de demonstração … Saiba mais" tinha 16 px de
margem e a ponta entrava 16 px na caixa do link (encostava no sublinhado).
A faixa passou a 40 px (`--espaco-7` + `--espaco-6`): com 32 a ponta caía
exatamente na base da caixa (folga 0, medido), com 40 sobram 8.
`config/test_nervura.py` prende a margem. Os pares que raspam na auditoria
(`--danger`, `--brasa` sobre `--surface-3`) não ocorrem em tela real:
medido, `--danger` só aparece sobre `--surface` (6,76 Ferro / 5,49 Papel)
e sobre a tinta de erro (6,17 / 5,8); `--brasa` só como texto da corrida.
O `agent-browser` estava BLOQUEADO pelo Smart App Control do Windows quando
isto foi feito (o QA foi por `scripts/qa/nav.py` sobre o mesmo Chrome 153);
desde 20/09/2026 o SAC está desligado e os dois rodam — ver "Limites reais
deste ambiente".

## Testes

Nome descreve o comportamento, não o método. Docstring diz **por que** aquilo
importa — de preferência com o caso real que motivou o teste.

Armadilha recorrente neste repositório: **o seletor do JavaScript e o marcador
do HTML são a mesma string.** `assertNotIn("data-x", html)` passa por acidente
porque `data-x` também está dentro do `<script>`. Ancore na classe
(`class="card resumo"`) ou no texto visível.

Contraste é medido, não julgado: `config.tests` recalcula a razão WCAG a partir
dos tokens, inclusive contra os fundos tingidos (`--brand-soft` e companhia).

**A SUÍTE VIVE NUMA QUARTA-FEIRA CONGELADA, E A NOTURNA VIVE NO DIA REAL
(18/09/2026).** `RunnerUnico.setup_test_environment` liga `config/relogio.py`:
`timezone.now()` devolve a HORA real de agora com a DATA local trocada por
`DATA_DA_SUITE` — quarta 16/09/2026, o "pior estado" que `plans/test_stress`
já congelava à mão. Só a data, e só `timezone.now`: o app deriva "hoje" de
`localdate()`/`localtime()`, nunca de `date.today()`, e a hora continua real
e monotônica (`created_at` ordena; `Barrier` e timeouts são de verdade). O
`default=timezone.now` de campo guardou o OBJETO da função na definição da
classe e é trocado à mão — com o cache `_get_default` esquecido, senão a
troca não muda linha nenhuma. Dois incidentes pediram isto: o push de
terça 15/09 que passou e reprovava `plans.test_stress` na quarta, e
`test_a_ficha_de_OUTRO_dia` caindo ao fatiar a suíte noutro dia (18/09) —
a ficha de outro dia mostra a variação da PRÓXIMA ocorrência, que depende
do calendário, e o teste assumia a opção 1. Teste que precisa de outro dia
usa `relogio.congelado_em(dia)` (ou o `mock.patch` de `localdate` que já
usava); teste que precisa do dia de verdade usa `relogio.relogio_real()`;
**teste nunca chama `date.today()`** — com a data congelada ele diverge de
`localdate()` e passa a medir a máquina (achievements, test_movimento e
plans.tests faziam isso e foram convertidos). `NUTRIPLAN_DATA_REAL=1`
desliga o congelamento; `NUTRIPLAN_DATA_DA_SUITE=AAAA-MM-DD` escolhe a
data — é assim que se reproduz o que a noturna achou, ou se varre a
semana atrás de teste que depende do dia. A dependência de calendário que
o congelamento esconde tem dono: `.github/workflows/noturna.yml` roda a
suíte completa toda madrugada (04:20 UTC) com a data real, o log DIZ
"Relógio: DATA REAL" (o fluxo faz `grep`), e uma issue "Suíte noturna
vermelha com a data real" abre ou ganha comentário ao cair e FECHA sozinha
na primeira verde; `simular_falha` no `workflow_dispatch` é o controle
positivo do alerta. O gate (`suite.yml`) NÃO liga o relógio real, e
`config/test_relogio.py` prende as duas metades. O que o gate mede é um
dia só, de propósito: os testes de paridade da ficha de outro dia
(`workouts/test_ficha_unica.py`) escrevem a data dos DOIS ramos — bloco
ímpar → opção 2, bloco par → opção 1 — e cada ramo fica vermelho sozinho
quando `variacao_do_dia` ignora a paridade. E a semana foi VARRIDA antes
de a noturna existir (`NUTRIPLAN_DATA_DA_SUITE` em quarta, segunda, sábado
e domingo): oito testes de `workouts` assumiam que "a sessão de hoje" é a
linha cujo `weekday` é hoje — verdade só nas primeiras posições da semana;
com cinco dias a partir de um sábado a posição 3 é A de novo, e o app
linka a ficha da linha de SEGUNDA. Teste que precisa da sessão de hoje
chama `services.sessao_do_dia(plano, localdate())`, e "outro dia" é outra
LETRA; teste que precisa de uma letra específica usa `tornar_hoje`; a
opção de hoje é `opcao_do_dia`, nunca `da_opcao(1)` fixo. O cron que o #33
tinha posto em `suite.yml` saiu: rodaria congelado e não pegaria dia
nenhum — a noite é da `noturna.yml`.

## Limites reais deste ambiente

- **O `agent-browser` É O PADRÃO DE QA DE NAVEGADOR DE NOVO (20/09/2026),
  e `scripts/qa/nav.py` (CDP) é o FALLBACK.** Histórico em uma linha: de
  14 a 20/09 o Smart App Control bloqueava o binário (`spawn`, evento
  CodeIntegrity 3077) e o `nav.py` foi a única ferramenta; o dono desligou a
  política em 20/09 e o `agent-browser` 0.38.1 voltou — provado em produção
  no mesmo dia: `open` do `/demo/`, `snapshot -i`, `click` num cartão
  (chegou em `/demo/treino/`), `screenshot` a 390 px, `vitals`. O que ele
  dá e o `nav.py` não: `snapshot` com refs para o agente, `a11y` (axe-core),
  `vitals`, `network requests`, `batch`, `set media dark|light`, `set
  offline`, `find role|text|label`. Regras que continuam: sessão própria
  (`AGENT_BROWSER_SESSION`, nova a cada execução de QA — o perfil guarda
  cookies), saída sempre para arquivo e `stdin` fechado (o daemon herda o
  stdout e um pipe espera um EOF que nunca vem), `set viewport` e `set
  media` antes do `open`. O `nav.py <sessão> open|eval|click|type|
  screenshot|viewport|cookie|tema|movimento|rede` fica para o que o
  `agent-browser` não faz — `rede 3g` (latência/banda emuladas para o
  L08), `permissao`, `movimento reduzido` — e para sites de terceiros na
  sessão logada do dono; fala CDP com o MESMO Chrome 153
  (`~/.agent-browser/browsers`). Node 24/npm 11 (WinGet) continuam
  instalados; Lighthouse e Playwright seguem de fora por decisão.
- **O mesmo bloqueio valia para `.pyd` sem assinatura no `.venv` — e
  acabou junto com o SAC.** O fontTools 4.65 vem com seis extensões
  compiladas (`bezierTools`, `cu2qu`, `qu2cu`, `momentsPen`, `iup`,
  `lexer`) e `config/test_fontes.py` errava com "Uma política de Controle
  de Aplicativo bloqueou este arquivo" — três ERROR em todo hook local, e o
  CI (Linux) verde. Os seis `.pyd` foram afastados para
  `*.pyd.bloqueado-sac` em 18/09 (o fontTools caía no Python puro, mesmo
  resultado) e DEVOLVIDOS em 20/09, com o SAC desligado: importam como
  extensão e os 13 testes de `config/test_fontes.py` passam no Windows. O
  `SkipTest` de `win32` (PR #34) fica no teste como guarda — só dispara se a
  extensão não carregar, e hoje ela carrega. O psycopg também: a
  implementação `binary` (`pq.cp312-win_amd64.pyd`) foi bloqueada na manhã
  de 20/09 e voltou à tarde; o `zz_nutriplan_libpq.pth` que a sessão de
  auditoria pôs no `.venv` para o `libpq` 16 fica, porque é inofensivo.
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
- **O SMART APP CONTROL DESTA MÁQUINA FOI DESLIGADO PELO DONO EM
  20/09/2026, e é irreversível** (`VerifiedAndReputablePolicyState = 0`;
  religar exige reinstalar o Windows). De 14 a 20/09 ele bloqueava binário
  sem assinatura com "Uma política de Controle de Aplicativo bloqueou este
  arquivo" (evento CodeIntegrity 3077), e a regra do período — `.pyd`/`.exe`
  não assinado bloqueado → Python puro, nunca remendo no teste — pagou três
  contas: o `agent-browser` (`NotSigned`) não rodava e o QA era `nav.py`
  sobre o Chrome 153 que ele baixou; os `.pyd` do fontTools foram afastados
  do `.venv` compartilhado; e o `psycopg` binário caiu na manhã de 20/09
  (`.pth` do `libpq` 16 como contorno). Tudo isso voltou a carregar no
  mesmo dia, verificado: `agent-browser` abre/lê/fotografa, `nav.py` sobe o
  Chrome 153, `psycopg.pq.__impl__ == "binary"`, os seis `.pyd` do fontTools
  importam. A mudança de configuração de segurança foi do dono, na tela de
  Segurança do Windows — a sessão não a faz nem com autorização; ela só
  verifica depois. Se o sintoma voltar a aparecer, não é o SAC: olhe a
  quarentena do Defender. **A regra "sem remendo no teste" continua valendo
  sem o SAC**: binário que não carrega se resolve na biblioteca (afastar ou
  reinstalar o `.pyd`), nunca com `skip` escrito para a máquina passar. O
  `skip` de `config/test_fontes.py` (`win32`) continua no teste como guarda,
  hoje sem gatilho; no CI (Linux) a extensão que não carrega é FALHA.
- **Nenhum processo de fundo abre janela, e todo processo de fundo nasce em
  `scripts/fundo.py`.** No Windows 11 o Windows Terminal hospeda todo console
  novo — e um processo sem console (os do Claude Code, o Agendador) que lança
  `powershell`, `cmd /c` ou `start` cria um console novo, que é uma janela na
  tela do dono. Foi assim em 16/09/2026: a tarefa `NutriPlan lembretes` abria
  um PowerShell vazio a cada 5 minutos, e `-WindowStyle Hidden` não evitava,
  porque o PowerShell lê a flag depois que o console dele já existe.
  `fundo.py rodar` lança com `CREATE_NO_WINDOW` (console que nunca aparece e
  os netos herdam — não `DETACHED_PROCESS`, que dá console nenhum e faz o
  primeiro neto de console abrir janela); `fundo.py notificar` toca por
  `winsound` e avisa por `pythonw`. `config/test_janela_de_fundo.py` varre
  `scripts/`, `artifacts/`, `.superpowers/` e as skills e fica vermelho com
  qualquer chamada dessas fora do `fundo.py`.
## Deploy

**O GATE É O CI, E NINGUÉM EMPURRA EM `main` (17/09/2026).** Um push chegou
ao GitHub naquele dia sem passar pelo reflog de nenhuma sessão desta
máquina; um gate que só existe numa máquina não é gate, porque ninguém
consegue conferir se ele rodou. Desde então:

- **DOIS fluxos desde 18/09/2026, e o gate é o RÁPIDO.** A suíte inteira,
  serial, executava em ~31 min (medido nos últimos 10 runs: instalar ~10 s
  com cache, o resto é o `manage.py test`), e com a fila local cada PR
  esperava ~32 min de runner. `suite-rapida.yml` (check **"suíte rápida"**)
  é o GATE: a suíte FATIADA em 5 por `ci/shard.py` (um job por fatia, cada
  um SERIAL, os jobs em paralelo), `--exclude-tag lento`. **Não** usamos
  `--parallel` do Django: ele roda cada processo com um clone do banco, mas
  a suíte tem teste que assume ORDEM de PK, e no CI (PR #33, Linux) UM caiu
  e o runner morreu com `cannot pickle 'traceback'`, escondendo a falha —
  fatiar mantém cada fatia idêntica ao verde serial de sempre. `ci/shard.py`
  descobre TODO módulo versionado e reparte equilibrado (peso por linhas, e
  peso extra para quem semeia um ano); `config/test_ci.py` cobra que a
  partição não deixa módulo órfão (um módulo em nenhuma fatia nunca rodaria
  no gate). O check é o job `gate` ("suíte rápida"), verde só se TODAS as
  fatias passam. Roda em todo PR, alvo < 10 min. `suite.yml` (check
  **"suíte completa"**) roda as MESMAS fatias com TUDO, inclusive `lento`,
  DEPOIS do merge (`push: main`), à noite (`schedule` 06:00 UTC) e à mão
  (`workflow_dispatch`) — não barra PR. Os dois: Postgres 16 (produção), sem
  segredo, `contents: read`, cada fatia sobe seu log e `--durations 15`.
  **`@tag("lento")` é só para teste pesado que NÃO é o único guarda de algo
  crítico** (concorrência, dourado, idempotência, segurança ficam no rápido
  mesmo quando custam) — cada um movido está justificado no relatório;
- **NÃO HÁ GATE NO SERVIDOR: o repositório é PRIVADO** e a API do GitHub
  devolve **403 "Upgrade to GitHub Pro or make this repository public"**
  para branch protection E para rulesets (conferido em 18/09/2026 — a
  afirmação antiga de "branch protection pela API, strict, enforce_admins"
  estava errada, e o "repositório público, minutos ilimitados" idem). O
  único gate é COOPERATIVO: `scripts/github.py enfileirar`/`esperar` esperam
  o check `CHECK` (= "suíte rápida") ficar verde antes de mergear pela API.
  Ninguém deve chamar `merge` à mão. E porque é privado, **minuto de Actions
  é metered** (~2000/mês no free): PR de 32 min era espera E custo — mais uma
  razão para o gate rápido, e para a completa não rodar em todo PR;
- **A FILA DE MERGE DO GITHUB NÃO EXISTE EM REPOSITÓRIO DE CONTA PESSOAL
  (17/09/2026)** — a API devolve 422/403. A resposta é a FILA LOCAL:
  `scripts/github.py enfileirar <n>` põe uma senha em
  `C:\Users\biel-\nutriplan-fila\` (fora de qualquer worktree, uma por PR,
  em ordem de chegada), e a sessão da vez faz o laço merge de `main` na
  branch → push → **espera "suíte rápida" do head certo (`esperar --sha`)**
  → merge, enquanto as outras esperam. Posse abandonada (90 min) é liberada
  sozinha. **O laço roda num WORKTREE PRÓPRIO e descartável (18/09/2026), não
  na árvore da sessão** — `git worktree add --detach` no head remoto da
  branch, merge/push/merge lá, `git worktree remove` no fim —, então a sessão
  NÃO precisa estar com a branch em HEAD e SEGUE trabalhando enquanto a fila
  anda (antes o `enfileirar` travava a árvore da sessão até a fila terminar).
  O push do worktree é `--no-verify`: o pre-push é o atalho LOCAL e redundante
  ali (o gate é o check do CI que a fila espera sobre o mesmo SHA, e a árvore
  do worktree já é a que sobe). O ruleset com a fila do GitHub
  (`corpo_da_fila`, `fila-ativar`) e o gatilho `merge_group` ficam PRONTOS
  para o dia em que o repositório morar numa organização (ou virar público) —
  decisão do dono;
- **Se a "suíte completa" quebrar** (pós-merge ou no cron noturno): foi um
  `lento` que regrediu no merge que acabou de entrar OU algo que depende de
  calendário. O GitHub manda e-mail ao dono por run vermelho no branch
  padrão (é o alerta, sem segredo de webhook). Conserte ou reverta o merge
  culpado; o gate rápido não pega `lento`, então a correção também passa
  rápido. Rodar a completa à mão: `workflow_dispatch` na aba Actions;
- o fluxo é **branch → PR → `enfileirar` (espera a vez, atualiza, espera o
  check, mergeia) → `/saude/`**. Sem `gh` nesta máquina, o helper é
  `scripts/github.py` (`pr`, `status`, `esperar`, `enfileirar`, `fila`,
  `fechar`, `protecao`; `merge` à mão só fora da fila, e é o que cria a
  corrida), com o token do Git Credential Manager — nunca impresso, nunca
  em argumento;
- o `pre-push` local virou ATALHO: no worktree descartável do SHA que sobe,
  `config` + teste dourado + doutrina + gate por letra + orçamentos, em
  poucos minutos; `NUTRIPLAN_SUITE_COMPLETA=1` roda tudo localmente como
  antes. `config/test_ci.py` prende o contrato dos dois fluxos, do hook e do
  helper.

O merge em `main` dispara o Render. `scripts/build.sh` roda collectstatic →
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

## O que existe no Render (inventário de 16/09/2026, sem valores)

Um workspace ("My Workspace"), região **Oregon**, e a chave de API
`nutriplan-claude-code` fora do repositório (`RENDER_API_KEY` no ambiente da
máquina e `~/.nutriplan-secrets/render_api_key`). `scripts/render_api.py`
fala com a API sem imprimir valor nenhum: `inspect` (serviços e NOMES das
variáveis), `env`, `cron`, `deploy`, `trigger`, `runs`, `logs`, `status`.

- **Web service `nutriplan`** (`srv-da6f5kou01pc73fsfkqg`): plano **free**,
  deploy automático de `main`, build em `scripts/build.sh`, healthcheck
  `/saude/`. Variáveis, por nome: `DATABASE_URL` (Neon — o banco do Render
  é só rollback), `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
  `DJANGO_EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`,
  `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` (Brevo, 2525),
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `PYTHON_VERSION`,
  `WEB_CONCURRENCY` e, desde 16/09/2026, `VAPID_PUBLIC_KEY`,
  `VAPID_PRIVATE_KEY`, `VAPID_ADMIN_EMAIL` (par em
  `~/.nutriplan-secrets/vapid/`; a pública começa com `BPpbVTBznicK`). Com
  elas o cartão "Lembretes" aparece e a assinatura push é gravada — provado
  em produção com conta descartável e Chrome real: `/push/inscrever/` 200,
  FCM 201, notificação exibida.
- **Lembretes SEM cron e SEM nada pago (decisão do dono, 16/09/2026).** A
  criação do cron pela API respondeu `402 Payment information is required`
  (custaria no mínimo US$ 1/mês), e a instância web continua `free`.
- **Quem DISPARA lembrete com PONTUALIDADE é o UptimeRobot (18/09/2026), e o
  `schedule` do Actions é FALLBACK.** O `schedule` do GitHub atrasa e PULA —
  MEDIDO em 18/09: ~9 rodadas em 31 h (intervalos de 2 a 5,5 h), então o
  lembrete saía a cada ~4,4 h em vez de 5 min. O primário passou a ser um
  segundo monitor do UptimeRobot em `GET /tarefas/lembretes/externo/<token>/`
  (a cada 5 min, pontual). O UptimeRobot free só manda GET/HEAD e SEM
  cabeçalho, então o token vai na URL (`NUTRIPLAN_DISPARO_TOKEN`, SEPARADO do
  Bearer do POST): `config/observabilidade.py` o redige do log do Django, mas
  ele APARECE no log de ACESSO do Render — por isso é de baixo dano (só
  dispara lembretes vencidos, idempotente, com limite de taxa de
  `INTERVALO_MINIMO_EXTERNO`). A rota é `push.views.DisparoExternoView` (GET,
  503 sem a variável, 403 com token errado; loga user-agent e origem, nunca o
  token). O `schedule` continua no `POST /tarefas/lembretes/`
  (`TarefaLembretesView`, Bearer `NUTRIPLAN_TAREFAS_TOKEN`) como FALLBACK: o
  `push/tarefas.py` SE ABSTÉM (`rodar(externo=False)`) quando um disparo
  externo cuidou há menos de `RESERVA_DO_FALLBACK` (4 min) — assim o pontual
  manda e o `schedule` só assume se o UptimeRobot cair. A memória do último
  externo é por PROCESSO (dois workers) e some no restart; errar dá no
  máximo uma rodada redundante, que a constraint do `NotificationLog` torna
  inofensiva.

- **Quem MANTÉM ACORDADO é o UptimeRobot (17/09/2026), não o Actions.** Um
  monitor HTTP(s) gratuito — conta `bielpointblank@gmail.com`, monitor
  "NutriPlan vivo" (`dashboard.uptimerobot.com/monitors/804021213`) — bate em
  `GET /saude/vivo/` a cada 5 minutos (o mínimo do plano free) e alerta por
  e-mail se cair. `/saude/vivo/` NÃO consulta o banco, de propósito: um
  monitor em `/saude/` acordaria o Neon o tempo todo e a cota de 100 CU-h
  estouraria no meio do mês (ver "Monitor externo bate em `/saude/vivo/`").
  Antes disso o "manter acordado" era um LAÇO de ~5h45 dentro da rodada do
  Actions que se re-disparava sozinho (`GITHUB_TOKEN`, `actions: write`) — a
  "corrente"; com o UptimeRobot ela perdeu a razão e saiu (o fluxo voltou a
  ser uma rodada por disparo do `schedule`). A chave do UptimeRobot, se um
  dia a API for usada, mora só no ambiente da máquina (`API Settings` no
  painel), nunca no repositório.

**A infraestrutura é 100 % gratuita — Render free + Neon free + GitHub
Actions + UptimeRobot free —, e isso implica três coisas escritas:**

- **três responsabilidades, e o UptimeRobot cuida de duas (18/09/2026).**
  MANTER ACORDADO é do UptimeRobot em `/saude/vivo/` (monitor "NutriPlan
  vivo"); DISPARAR LEMBRETE, com pontualidade, é do UptimeRobot em
  `/tarefas/lembretes/externo/<token>/` (um segundo monitor); e o `schedule`
  do Actions em `POST /tarefas/lembretes/` é o FALLBACK. Os dois monitores
  batem de 5 em 5 min (o mínimo do free) e alertam por e-mail. Por que o
  UptimeRobot e não o `schedule` para disparar: o `schedule` do GitHub ATRASA
  e PULA (MEDIDO em 17 e 18/09), e lembrete precisa de pontualidade. **Se um
  dos monitores cair** (o e-mail avisa): reative no painel; enquanto isso, o
  `schedule` (fallback) assume os lembretes quando não vê disparo externo há
  > 4 min, e o `POST` do lembrete acaba acordando o web. **Se o `schedule` do
  Actions parar** (repositório sem atividade por 60 dias, ou pane): os
  lembretes param só se o UptimeRobot TAMBÉM estiver fora; `workflow_dispatch`
  na aba Actions dispara à mão, e um commit religa o `schedule`;
- **o Neon dorme entre refeições, de propósito.** Uma consulta a cada 5 min
  o manteria acordado o dia inteiro (182 CU-h contra 100 de cota). Por isso
  a tarefa, depois de rodar, calcula a próxima refeição de quem tem
  assinatura e responde `{"pausada": true}` sem banco até 20 min antes dela
  (ou até 30 min, o que vier primeiro — assinatura nova entra na conta em no
  máximo meia hora). A pausa é por processo (dois workers) e some no
  restart. O ping de manter acordado NUNCA usa `/saude/`;
- **dependência da política do free.** Render pode mudar o tempo de sono,
  as horas gratuitas (750 h/mês por workspace hoje) ou bloquear o ping;
  UptimeRobot pode mudar o mínimo de 5 min do plano free ou o número de
  monitores; GitHub pode desligar o `schedule` de repositório sem atividade
  por 60 dias (ele avisa por e-mail) e atrasa ou pula o cron sob carga; o
  Neon pode reduzir a cota. Nada disso quebra o app — só os lembretes e o
  cold start, e cada um tem o seu dono para reativar.

**O que mudaria se um dia virar pago:** instância `starter` no Render
(~US$ 7/mês) elimina o sono, e aí o UptimeRobot vira só alerta de queda; o
cron do Render (≥ US$ 1/mês, `scripts/render_api.py cron`, bloco de exemplo
no histórico do `render.yaml` até 16/09) substituiria o `schedule` do Actions
com relógio exato — e a janela de 15 min poderia voltar a 10, e o lembrete
deixaria de atrasar; o Neon pago tira o teto de CU-h e a pausa de
`push/tarefas.py` viraria só economia. Nenhuma dessas trocas exige código
novo além de apagar o que existe para contornar o gratuito.

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