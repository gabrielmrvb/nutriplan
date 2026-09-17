"""
Processo de fundo e notificação nascem AQUI, e em nenhum outro lugar.

POR QUE ISTO EXISTE
-------------------
Em 16/09/2026 o dono via janelas do Windows Terminal — um PowerShell vazio —
abrirem sozinhas várias vezes por hora. A causa, provada por horário: a tarefa
agendada `NutriPlan lembretes` rodava `powershell.exe -WindowStyle Hidden -File
scripts/send_reminders.ps1` a cada 5 minutos, na sessão interativa. Captura ao
vivo do disparo das 18:51:

    18:51:01.7  powershell.exe -WindowStyle Hidden ... send_reminders.ps1
    18:51:01.8  OpenConsole.exe -Embedding
    18:51:02.0  WindowsTerminal.exe -Embedding          <- a janela
    18:51:21.8  python.exe manage.py send_meal_reminders

`-WindowStyle Hidden` chega tarde. É um argumento do PowerShell, lido depois
que o console dele já existe — e no Windows 11 quem hospeda todo console novo
é o Windows Terminal, que abre uma janela para isso. Vale igual para `cmd /c`,
para `start`, e para qualquer `subprocess` que lance um programa de console a
partir de um processo que NÃO tem console (os do Claude Code, por exemplo): o
Windows cria um console novo, e console novo é janela.

A REGRA
-------
Processo de fundo nasce com `CREATE_NO_WINDOW`: o filho ganha um console que
nunca é mostrado, e os netos herdam esse console em vez de pedir um novo.

Não é `DETACHED_PROCESS`. Esse dá ao filho console NENHUM — serve para um
Chrome, que é gráfico, e é armadilha para um script: o primeiro programa de
console que o script chamar abre janela.

Notificação toca por `winsound`, que não precisa de console, e o aviso visual
é um MessageBox lançado por `pythonw.exe` — executável gráfico, sem console
para o Windows Terminal hospedar. Some sozinho em 20 s.

COMO USAR
---------
    python scripts/fundo.py rodar [--log ARQ] [--cwd DIR] -- comando args...
        Lança em segundo plano, sem janela, e imprime o pid. Sobrevive a quem
        chamou.

    python scripts/fundo.py notificar [--titulo T] [--sem-banner] [texto]
        tan-tan-tan-TAAAN + aviso na tela, e volta na hora.

    python scripts/fundo.py lembretes
        Roda `send_meal_reminders` com a saída num log. É o que a tarefa do
        Agendador chama — por `pythonw`, nunca por PowerShell.

    python scripts/fundo.py agendar-lembretes | desagendar-lembretes
        Cria ou remove essa tarefa (a cada 5 min, sem janela).

    python scripts/fundo.py varrer [raiz]
        A varredura de `config/test_janela_de_fundo.py`: toda chamada a
        powershell/cmd/start/wt fora deste arquivo, ou sem a flag certa.
"""
import argparse
import contextlib
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROPRIO = Path(__file__).resolve()

#: Console criado e nunca mostrado. Os netos herdam este console.
CREATE_NO_WINDOW = 0x08000000
#: Ctrl+C em quem chamou não chega ao filho.
CREATE_NEW_PROCESS_GROUP = 0x00000200
#: Sai do job de quem chamou, quando o job permite — senão o filho morre
#: junto com a ferramenta que o lançou.
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

FLAGS_DE_FUNDO = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP

TAREFA_DOS_LEMBRETES = "NutriPlan lembretes"

#: tan-tan-tan-TAAAN, como no `notificar.ps1` que este arquivo substitui.
NOTAS = ((784, 180), (988, 180), (1175, 180), (1568, 650))


