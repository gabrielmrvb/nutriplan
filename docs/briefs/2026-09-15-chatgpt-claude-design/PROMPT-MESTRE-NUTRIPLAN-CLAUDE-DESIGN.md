# Prompt mestre — Claude Design + Superpowers + Agent Browser no NutriPlan

> Cole este prompt no **Claude Code aberto na raiz do repositório do NutriPlan**, somente depois de colocar na raiz o export real do Claude Design com o nome `design-system-export`.

---

Você está trabalhando no repositório real do **NutriPlan**, um aplicativo mobile-first de alimentação, treino, hidratação, progresso e corrida. Sua missão é transformar o export bruto criado no Claude Design em um design system canônico, incorporá-lo com segurança ao aplicativo existente, melhorar as telas reais e validar toda a experiência navegando no produto.

Execute o trabalho completo de ponta a ponta. Não espere aprovações intermediárias e não devolva apenas recomendações, mockups ou um plano. Investigue, planeje, implemente, teste, corrija e entregue o resultado validado.

## 0. Resultado obrigatório

Ao terminar, o projeto deverá ter:

1. Um único design system canônico e versionado, integrado à stack real do NutriPlan.
2. Componentes reutilizáveis com variantes e estados completos.
3. Tokens visuais aplicados ao produto, evitando valores arbitrários espalhados.
4. Documentação preservada e atualizada sem apagar contratos existentes.
5. Uma rota interna de showcase que apresente a biblioteca visual.
6. As telas prioritárias do NutriPlan migradas de forma incremental para o novo sistema.
7. Navegação e fluxos essenciais funcionando em celular.
8. Auditoria real feita com Agent Browser, incluindo cliques, formulários, rolagem, estados e regressões.
9. Build, testes, lint e demais verificações existentes passando.
10. A pasta bruta `design-system-export` removida somente depois de toda a validação.
11. Um relatório final objetivo, com evidências e decisões tomadas.

## 1. Regras de operação autônoma

- Comece inspecionando o repositório, as instruções locais e o estado do Git.
- Leia integralmente todos os `AGENTS.md`, `CLAUDE.md`, `DESIGN.md` ou arquivos equivalentes aplicáveis antes de editar.
- Preserve alterações preexistentes do usuário. Não reverta, sobrescreva nem reorganize trabalho que não pertence a esta missão.
- Não use comandos destrutivos para “limpar” o repositório.
- Não force uma stack nova, um framework novo ou uma arquitetura nova sem necessidade demonstrável.
- Diante de ambiguidade, escolha a alternativa mais conservadora: preservar comportamento, dados, compatibilidade e histórico.
- Registre no relatório final as decisões ambíguas tomadas autonomamente.
- Não declare sucesso por aparência. Todo resultado deve ter evidência de arquivo, teste e navegação real.
- Não invente o conteúdo ausente. Se `design-system-export` não existir, estiver vazio ou não for um export utilizável, pare apenas por esse impedimento físico e informe exatamente o que falta. Não crie uma pasta falsa para simular a entrada.
- Nunca exponha, imprima ou versione segredos, tokens, credenciais ou dados pessoais.

## 2. Uso obrigatório do Superpowers

Use o Superpowers como disciplina de execução, aproveitando os recursos realmente instalados no ambiente. Descubra as skills disponíveis em vez de inventar nomes ou comandos.

O processo deve cobrir, por meio das skills equivalentes disponíveis:

1. entendimento do problema e das restrições;
2. elaboração de um plano executável por fases;
3. execução disciplinada do plano;
4. desenvolvimento orientado a testes quando aplicável;
5. investigação sistemática de defeitos;
6. verificação antes de qualquer alegação de conclusão;
7. revisão adversarial ou revisão de código antes da entrega.

Não transforme o uso do Superpowers em uma pausa para perguntar o que fazer. Faça o raciocínio internamente, registre o plano no formato previsto pelo ambiente e avance. Se uma skill recomendar perguntas opcionais, responda com base no repositório, no produto atual e na decisão conservadora.

## 3. Uso obrigatório do Agent Browser

O Agent Browser é obrigatório para compreender e validar o aplicativo real. Use a ferramenta de navegador disponível no ambiente e siga suas instruções próprias. Não substitua a navegação por leitura de templates nem por testes unitários.

