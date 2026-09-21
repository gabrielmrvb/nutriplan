# Retenção e descoberta — o que faz alguém ficar e o que faz alguém achar o app (21/09/2026)

Missão do dono, cinco itens, **um PR por item**, cada um provado em produção
com conta descartável (signup público, e-mail real recebido, conta apagada
pela tela). Worktree `C:\Users\biel-\nutriplan-retencao`, base `55b6c18`.

## Objetivo, em uma frase por item

1. **E-mails transacionais** pela Brevo já configurada (SMTP 2525): boas-vindas
   no cadastro (troca para "após verificação" quando a sessão de segurança
   publicar o gancho), "você não treina há 5 dias" (diário, respeita
   preferência) e resumo semanal (segunda de manhã: treinos, séries, peso,
   água); preferência granular no perfil (quais e-mails, quais pushes,
   horário); link de descadastro em todos; teste de render + envio real.
2. **/ajuda/**: FAQ escrita a partir do que o app faz; "Reportar um problema"
   com rota, versão e dispositivo preenchidos, enviado por e-mail ao dono;
   "O que mudou" alimentado por um `CHANGELOG.md` para gente (não pelo
   `BACKLOG.md`, que é caderno de engenharia).
3. **Glúteo** como grupo muscular próprio: modelo, reclassificação por
   migração de dados com teste, divisão e volume ajustados; prova de que
   nenhuma ficha existente perde exercício.
4. **SEO** das rotas públicas: title/description por rota, Open Graph +
   Twitter card com imagem gerada da landing, `sitemap.xml`, `robots.txt`,
   canonical, JSON-LD `SoftwareApplication`; Lighthouse SEO ≥ 95 na landing
   e no `/demo/`.
5. **Compartilhar o placar** como PNG no design NERVURA (nome da sessão,
   séries, volume, tempo e marca — sem peso corporal), Web Share API com
   fallback de download.

## O que o código faz hoje (lido)

- E-mail: `EMAIL_BACKEND` por env (console local, SMTP Brevo 2525 em
  produção), `DEFAULT_FROM_EMAIL = "NutriPlan <nao-responda@nutriplan.app>"`;
  o único e-mail do app é o de senha (`templates/accounts/email_senha.*`,
  inline-style, `autoescape off` + `force_escape` no nome). Não há
  `django.contrib.sites`; o link do reset usa `protocol`/`domain` do request.
- Agendamento: NÃO há cron pago. `push/tarefas.rodar()` é chamado de 5 em 5
  min (UptimeRobot no GET externo, `schedule` do Actions no POST) e DORME
  até 30 min (`_pausa_ate`) para o Neon hibernar. Idempotência dos lembretes
  pela constraint do `NotificationLog`.
- Preferência de aviso: só `PushSubscription.is_active`; nada por tipo, nada
  de horário.
- Cadastro: `SignupView.form_valid` (senha) e o adapter social do allauth
  (`NutriPlanSocialAccountAdapter`, Google) — dois caminhos criam usuário.
  `ACCOUNT_EMAIL_VERIFICATION = "none"` (a verificação é da sessão de
  segurança; ledger).
- Grupos musculares: `MuscleGroup` (11 valores), `HAMSTRINGS` rotulado
  "Posterior de coxa e glúteo"; `doutrina.GRANDES` e `adaptacao.GRUPOS_
  INFERIORES` enumeram; TREINO.md tabela B é por nível × ocorrências (não por
  grupo) e a tabela "média medida" tem uma coluna por grupo; splits têm
  `principais`; `services.py:2066` mapeia grupo → nome curto.
- Público: landing em `/` (anônimo), `/demo/…` (middleware), `/conta/entrar/`,
  `/conta/cadastro/`, `/privacidade/`, `/termos/`. `base.html` tem `<title>`
  em bloco e UMA `<meta name=description>` fixa; sem OG, sem canonical, sem
  sitemap, sem robots.
- Placar: `.recompensa` na execução (NERVURA 3/3), `services.Placar` com
  carga total, séries, minutos, vs. última, recorde.

## Decomposição

| # | unidade | rótulo | arquivos (dono) |
|---|---|---|---|
| A | app `avisos/` (preferência, log, serviços, jobs, descadastro, tela) + gancho em `push/tarefas.rodar` + boas-vindas nos dois cadastros | SEQUENCIAL (settings/urls) | `avisos/*`, `templates/avisos/*`, `templates/email/*`, `push/tarefas.py`, `push/services.py` (gate do push), `accounts/views.py` (signup), `accounts/adapters.py`, `config/settings.py`, `config/urls.py`, `scripts/hooks/pre-commit` (CONHECIDAS) |
| B | app `ajuda/` (FAQ, reportar, o que mudou) + `CHANGELOG.md` | SEQUENCIAL (urls) | `ajuda/*`, `templates/ajuda/*`, `CHANGELOG.md`, `config/urls.py`, `templates/base.html` (link) |
| C | glúteo | PARALELIZÁVEL | `workouts/models.py`, `workouts/data/*.json`, `workouts/migrations/00xx`, `workouts/doutrina.py`, `workouts/adaptacao.py`, `workouts/services.py`, testes, `TREINO.md`, `CLAUDE.md` |
| D | SEO | PARALELIZÁVEL | `templates/base.html` (head), `templates/plans/landing.html`, `config/urls.py` (sitemap/robots), `plans/seo.py`, `static/img/og-*.png` |
| E | compartilhar placar | PARALELIZÁVEL | `templates/workouts/agora.html` (placar), `static/js/pwa.js`, testes |

Serializados: `config/settings.py` e `config/urls.py` (aviso no ledger a cada
toque; a sessão analytics também os toca).

## Critérios de sucesso (o que a prova em produção tem de mostrar)

1. Conta descartável `claudeglauco+retencao@gmail.com` criada pelo signup →
   e-mail de boas-vindas RECEBIDO no Gmail (lido pelo conector); `/avisos/`
   mostra as preferências; descadastro pelo link do e-mail desliga o tipo;
   `manage.py` dos jobs num banco local com fixture prova os dois outros
   e-mails (o de inatividade e o semanal não dá para esperar 5 dias em
   produção — a prova deles é local + o envio real de um deles pela conta
   descartável com data forçada).
2. `/ajuda/` 200 anônima e logada; "Reportar um problema" com rota/versão/
   dispositivo preenchidos → e-mail recebido; "O que mudou" lista o
   `CHANGELOG.md`.
3. Suíte verde com o dourado intacto; teste que compara a prescrição de
   todas as divisões/níveis/equipamentos ANTES (grupo antigo) e DEPOIS: nenhum
   exercício some de nenhuma sessão; migração de dados testada.
4. `curl` em produção: `sitemap.xml`, `robots.txt`, OG/Twitter/canonical/
   JSON-LD nas rotas públicas; Lighthouse SEO ≥ 95 na landing e no `/demo/`.
5. Placar em produção com "Compartilhar": PNG gerado (canvas) com os cinco
   dados e a marca, sem peso corporal; `navigator.share` quando existe,
   download quando não.

## Decisões que tomei sozinha (vetáveis)

- E-mails moram num app novo `avisos/` (preferência + log + jobs + tela +
  descadastro): `push/` continua sendo o push, e `accounts/models.py` é
  arquivo serializado por todo mundo.
- Os jobs de e-mail rodam DENTRO da rodada do `push/tarefas.rodar()` (quando
  ela não está pausada), na hora escolhida pela pessoa (`hora_email`,
  padrão 08:00) — chegam em até 30 min depois da hora, o preço de deixar o
  Neon dormir; nada de workflow novo (o `schedule` pula).
- "Não treina há 5 dias" é UM e-mail por episódio de pausa (chave = data da
  última série, ou "nunca" + data do cadastro), nunca um por dia.
- Resumo semanal só para quem tem plano ativo; a semana é a de segunda a
  domingo anterior (ISO), chave `AAAA-Www`.
- Descadastro por link com chave própria por pessoa (`Preferencia.chave`,
  32 hex), GET e POST (RFC 8058 `List-Unsubscribe-Post`), sem login.
- Boas-vindas sai no cadastro (senha E Google) até a sessão de segurança
  publicar o gancho de verificação; o ponto de troca é uma função só
  (`avisos.services.boas_vindas`).
- "O que mudou" lê um `CHANGELOG.md` novo, para gente, e não o `BACKLOG.md`.
- Placar → PNG no NAVEGADOR (canvas com as fontes já carregadas), não no
  servidor: zero dependência nova, funciona offline, nada de dado no servidor.