def pythonw():
    """O `pythonw.exe` do mesmo ambiente deste Python.

    Sem console de nascença — o Windows Terminal não tem o que hospedar. Se
    não existir (ambiente sem venv), o próprio `python.exe` serve, porque quem
    lança já pede `CREATE_NO_WINDOW`.
    """
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def rodar(comando, log=None, cwd=None):
    """Lança `comando` em segundo plano, sem janela. Devolve o `Popen`.

    stdin fechado, porque processo de fundo que espera teclado fica pendurado
    para sempre. Saída vai para `log` (acrescentando) ou para lugar nenhum.
    """
    comando = list(comando)
    # `CreateProcess` procura o executável relativo ao cwd de QUEM CHAMA, não
    # ao `cwd` do filho: `rodar --cwd X -- .venv/Scripts/python.exe` morria com
    # "arquivo não encontrado" mesmo com o python lá. Resolvido aqui, uma vez.
    if cwd and comando and not os.path.isabs(comando[0]):
        candidato = Path(cwd) / comando[0]
        if candidato.exists():
            comando[0] = str(candidato)
    saida = open(log, "ab") if log else subprocess.DEVNULL
    try:
        if os.name != "nt":
            return subprocess.Popen(
                comando, cwd=cwd or RAIZ, stdin=subprocess.DEVNULL,
                stdout=saida, stderr=subprocess.STDOUT, start_new_session=True,
            )
        base = dict(
            cwd=cwd or RAIZ, stdin=subprocess.DEVNULL, stdout=saida,
            stderr=subprocess.STDOUT, close_fds=True,
        )
        try:
            return subprocess.Popen(
                comando, creationflags=FLAGS_DE_FUNDO | CREATE_BREAKAWAY_FROM_JOB, **base
            )
        except PermissionError:
            # O job de quem chamou não deixa sair. Sem janela mesmo assim.
            return subprocess.Popen(comando, creationflags=FLAGS_DE_FUNDO, **base)
    finally:
        if log:
            saida.close()


def _log_padrao(nome):
    return Path(tempfile.gettempdir()) / ("nutriplan-%s.log" % nome)


# ---------------------------------------------------------------- notificar


def tocar():
    import winsound

    for i, (freq, ms) in enumerate(NOTAS):
        if i:
            time.sleep(0.06)
        winsound.Beep(freq, ms)


def banner(titulo, texto, segundos=20):
    """MessageBox por cima de tudo, que some sozinho.

    `MessageBoxTimeoutW` não está documentado, mas está em toda versão do
    Windows desde o XP, e é o que evita um aviso esquecido para sempre na tela.
    """
    import ctypes

    MB_ICONINFORMATION, MB_SETFOREGROUND, MB_TOPMOST = 0x40, 0x10000, 0x40000
    ctypes.windll.user32.MessageBoxTimeoutW(
        None, texto, titulo,
        MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST, 0, int(segundos * 1000),
    )


def _avisar_aqui(titulo, texto, com_banner):
    tocar()
    if com_banner:
        banner(titulo, texto)


def notificar(texto, titulo="NutriPlan", com_banner=True, esperar=False):
    """Toca e avisa. Por padrão lança um `pythonw` e volta na hora.

    `esperar=True` faz tudo neste processo — para teste e para quem quer
    bloquear até o aviso sumir.
    """
    if os.name != "nt":
        print("[notificar] %s — %s" % (titulo, texto))
        return None
    if esperar:
        _avisar_aqui(titulo, texto, com_banner)
        return None
    args = [pythonw(), str(PROPRIO), "_avisar", titulo, texto]
    if not com_banner:
        args.append("--sem-banner")
    return rodar(args, log=_log_padrao("notificar"))


# ---------------------------------------------------------------- lembretes


def acao_dos_lembretes():
    """A linha que o Agendador executa: pythonw, este arquivo, `lembretes`."""
    return '"%s" "%s" lembretes' % (pythonw(), PROPRIO)