O navegador deve ser usado em três momentos:

### 3.1 Baseline antes das alterações

Percorra o aplicativo atual e registre:

- estrutura de navegação;
- telas, modais, drawers, menus, formulários e accordions;
- estados vazios, carregando, sucesso, erro, bloqueado e desabilitado;
- hierarquia visual, espaçamento, tipografia, contraste e consistência;
- animações, transições, feedback de toque e comportamento durante rolagem;
- problemas de overflow, elementos cortados, saltos de layout e conteúdo duplicado;
- pontos onde uma área obriga o usuário a entrar desnecessariamente em outra;
- componentes equivalentes implementados de formas diferentes.

Teste principalmente os viewports:

- `360 × 800`;
- `390 × 844` como referência principal;
- `430 × 932`;
- um desktop apenas como verificação de sanidade, pois o produto é mobile-first.

Não faça alterações externas desnecessárias durante o baseline. Use conta de QA ou demo apropriada e preserve contas reais.

### 3.2 Verificação durante a implementação

Após cada conjunto coerente de telas:

- abra as páginas afetadas;
- confira estado inicial e estados interativos;
- teste teclado, foco e retorno de foco onde aplicável;
- teste rolagem para cima e para baixo;
- confirme que drawers e modais travam e restauram a rolagem corretamente;
- confirme que animações não causam tremor, reposicionamento indevido ou enjoo;
- verifique `prefers-reduced-motion`;
- procure erros no console e requisições com falha;
- corrija antes de avançar.

### 3.3 Regressão completa no final

Navegue por 100% das rotas e controles alcançáveis pelo perfil de QA. “100%” significa inventário rastreável: cada item clicável deve aparecer no relatório como testado, não aplicável ou bloqueado com motivo concreto.

## 4. Inventário e triagem do export

Leia a árvore completa de `design-system-export` antes de escrever no projeto. Gere um inventário temporário contendo caminho, tipo, tamanho, hash quando útil, função provável e classificação.

Classifique cada item em uma destas categorias:

- **canônico:** versão mais completa e atual de componente, tela, template, token, guideline ou asset;
- **derivado/duplicado:** cópia, versão antiga, export aninhado ou variação inferior de algo canônico;
- **interno do Claude Design:** bundle, cache, manifesto interno, thumbnail, upload intermediário ou arquivo sem função no produto;
- **referência visual:** HTML, imagem ou material que deve permanecer consultável, mas não virar componente de produção;
- **incerto:** item que precisa de comparação adicional antes de uma decisão.

Quando houver duplicatas:

1. compare conteúdo e não apenas nome ou data;
2. considere variantes, estados, acessibilidade, responsividade e completude;
3. escolha a versão com maior cobertura útil e melhor compatibilidade com o projeto;
4. registre todas as disputas e o vencedor;
5. nunca leve duas implementações equivalentes para a base final.

Itens que não podem ser descartados por engano:

- qualquer `DESIGN.md` ou contrato visual equivalente, inclusive em subpastas;
- configuração de lint ou validação de aderência visual;
- tokens, fontes, ícones e assets utilizados por versões canônicas;
- HTMLs de referência visual.

Mova os HTMLs selecionados para uma subpasta apropriada dentro de `design-system/references`. Ajuste caminhos relativos de CSS, JavaScript, fontes e imagens para que continuem abrindo depois da remoção do export bruto. Não transforme esses HTMLs automaticamente em código de produção.

## 5. Diagnóstico da stack real

Antes de portar componentes, descubra e documente a realidade do repositório:

- linguagem, framework, renderização e versões instaladas;
- estrutura de templates, componentes e assets;
- pipeline de CSS e JavaScript;
- existência e versão de Tailwind, shadcn/ui ou bibliotecas equivalentes;
- forma de carregamento das fontes;
- sistema atual de ícones;
- tema claro/escuro e preferências do sistema;
- breakpoints, tokens e convenções já existentes;
- autenticação, rotas públicas e privadas;
- testes disponíveis e comandos oficiais;
- PWA, cache, service worker e implicações de atualização;
- processo de build, deploy e health check;
- compatibilidade exigida pelos navegadores móveis usados pelo produto.

Confirme no código e na documentação oficial da versão instalada. Não aplique convenções de memória que pertençam a outra versão.

