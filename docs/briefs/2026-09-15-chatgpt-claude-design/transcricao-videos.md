# A narração dos três Reels do @matheusgomes

Transcrita em 15/09/2026 com `faster-whisper` (modelo `small`, pt, CPU) a
partir dos MP4 públicos do Instagram, e resumida aqui passo a passo, com as
citações curtas que importam. O modelo erra nome próprio ("Behinds" é
Behance, "chat IPT" é ChatGPT, "Ops 5 no Effort Extra" é Opus 5 com esforço
Extra) — já corrigido abaixo.

## O que a fala acrescenta ao que a tela mostra

### Parte 1/2 — criar o design system (`DdMjjtITgul`)

1. Entrar em **claude.ai/design**, modelo **Opus 5**, esforço **Extra**.
2. No "+" do prompt, **Design System → Create new**.
3. Referência visual: ele usa o **Behance** ("pode ser Figma, Pinterest, o
   que quiser"), busca **"dashboard web design"** e escolhe um case. A
   régua dele: *"quanto mais completo for o projeto que você pegar, melhor
   — se você pegar uma coisa muito crua, vai ter que pautar outras coisas,
   ou o Claude Design vai inventar"*. O case escolhido já traz fonte, grid,
   tamanhos, formato de ícone, tipografia e cores.
4. Para baixar as imagens do case ele **usa o agente do ChatGPT** ("abaixe
   as imagens desse projeto e salve na minha pasta Downloads") — 8 imagens.
5. No setup do Claude Design: **nome da empresa**, opcionalmente **linkar o
   GitHub**, **a logo**, e a nota de uma linha ("dashboard moderno, clean,
   agradável…"). As 8 imagens vão para **assets**.
6. "Continuar" → geração de **uns 5 minutos**. O Claude Design **faz uma
   série de perguntas**; ou você responde, ou clica **"decida por mim"**.
7. Resultado: **tom de voz, cores, tipografia, grids, elementos**, um
   exemplo de dashboard futuro e a versão mobile. *"Qualquer coisa que você
   não gostar, é só pedir para mudar."*

### Parte 2/2 — exportar e integrar (`DdM5PxOTBRe`)

1. claude.ai/design → **Design systems** → o que você criou.
2. **Share → Project HTML → Export** (exporta tudo). A segunda opção,
   "compila HTML", *"você não vai usar"*. Ele observa que o design system
   **já criou um dashboard também**.
3. Abrir a pasta exportada; **renomear para `design-system-export`** e
   **colar na raiz do projeto**. (*"Você pode apagar tudo que foi criado"*
   — ele descarta o resto do zip e leva só essa pasta.)
4. Rodar **o prompt dos comentários** (a Parte 1; as outras três partes
   vêm em seguida) — *"são só dois prompts que você vai rodar e tudo vai
   ser feito sozinho"*.
5. O que muda: a pasta bruta some, nasce **`design-system`** organizada, e
   na raiz ele **cria `AGENTS.md`** (*"se você já tiver esse arquivo, não
   tem problema, ele faz o merge"*), **`CLAUDE.md`** e **`DESIGN.md`** com
   as especificações, **atualiza ou cria `PRODUCT.md`**, e dentro de
   `design-system` **gera uma skill** — *"sempre que a gente for trabalhar,
   ele vai ler essa skill e entender quais são os padrões"*. Light e dark.

### "Dashboard mais lindo do mundo com 1 prompt" (`DdSfS5FMgkO`)

1. claude.ai/design → **selecionar o design system criado** → template
   **blank** (nenhum).
2. Colar o prompt (o do CRM, que está na msg 27 da transcrição do ChatGPT —
   *"você pode reestruturar ele pro seu negócio, mas é uma base para
   entender como eu gosto de pautar"*).
3. **Opus 5, esforço Extra** → rodar. *"100% em cima do design system que
   foi criado… qualquer coisa que eu pautar, nada vai sair do padrão — site,
   app, Play Store, App Store."*
4. O resultado sai com gamificação, organizações, equipe e permissões,
   planos e pagamentos, perfil, suporte interno, painel, conversas, contatos,
   funil, tarefas. Ele mesmo diz que descobriu o resultado gravando.

O que **não** está em nenhuma das três falas: nenhuma menção ao plugin
`frontend-design`, nenhuma menção a Superpowers ou a Agent Browser, e
nenhum passo em que o app existente seja analisado antes de criar o sistema
— a entrada é uma referência de terceiros mais a logo e uma frase.

O bruto da transcrição (narração verbatim) não entra no repositório por ser
conteúdo de terceiro; ficou na máquina de quem transcreveu.