def lembretes():
    """`send_meal_reminders` dentro deste processo, com a saída num log.

    Em processo, e não por `subprocess`: sob `pythonw` não há stdout, e um
    filho de console pediria console novo — que é a janela que este arquivo
    existe para não abrir.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.chdir(RAIZ)
    sys.path.insert(0, str(RAIZ))
    with open(_log_padrao("lembretes"), "a", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            print("--- %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
            import django

            django.setup()
            from django.core.management import call_command

            call_command("send_meal_reminders")


def _schtasks(*args):
    return subprocess.run(
        ["schtasks", *args], capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def agendar_lembretes():
    r = _schtasks(
        "/Create", "/F", "/SC", "MINUTE", "/MO", "5",
        "/TN", TAREFA_DOS_LEMBRETES, "/TR", acao_dos_lembretes(),
    )
    print((r.stdout or r.stderr).strip())
    return r.returncode


def desagendar_lembretes():
    r = _schtasks("/Delete", "/F", "/TN", TAREFA_DOS_LEMBRETES)
    print((r.stdout or r.stderr).strip())
    return r.returncode


# ---------------------------------------------------------------- varrer

#: Onde uma sessão pode ter deixado um lançador: scripts, a pasta `artifacts`
#: que as sessões usam de rascunho, o material do superpowers e as skills.
PASTAS_VARRIDAS = ("scripts", "artifacts", ".superpowers", ".claude/skills")
PASTAS_IGNORADAS = {".venv", "node_modules", "__pycache__", ".git"}
#: O que pode ser um lançador. HTML, JS, CSS e imagem não lançam nada — e um
#: `alignItems: "start"` num HTML exportado já casou com o gatilho de `start`.
EXTENSOES_VARRIDAS = {".py", ".sh", ".ps1", ".bat", ".cmd", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ""}

#: Cada gatilho é (nome, regex). O que casa é uma CHAMADA, não uma menção: em
#: markdown só o que está em bloco de código conta, e linha de comentário não
#: conta em lugar nenhum.
#: (nome, regex, extensões em que vale — None é todas).
GATILHOS = (
    ("powershell", re.compile(r"(?<![\w-])(powershell|pwsh)(\.exe)?\b", re.I), None),
    ("cmd /c", re.compile(r"(?<![\w-])cmd(\.exe)?\s+/[ck]\b", re.I), None),
    ("cmd /c", re.compile(r"[\"']cmd(\.exe)?[\"']\s*,\s*[\"']/[ck][\"']", re.I), {".py"}),
    ("start", re.compile(r"(^|[;&|(`]\s*)start\s+\S", re.I), None),
    # lista de argumentos em Python: `["start", ...]`. Só em .py, pelo mesmo motivo.
    ("start", re.compile(r"[\[(,]\s*[\"']start[\"']"), {".py"}),
    ("Start-Process", re.compile(r"\bStart-Process\b", re.I), None),
    ("wt", re.compile(r"(^|[;&|(]\s*)wt(\.exe)?(\s|$)", re.I), None),
    # Notificação sonora fora daqui: é o `notificar.ps1` que este arquivo aposentou.
    ("beep", re.compile(r"\[(System\.)?Console\]::beep|System\.Media\.SoundPlayer", re.I), None),
)

#: O que torna uma chamada aceitável. `-WindowStyle Hidden` só vale junto de
#: `Start-Process`, que o passa ao Windows ANTES de criar o processo; na linha
#: de comando do próprio powershell ele chega tarde — é o caso das 18:51.
_START_PROCESS = re.compile(r"\bStart-Process\b", re.I)
_OCULTO_PS = re.compile(r"-WindowStyle\s+Hidden|-NoNewWindow", re.I)
_OCULTO_START = re.compile(r"\bstart\s+/b\b", re.I)
_COMENTARIO = re.compile(r"^\s*(#|//|::|rem\s|<!--)", re.I)
_CERCA = re.compile(r"^\s*(```|~~~)")


def _linhas_que_contam(caminho, texto):
    """Devolve (numero, linha) só do que pode ser executado."""
    md = caminho.suffix.lower() == ".md"
    dentro = False
    for n, linha in enumerate(texto.splitlines(), 1):
        if md:
            if _CERCA.match(linha):
                dentro = not dentro
                continue
            if not dentro:
                continue
        if _COMENTARIO.match(linha):
            continue
        # comentário no fim da linha: `pg_ctl start  # nada de powershell aqui`
        linha = re.split(r"\s#(?!\{)", linha, 1)[0]
        yield n, linha


def _instrucao(linhas, i, sufixo):
    """A linha `i` mais as continuações dela — e só elas.

    A flag precisa estar na MESMA instrução que a chamada. Olhar as linhas
    vizinhas aceitava um `Start-Process` pelado porque o de baixo tinha
    `-WindowStyle Hidden`.
    """
    inicio = fim = i
    if sufixo == ".py":
        # Profundidade de parênteses no FIM de cada linha. A instrução começa
        # na última linha antes de `i` que fechou tudo, e termina na primeira
        # a partir de `i` que fecha tudo. `subprocess.Popen(` pode estar três
        # linhas acima da string "powershell" — e a flag, duas abaixo.
        profundidade, ao_fim = 0, []
        for _, l in linhas:
            profundidade += l.count("(") + l.count("[") - l.count(")") - l.count("]")
            ao_fim.append(profundidade)
        while inicio > 0 and ao_fim[inicio - 1] > 0:
            inicio -= 1
        while fim + 1 < len(linhas) and ao_fim[fim] > 0:
            fim += 1
    else:
        # PowerShell continua com crase no fim da linha; shell, com barra.
        while fim + 1 < len(linhas) and linhas[fim][1].rstrip().endswith(("`", "\\")):
            fim += 1
        while inicio > 0 and linhas[inicio - 1][1].rstrip().endswith(("`", "\\")):
            inicio -= 1
    return "\n".join(l for _, l in linhas[inicio: fim + 1])


def _aceitavel(nome, instrucao):
    if nome in ("wt", "beep"):
        return False
    if nome == "start":
        return bool(_OCULTO_START.search(instrucao))
    if nome == "Start-Process":
        return bool(_OCULTO_PS.search(instrucao))
    # powershell / cmd
    if "CREATE_NO_WINDOW" in instrucao:
        return True
    return bool(_START_PROCESS.search(instrucao) and _OCULTO_PS.search(instrucao))


def varrer(raiz=RAIZ):
    """Toda chamada que abriria janela, como lista de (arquivo, linha, gatilho, trecho)."""
    raiz = Path(raiz)
    achados = []
    for pasta in PASTAS_VARRIDAS:
        base = raiz / pasta
        if not base.is_dir():
            continue
        for caminho in sorted(base.rglob("*")):
            if not caminho.is_file() or PASTAS_IGNORADAS & set(caminho.parts):
                continue
            if caminho.suffix.lower() not in EXTENSOES_VARRIDAS:
                continue
            if caminho.resolve() == PROPRIO or caminho == raiz / "scripts" / "fundo.py":
                continue
            try:
                texto = caminho.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            linhas = list(_linhas_que_contam(caminho, texto))
            for i, (n, linha) in enumerate(linhas):
                for nome, regex, extensoes in GATILHOS:
                    if extensoes and caminho.suffix.lower() not in extensoes:
                        continue
                    if not regex.search(linha):
                        continue
                    if _aceitavel(nome, _instrucao(linhas, i, caminho.suffix.lower())):
                        continue
                    achados.append((caminho.relative_to(raiz).as_posix(), n, nome, linha.strip()[:100]))
                    break
    return achados


def _descrever(achados):
    return "\n".join("  %s:%d  [%s]  %s" % a for a in achados)


# ---------------------------------------------------------------- cli


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n", 2)[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rodar")
    r.add_argument("--log")
    r.add_argument("--cwd")
    r.add_argument("comando", nargs=argparse.REMAINDER)

    n = sub.add_parser("notificar")
    n.add_argument("texto", nargs="?", default="Sua atenção é necessária. Relatório no chat.")
    n.add_argument("--titulo", default="NutriPlan")
    n.add_argument("--sem-banner", action="store_true")
    n.add_argument("--esperar", action="store_true")

    a = sub.add_parser("_avisar")
    a.add_argument("titulo")
    a.add_argument("texto")
    a.add_argument("--sem-banner", action="store_true")

    sub.add_parser("lembretes")
    sub.add_parser("agendar-lembretes")
    sub.add_parser("desagendar-lembretes")

    v = sub.add_parser("varrer")
    v.add_argument("raiz", nargs="?", default=str(RAIZ))

    args = p.parse_args(argv)

    if args.cmd == "rodar":
        comando = args.comando[1:] if args.comando[:1] == ["--"] else args.comando
        if not comando:
            p.error("rodar precisa de um comando depois de --")
        proc = rodar(comando, log=args.log, cwd=args.cwd)
        print(proc.pid)
        return 0
    if args.cmd == "notificar":
        proc = notificar(args.texto, args.titulo, not args.sem_banner, args.esperar)
        print(proc.pid if proc else "ok")
        return 0
    if args.cmd == "_avisar":
        _avisar_aqui(args.titulo, args.texto, not args.sem_banner)
        return 0
    if args.cmd == "lembretes":
        lembretes()
        return 0
    if args.cmd == "agendar-lembretes":
        return agendar_lembretes()
    if args.cmd == "desagendar-lembretes":
        return desagendar_lembretes()
    if args.cmd == "varrer":
        achados = varrer(args.raiz)
        if achados:
            print("%d chamada(s) que abririam janela:\n%s" % (len(achados), _descrever(achados)))
            return 1
        print("nenhuma chamada que abra janela")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