Se o export usar React, Tailwind ou shadcn, mas o projeto real usar outra stack, traduza os conceitos visuais e comportamentais para a stack existente. Não introduza um segundo frontend apenas para aproveitar o export.

## 6. Diagnóstico da documentação

Varra a raiz e as pastas de documentação. Catalogue todos os arquivos Markdown que funcionem como contrato ou instrução, incluindo nomes convencionais e nomes específicos do projeto.

Para cada arquivo, decida e registre uma destas ações:

- preservar sem alteração;
- fazer merge de uma seção específica;
- atualizar uma seção desatualizada;
- consolidar mantendo integralmente o conteúdo útil;
- criar porque é necessário e inexistente;
- não criar porque seria excesso para o tamanho do projeto.

Regras:

- nunca sobrescreva um documento inteiro para adicionar regras de design;
- preserve conteúdo não relacionado ao design system;
- não crie documentação duplicada;
- mantenha o estilo e a estrutura do repositório;
- se houver referências cruzadas, atualize-as;
- determine qual contrato os agentes do repositório realmente leem e coloque nele um resumo operacional do design system.

Ao final, o repositório deve registrar claramente:

- qual arquivo é a fonte da verdade visual;
- onde ficam tokens, componentes, padrões, assets e referências;
- como criar ou alterar um componente;
- como executar a rota de showcase;
- proibição de cores, fontes, espaçamentos e raios arbitrários quando houver token equivalente;
- processo mínimo de validação visual.

## 7. Construção do design system canônico

Crie `design-system` de acordo com a arquitetura real do projeto. A pasta não precisa reproduzir cegamente a estrutura do export; ela deve ser compreensível, estável e adequada à stack encontrada.

Porte todo o conjunto canônico. Se existirem N componentes canônicos úteis no export, a entrega deve explicar o destino dos N. Não reduza uma biblioteca completa a uma paleta de cores.

Preserve e implemente, quando aplicável:

- default;
- hover;
- pressed/active;
- focus e focus-visible;
- disabled;
- loading;
- skeleton;
- success;
- warning;
- error;
- vazio;
- selecionado;
- expandido/recolhido;
- conteúdo curto, longo e quebrado;
- diferentes densidades ou tamanhos previstos;
- tema claro e escuro, somente se realmente fizerem parte do produto/export.

Garanta:

- semântica HTML adequada;
- navegação por teclado;
- foco visível;
- nomes acessíveis;
- contraste coerente com WCAG;
- áreas de toque confortáveis em celular;
- responsividade sem overflow horizontal;
- animações com propósito e alternativa de movimento reduzido;
- componentes tipados quando a stack oferecer tipagem;
- nenhuma dependência copiada sem necessidade.

## 8. Tokens e identidade do NutriPlan

O resultado precisa parecer um produto de nutrição e treino maduro, não um CRM genérico, cassino, jogo infantil ou painel corporativo frio.

Preserve a identidade reconhecível do NutriPlan e refine-a com base no export:

- verde principal e verde de ação coerentes com a marca;
- fundos claros confortáveis;
- hierarquia forte, porém limpa;
- sensação de saúde, energia, confiança e progresso;
- cards e superfícies com profundidade controlada;
- tipografia muito legível em celular;
- iconografia consistente;
- dados e metas apresentados sem excesso visual;
- gamificação discreta e adulta, baseada em progresso real, sequência, metas e conquistas úteis;
- motion curto, funcional e consistente.

Defina tokens semânticos, não apenas valores crus. Cubra pelo menos:

- cores de canvas, superfície, texto, borda, ação e estados;
- tipografia e escala;
- espaçamento;
- raios;
- sombras;
- tamanhos mínimos de toque;
- motion: duração, easing, distância e stagger;
- camadas/z-index;
- largura de conteúdo e breakpoints relevantes.

Se já houver tokens equivalentes, faça merge e migração incremental. Não crie duas fontes da verdade.

## 9. Showcase obrigatório

Crie uma rota interna como `/design-system` ou o equivalente correto na stack. Proteja-a conforme as convenções do projeto se ela não deve ser pública.

A página deve renderizar:

- todos os tokens principais;
- todos os componentes canônicos;
- variantes e estados relevantes;
- conteúdo curto e longo;
- exemplos em largura estreita;
- estados de formulário;
- estados vazios, carregamento e erro;
- padrões de navegação;
- motion e opção de movimento reduzido;
- temas existentes.

Ela deve consumir os componentes reais, não duplicações feitas exclusivamente para documentação.

## 10. Estratégia de integração no NutriPlan

Não faça uma reescrita big bang. Migre por fundações e fluxos, mantendo o aplicativo utilizável após cada etapa.

Ordem recomendada, ajustável somente com justificativa técnica:

1. tokens, fontes, ícones e primitivas;
2. botões, inputs, seletores, feedbacks e estados;
3. navegação global e estrutura de página;
4. autenticação e cadastro;
5. onboarding de três etapas;
6. tela inicial e visão “Hoje”;
7. Alimentação e hidratação;
8. Treino e execução de exercícios;
9. Progresso;
10. Áreas e Perfil;
11. Corrida;
12. estados raros, erros e telas auxiliares.

Onde já existir componente equivalente:

- compare as implementações;
- preserve contratos públicos e comportamento válido;
- escolha um único componente sobrevivente;
- migre consumidores progressivamente;
- elimine a duplicação apenas depois da migração e dos testes.

## 11. Requisitos específicos do NutriPlan

### 11.1 Navegação

A navegação principal mobile deve seguir a arquitetura vigente aprovada no projeto. Considere como referência a barra:

- Alimentação;
- Treino;
- Progresso;
- Áreas.

Perfil pertence a Áreas, e itens já presentes na barra principal não devem aparecer duplicados dentro de Áreas. Antes de aplicar, confirme no código e nas decisões documentadas se essa arquitetura já foi implementada ou substituída por decisão posterior.

### 11.2 Login, cadastro e onboarding

- A entrada deve comunicar imediatamente o valor do NutriPlan.
- Evite uma tela genérica baseada apenas em logo, campos e botão.
- Preserve rapidez, legibilidade e confiança.
- O cadastro e o onboarding devem ter progresso claro, validação próxima do campo e recuperação de erro.
- Teste teclado móvel, autofill, campos longos, voltar e avançar.
- Não adicione perguntas sem impacto real na personalização.

### 11.3 Alimentação e “Hoje”

- Separe visualmente resumo do dia, refeições, hidratação, metas e ações.
- Evite transformar Alimentação em atalho confuso para funcionalidades de Treino.
- Dê a cada informação um lugar previsível.
- Reduza repetição, ruído e cartões sem função.
- Ações destrutivas, como zerar água, devem ser claramente diferenciadas e protegidas de toque acidental.

### 11.4 Treino

- A tela principal deve priorizar os cards dos treinos disponíveis, sem despejar imediatamente a lista inteira de exercícios.
- O fluxo esperado é: escolher/iniciar treino → abrir ficha do treino → selecionar ou executar exercício.
- O vídeo correto deve abrir no contexto da execução, com apenas um player ativo.
- Preserve estado do treino quando drawers, modais ou vídeos forem abertos e fechados.
- Não reintroduza Anatomia 3D ou animações artificiais de exercício; o produto usa vídeos Shorts curados.
- Não altere o mapeamento de exercícios por posição. Use identificadores estáveis e nomes validados.
- Não modifique regras científicas do motor de treino apenas por estética.
- Horário e duração não devem voltar a poluir a experiência se já tiverem sido removidos ou tornados opcionais por decisão vigente.
- Valide séries, repetições, descanso, volume e divisão com testes existentes antes de tocar nesses dados.

### 11.5 Progresso e gamificação

- Mostre evolução real, aderência, sequência, marcos e tendências compreensíveis.
- Use celebrações pequenas e proporcionais.
- Não infantilize a interface com excesso de medalhas, confetes ou moedas.
- Não invente pontuação sem regra de produto.
- Diferencie conquista, meta, recomendação e alerta.

### 11.6 Corrida

- Preserve os recursos existentes e a estratégia real do produto.
- Apresente distância, tempo, pace e rota com hierarquia adequada quando disponíveis.
- Não prometa execução em segundo plano que a plataforma atual não suporte.
- Garanta estados de GPS indisponível, permissão negada, pausa, retomada e finalização, se esses fluxos existirem.

