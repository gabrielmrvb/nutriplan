# Ledger — janelas do Windows Terminal abrindo sozinhas (16/09/2026)

Missão curta: um PowerShell vazio aparecia na tela do dono várias vezes por
hora. Resolver na origem, travar em teste, provar.

## 1. Diagnóstico

### O que foi varrido

| fonte | como | resultado |
|---|---|---|
| Agendador de Tarefas | `Get-ScheduledTask` fora de `\Microsoft\` (o `schtasks /fo LIST` sai em pt-BR — "Nome da Tarefa:", e um filtro por `TaskName:` casa zero) | **1 tarefa nossa: `NutriPlan lembretes`** |
| processos vivos | `Win32_Process` com pai e linha de comando | `WindowsTerminal.exe -Embedding` vivo desde 18:41:02, título `powershell.exe` |
| `scripts/`, `.claude/`, `.superpowers/`, `.agents/`, `AGENTS.md`, `artifacts/` nos 3 worktrees | grep por `powershell`, `cmd /c`, `start`, `wt`, `Start-Process` | só comentários e o `Start-Process -WindowStyle Hidden` do `capturar_telas.ps1` (com flag; aceito) |
| hooks do Claude Code | `settings.json` | `"hooks": {}` |
| `vigia_main.sh` | `nutriplan-design/artifacts/` (não rastreado) | laço de 30 min com `git fetch`; **não estava rodando** |
| `notificar.ps1` | `nutriplan-design/artifacts/` (não rastreado) | `[console]::beep` + `Write-Host`: exige console; abre janela se chamado por `start` |

### A culpada, com prova de horário

`\NutriPlan lembretes`: gatilho `PT5M` (a cada 5 min, sem fim), `LogonType=Interactive`,
ação `powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "...\scripts\send_reminders.ps1"`.
Último resultado `0x41306` = "encerrada pelo usuário" — é o dono fechando a janela.

Captura ao vivo do disparo previsto para 18:51:00 (watcher de processos, antes de qualquer mudança):

```
18:51:01.7  powershell.exe  pid=34104  "powershell.exe" -WindowStyle Hidden ... send_reminders.ps1   <- a tarefa
18:51:01.7  conhost.exe     pid=31336  (pai 34104)
18:51:01.8  OpenConsole.exe -Embedding
18:51:02.0  WindowsTerminal.exe pid=33396 -Embedding                                                <- A JANELA
18:51:21.8  python.exe manage.py send_meal_reminders  (pai 34104)
```

E o disparo anterior: console pid 33324 às 18:41:01 → `WindowsTerminal.exe` pid 10900 às 18:41:02.
Dois disparos, 5 minutos exatos entre eles, janela um segundo depois de cada um.

### Por que `-WindowStyle Hidden` não escondia

É um argumento do PowerShell, lido depois que o console dele já existe. O Windows
11 delega todo console novo ao Windows Terminal (`-Embedding` = ativado por COM
para hospedar), e a janela já está aberta quando o PowerShell pede para se
esconder. Os 20 s entre o powershell (18:51:01) e o python (18:51:21) são o
PowerShell subindo; o script não imprime nada — daí "PowerShell vazio".

### O que NÃO era

- `scripts/qa/nav.py` lança Chrome headless com `DETACHED_PROCESS` — Chrome é
  gráfico, não pede console. CONFIRMADO PELO CÓDIGO: não é fonte de janela.
  OBSERVAÇÃO: quando a sessão design terminar, migrar para `fundo.rodar`.
- `vigia_main.sh`: não estava em execução. Sai porque o CI substitui.

## 2. Correção na origem

| o quê | como | quando |
|---|---|---|
| tarefa `NutriPlan lembretes` | exportada para backup (`tarefa-lembretes-backup.xml`, no scratchpad da sessão) e apagada com `Unregister-ScheduledTask` | **18:55:27** |
| `scripts/send_reminders.ps1` | removido do repositório | este commit |
| `scripts/fundo.py` | criado: `rodar` (`CREATE_NO_WINDOW`, sobrevive à ferramenta), `notificar` (`winsound` + MessageBox por `pythonw`, some em 20 s), `lembretes`/`agendar-lembretes`/`desagendar-lembretes` (tarefa por `pythonw`, sem console), `varrer` | este commit |
| `nutriplan-design/artifacts/vigia_main.sh` e `notificar.ps1` | apagados depois do push; sessões avisadas | ver §6 |
| README | a seção Lembretes deixa de ensinar a tarefa por PowerShell | este commit |

Decisão: a tarefa local **não foi recriada**. Ela lia o banco local (dados de
teste), falhava sempre que o Postgres não estava de pé (ele não sobe sozinho
depois de reiniciar), e o próprio `CLAUDE.md` já dizia que sem o cron do Render
ninguém recebe lembrete. Quem quiser os lembretes locais de volta:
`python scripts/fundo.py agendar-lembretes` — um comando, sem janela.

## 3. Trava

`config/test_janela_de_fundo.py` (9 testes, `SimpleTestCase`, sem banco):

- varre `scripts/`, `artifacts/`, `.superpowers/` e `.claude/skills/` e fica
  vermelho com `powershell`/`pwsh`, `cmd /c`, `start`, `wt`, `Start-Process`
  ou `[console]::beep` fora de `scripts/fundo.py`;
- aceita só a flag que de fato esconde — `CREATE_NO_WINDOW` em Python,
  `-WindowStyle Hidden`/`-NoNewWindow` junto de `Start-Process`, `start /B` —
  e **na mesma instrução** (a versão que olhava linhas vizinhas aceitava um
  `Start-Process` pelado porque o de baixo tinha a flag);
- `powershell.exe -WindowStyle Hidden -File x.ps1` continua vermelho: é
  literalmente a ação da tarefa que abria janela;
- em markdown só bloco de código conta; comentário não conta em lugar nenhum;
  HTML/JS/CSS não são varridos (`alignItems:'start'` já casou uma vez);
- controle positivo com 13 formas plantadas em pasta temporária e controle
  negativo com as formas aceitas — sem isso um regex quebrado deixaria a
  varredura verde para sempre.

Sabotagem: ver §5.

## 4. Regra

- `CLAUDE.md`, "Limites reais deste ambiente": novo item.
- `nutriplan-missao` §3: subseção "Processo de fundo e notificação: só por `scripts/fundo.py`".

## 5. Prova

### 60 minutos sem janela

Watcher `vigia_janelas.py` (ctypes/Toolhelp32 — o ambiente não tem psutil),
lançado por `fundo.py rodar` às **19:10:44**, 15 min depois da tarefa ser
apagada. Registra todo nascimento de `WindowsTerminal`/`OpenConsole`/`wt`
(JANELA) e de `powershell`/`pwsh`/`cmd` (console). O critério é **JANELA = 0**:
os `powershell.exe` com pai `claude.exe` são a ferramenta PowerShell desta
sessão, com console oculto do harness, e não abrem nada.

Resultado: preenchido em §7 quando o watcher terminar (20:10:44).

### Notificação sem abrir nada

`fundo.py notificar` disparado às **19:11:26**. Caixa de aviso `NutriPlan — prova`
(classe `#32770`) encontrada por `FindWindowW` às **19:11:29**; às 19:11:47 já
tinha sumido sozinha, nenhum `pythonw` vivo, zero JANELA no watcher, log de
erro vazio. Som: `winsound.Beep`, ouvido ou não é do dono — o processo não
reclamou.

### `fundo.py rodar` sobrevive à ferramenta

Lançado num chamado do Bash, encontrado vivo num chamado seguinte do
PowerShell (pids 32788 lançador do venv e 1568 intérprete, ambos desde 19:10:44).

## 6. Outras sessões

Avisadas por mensagem depois do push (ver relatório no chat): parar de usar
`artifacts/notificar.ps1` e `vigia_main.sh`, usar `scripts/fundo.py notificar`
e `fundo.py rodar`; para pegar o arquivo sem mesclar `main`:
`git show origin/main:scripts/fundo.py > scripts/fundo.py`.

## 7. Fechamento

(preenchido no fim da missão)
