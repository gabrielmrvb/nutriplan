# O prompt original do autor (@matheusgomes), nas quatro partes

Copiado verbatim em 15/09/2026 do comentário fixado e das três respostas dele
no Reel https://www.instagram.com/p/DdM5PxOTBRe/ ("Construa os projetos mais
lindos do mundo — Parte 2/2"). É o texto que o
[`PROMPT-MESTRE-NUTRIPLAN-CLAUDE-DESIGN.md`](PROMPT-MESTRE-NUTRIPLAN-CLAUDE-DESIGN.md)
do ChatGPT adaptou. O autor escreveu para um projeto React + Vite + Tailwind
(`convertechat-web`), e o texto presume isso — Tailwind, shadcn/ui,
typecheck, "componentes tipados".

---

## Prompt (Parte 1)

Na raiz deste projeto tem a pasta `design-system-export`, um dump cru do Claude Design com o design system completo. Não é um pacote limpo: tem código de verdade, tem artefato interno da ferramenta, e provavelmente tem versões duplicadas do mesmo componente em pastas diferentes. Sua tarefa é triar, reorganizar tudo numa pasta nova `design-system`, incorporar ao projeto, deixar a documentação do repositório em ordem, e só no fim apagar `design-system-export`.

Execute tudo de ponta a ponta sem pedir aprovação. Monte o plano internamente e siga com ele. Não me faça perguntas intermediárias, não pare para confirmar decisões, não espere ok em nenhum momento. Quando houver ambiguidade, tome a decisão mais conservadora — a que preserva o que já existe no projeto — e registre a escolha no relatório final. Só interrompa se algo impedir fisicamente a conclusão da tarefa.

### 1. Triagem do dump

Leia a pasta inteira antes de escrever qualquer coisa e classifique cada arquivo em:

- canônico: a versão mais completa e recente de cada componente, tela, template, token, guideline e asset
- derivado ou duplicado: versões antigas, exports aninhados, cópias do mesmo componente em pastas diferentes
- interno da ferramenta: bundles, manifests, thumbnails, uploads e afins

Quando o mesmo componente aparecer em mais de um lugar, compare de fato e escolha a versão com mais variantes e estados — não a primeira que encontrar. Só o grupo canônico entra no projeto. Anote os conflitos e a escolha de cada um para o relatório.

Dois itens são fáceis de descartar por engano e não podem se perder: qualquer `DESIGN.md` no padrão Google Labs / Stitch, que é a fonte da verdade dos tokens e precisa ser resgatado mesmo que esteja numa subpasta; e qualquer config de lint de aderência ao design system, que deve ser integrada à config de lint do projeto.

Preserve também os HTMLs de referência visual que existirem no dump. Não viram componente, mas eu quero continuar podendo abri-los no navegador depois que a pasta original for apagada — mova para dentro de `design-system`, em subpasta própria de referência, ajustando caminhos de assets para que continuem renderizando sozinhos.

## Prompt (Parte 2)

### 2. Diagnóstico do projeto

Descubra o terreno real: se o projeto é novo ou já tem código, framework e versões realmente instaladas, se Tailwind e shadcn/ui já existem e em qual versão, como as fontes são carregadas, se há tema claro/escuro, onde a estilização mora. Cheque no repositório e na documentação atual das ferramentas — não assuma de memória, as convenções mudam entre versões.

### 3. Diagnóstico da documentação

Varra a raiz e as pastas de docs e levante todo arquivo Markdown de contrato que já existe. Use como referência de busca os nomes que costumam aparecer — DESIGN.md, AGENTS.md, CLAUDE.md, PRODUCT.md, ARCHITECTURE.md, CONTRIBUTING.md, README.md, docs/* — mas não se limite a eles: qualquer Markdown que funcione como contrato ou instrução no projeto entra no levantamento, tenha o nome que tiver.

Em paralelo, verifique qual é hoje a convenção corrente para arquivos de instrução de agentes e documentação de repositório — o que as ferramentas de agente leem por padrão, qual arquivo virou padrão de fato, se algum foi substituído ou deprecado, e como os projetos organizam isso atualmente. Não confie na sua memória para isso; confirme antes de mudar qualquer coisa.

Com o levantamento e a convenção em mãos, decida para cada arquivo:

- existe e está no padrão → merge: preserva tudo que já está lá e acrescenta ou atualiza só a parte de design system
- existe mas está fora do padrão atual → renomeia, consolida ou aponta para o canônico, carregando o conteúdo antigo junto, sem perder nada
- não existe e é necessário → cria
- não existe e não faz sentido para este projeto → não cria, e registra o porquê

Considere o tamanho e a natureza do projeto: não imponha uma estrutura de documentação grande demais para o que ele é. Na dúvida entre reorganizar e apenas acrescentar, acrescente.

## Prompt (Parte 3)

### 4. Aplicação

Crie `design-system` e porte para lá tudo do grupo canônico, adaptado à stack real deste projeto: componentes de verdade, tipados, com todas as variantes e estados preservados (default, hover, active, focus, disabled, loading, erro, vazio, selecionado); os padrões de composição e templates; os assets; os tokens; as guidelines. Se o dump tinha vinte componentes, o projeto termina com vinte. Nada de reduzir a biblioteca a tokens.

Crie uma rota de showcase (algo como `/design-system`) que renderize a biblioteca inteira, todos os estados e ambos os temas.

Se o projeto já tem código, integre em vez de duplicar: onde já existe componente equivalente, uma versão só sobrevive, e valores de cor, fonte, espaçamento e raio hardcoded viram tokens. Incremental e rastreável, sem reescrever componente inteiro sem necessidade. Se o projeto é novo, deixe a base pronta para tudo daqui pra frente nascer dentro do sistema.

### 5. Documentação

Execute o que você decidiu no passo 3, com uma regra inegociável: nunca sobrescreva arquivo existente. Leia o conteúdo atual, preserve integralmente tudo que não é sobre design system, e insira ou atualize apenas a parte que me interessa aqui, mantendo o estilo e a estrutura de quem escreveu antes. Se houver seção de design desatualizada, substitua só ela. Se um arquivo for renomeado ou consolidado, o conteúdo antigo vai junto — nada se perde no caminho.

Independente do formato que o projeto adote, ao final estas informações precisam estar registradas em algum lugar que os agentes leiam:

- o DESIGN.md na raiz, versionado, é o contrato visual e a fonte da verdade dos tokens
- componentes novos saem da biblioteca em `design-system`, e nenhum valor de cor, fonte, espaçamento ou raio vai hardcoded no código
- o mapa da biblioteca: o que tem em cada subpasta, onde ficam os HTMLs de referência, e como criar um componente novo dentro do sistema

Não crie arquivo por criar. Se algo não faz sentido para este projeto, deixe de fora e registre o porquê no relatório.

## Prompt (Parte 4)

### 6. Validação

Instale as dependências, rode build, typecheck e lint, abra a rota de showcase e confirme que renderiza, e confirme que os HTMLs de referência abrem a partir do novo caminho. Conserte o que falhar e rode de novo até passar — não me entregue com erro pendente nem peça ajuda para resolver.

Só depois de tudo validado, apague `design-system-export` inteira.

### 7. Relatório final

Entregue de uma vez só, no fim:

- o que foi instalado e o que mudou no projeto
- quantos componentes foram portados contra quantos existiam no dump
- quais conflitos de duplicata apareceram e qual versão venceu em cada um
- a lista completa dos Markdown de contrato encontrados no projeto e o destino de cada um (merge, renomeado, consolidado, criado ou deixado intacto)
- quais decisões ambíguas você tomou sozinho
- o que ficou de fora e por quê