### 11.7 Motion

- Use tokens de movimento compartilhados.
- Microinterações devem explicar mudança de estado, continuidade ou sucesso.
- Evite animar grandes blocos durante a rolagem.
- Investigue qualquer tremor ou salto ao rolar no celular.
- Respeite `prefers-reduced-motion`.
- Não espalhe durações e easings hardcoded.

## 12. Dados e perfis de QA

Para validar personalização, use contas descartáveis ou contas de QA autorizadas. Não altere contas reais.

Teste pelo menos cinco combinações coerentes, cobrindo:

- objetivos diferentes;
- idades e pesos distintos;
- níveis iniciante, intermediário e avançado quando suportados;
- frequências semanais diferentes;
- disponibilidade de 3, 4 e 5 dias quando suportada;
- duração ou tempo disponível quando ainda fizer parte da regra;
- estados com e sem histórico.

Inclua o perfil de referência:

- 27 anos;
- 1,85 m;
- 102 kg;
- objetivo emagrecer;
- moderadamente ativo;
- nível intermediário;
- disponibilidade de segunda a sexta.

Altere os dados pela interface sempre que o teste pretender validar a experiência do usuário. Use manipulação direta de banco somente para preparar casos impossíveis ou caros pela UI, documentando o motivo.

## 13. Matriz mínima de fluxos

Teste e registre, conforme existirem no produto:

1. login válido e inválido;
2. cadastro;
3. onboarding completo em três etapas;
4. primeiro acesso;
5. recuperação de sessão e logout;
6. Alimentação/Hoje;
7. adicionar, editar, desfazer e excluir registros permitidos;
8. hidratação, inclusive confirmação de ação destrutiva;
9. iniciar treino;
10. abrir ficha;
11. abrir e fechar vídeo;
12. registrar séries e concluir treino;
13. trocar perfil e regenerar plano quando permitido;
14. Progresso, histórico e estados vazios;
15. Áreas e Perfil;
16. Corrida, se disponível no ambiente;
17. navegação voltar/avançar;
18. reload em rota privada;
19. troca de usuário no mesmo navegador;
20. exclusão da conta descartável ao final.

Não use somente o caminho feliz. Teste também campos inválidos, redes lentas quando simuláveis, ações repetidas, duplo toque, voltar no meio de um fluxo e conteúdo extenso.

## 14. Acessibilidade, qualidade visual e performance

Verifique:

- ordem de foco;
- rótulos acessíveis;
- contraste;
- zoom de texto;
- alvos de toque;
- mensagens de erro associadas aos campos;
- cabeçalhos e landmarks;
- conteúdo não dependente apenas de cor;
- ausência de overflow horizontal;
- estabilidade de layout;
- imagens e vídeos sem deslocamentos desnecessários;
- carregamento progressivo;
- ausência de listeners, players ou iframes duplicados;
- ausência de regressão perceptível de desempenho.

Use medições e ferramentas já disponíveis no projeto. Não adicione uma infraestrutura pesada apenas para produzir uma pontuação bonita.

## 15. Implementação e commits

- Faça alterações em lotes pequenos e coerentes.
- Rode verificações focadas após cada lote.
- Faça commits somente se isso estiver de acordo com o fluxo do repositório e com as instruções locais.
- Não inclua arquivos temporários, dumps, screenshots sensíveis ou credenciais em commits.
- Não misture refatorações sem relação com esta missão.
- Quando encontrar defeito preexistente diretamente bloqueando a integração, corrija-o e registre-o. Defeitos não relacionados devem ir para o relatório, não para uma expansão infinita de escopo.

## 16. Validação técnica obrigatória

Descubra os comandos oficiais do projeto e execute os equivalentes existentes de:

- instalação/verificação de dependências;
- formatação;
- lint;
- typecheck, se aplicável;
- testes unitários;
- testes de integração;
- testes end-to-end existentes;
- build de produção;
- checagem de migrations;
- validação de assets estáticos;
- checagens específicas de acessibilidade ou design system.

Abra a rota de showcase e confirme:

- renderização de todos os componentes;
- todos os assets carregando;
- referências HTML abrindo pelo novo caminho;
- ausência de erros relevantes no console;
- estados e temas funcionando;
- responsividade nos viewports definidos.

Quando uma verificação falhar:

1. reproduza;
2. descubra a causa;
3. aplique a correção mínima correta;
4. rode novamente a verificação focada;
5. rode a suíte de regressão adequada;
6. só então avance.

Não silencie teste, lint ou typecheck para obter verde artificial.

## 17. Deploy e QA de produção

Só publique se o repositório e as instruções locais autorizarem e fornecerem um fluxo existente. Não invente credenciais nem substitua o provedor configurado.

Depois do deploy saudável:

1. crie uma conta descartável exclusivamente pela interface pública;
2. use dados fictícios coerentes e um e-mail throwaway novo;
3. conclua cadastro e onboarding de três etapas;
4. percorra os fluxos críticos da matriz;
5. confirme ausência de respostas 5xx e erros graves no console;
6. registre evidências sem expor senha ou token;
7. exclua a conta pela interface ao final;
8. confirme por mecanismo permitido que a conta foi removida.

Se o deploy depender de um gate externo ainda em andamento, finalize tudo que for possível localmente, deixe o roteiro de QA pronto e aguarde o gate sem refazer trabalho já concluído.

## 18. Remoção do export bruto

`design-system-export` só pode ser removida quando todas estas condições forem verdadeiras:

- todos os itens foram inventariados;
- todo item canônico tem destino comprovado;
- conflitos foram registrados;
- HTMLs de referência funcionam no novo caminho;
- documentação foi integrada;
- showcase renderiza;
- lint, testes e build aplicáveis passaram;
- regressão visual foi executada;
- não existem imports ou links apontando para a pasta antiga.

Antes de apagar, faça uma busca final por referências ao caminho antigo. Depois da remoção, rode novamente as verificações essenciais. A exclusão da pasta está autorizada dentro destas condições; não apague nenhum outro conteúdo por associação.

## 19. Revisão adversarial final

Antes de responder, faça uma última revisão como se estivesse tentando reprovar a entrega. Procure especialmente:

- componente do export que desapareceu sem justificativa;
- duplicação entre legado e novo sistema;
- hardcodes remanescentes em telas migradas;
- mudança funcional disfarçada de redesign;
- problemas de foco, teclado ou rolagem;
- iframe ou player deixado ativo;
- animação que quebra durante scroll;
- links ou assets quebrados;
- documentação conflitante;
- teste que passou sem cobrir o comportamento real;
- diferenças entre ambiente local e produção;
- conta de QA esquecida.

Corrija tudo que estiver dentro do escopo antes da entrega.

## 20. Relatório final obrigatório

Entregue uma única resposta final contendo:

### Estado da entrega

- concluído, parcialmente concluído ou bloqueado;
- commit final e deploy, quando existirem;
- resumo do resultado percebido pelo usuário.

### Inventário do design system

- total de arquivos analisados;
- componentes canônicos encontrados e portados;
- tokens, assets, templates e referências preservados;
- itens internos descartados;
- conflitos de duplicata e vencedor de cada conflito;
- itens deixados de fora e motivo.

### Integração no NutriPlan

- telas e componentes migrados;
- componentes legados consolidados;
- mudanças de navegação;
- mudanças de motion;
- melhorias de acessibilidade;
- decisões conservadoras tomadas.

### Documentação

- lista de contratos Markdown encontrados;
- ação aplicada a cada um;
- localização da fonte da verdade visual;
- rota e instruções do showcase.

### Validação

- comandos executados e resultados;
- quantidade de testes aprovados;
- viewports navegados;
- fluxos do Agent Browser testados;
- perfis de QA utilizados;
- erros encontrados e corrigidos;
- limitações reais remanescentes.

### Evidências

- caminhos de relatórios, inventários ou screenshots não sensíveis;
- URLs internas relevantes, se houver;
- confirmação da exclusão de `design-system-export`;
- confirmação da exclusão da conta descartável de produção.

Não termine com “próximos passos” para trabalho que estava dentro da missão. Se algo dentro do escopo não foi concluído, explique o bloqueio físico com evidência concreta.

---

Comece agora pela leitura das instruções do repositório, inspeção do estado do Git, descoberta das skills do Superpowers disponíveis e inventário completo de `design-system-export`. Depois registre internamente o plano por fases e prossiga sem pedir confirmação.
