"""Nenhum processo de fundo abre janela — e tudo passa por `scripts/fundo.py`.

O CASO REAL
===========

16/09/2026: janelas do Windows Terminal, um PowerShell vazio, abrindo sozinhas
várias vezes por hora na tela do dono. Culpada, provada por horário: a tarefa
agendada `NutriPlan lembretes`, `powershell.exe -WindowStyle Hidden -File
scripts/send_reminders.ps1` a cada 5 minutos. Às 18:51:01.7 nasceu o
powershell; às 18:51:02.0, o `WindowsTerminal.exe -Embedding` que o hospedava.
O `-WindowStyle Hidden` não evita nada: é lido pelo PowerShell depois que o
console dele já existe — e no Windows 11, console novo é o Windows Terminal
abrindo uma janela.

O QUE ESTES TESTES TRAVAM
=========================

1. A varredura de `scripts/`, `artifacts/`, `.superpowers/` e das skills não
   encontra chamada a powershell/cmd/start/wt nem beep fora de `fundo.py` —
   salvo com a flag que de fato esconde (`CREATE_NO_WINDOW` em Python,
   `-WindowStyle Hidden`/`-NoNewWindow` junto de `Start-Process`, `start /B`).
2. A varredura ENXERGA cada forma proibida (controle positivo) e IGNORA
   comentário, prosa de markdown, `pg_ctl start` e as formas com flag
   (controle negativo). Sem o positivo, um regex quebrado deixaria o teste 1
   verde para sempre.
3. `fundo.rodar` pede `CREATE_NO_WINDOW`; `fundo.notificar` lança `pythonw`;
   a tarefa de lembretes, se alguém a recriar, roda por `pythonw`.
4. O lançador antigo (`scripts/send_reminders.ps1`) saiu, e nenhum documento
   manda criar tarefa com `powershell.exe` de novo.

A varredura é estática de propósito: a prova dinâmica (60 min sem janela) foi
feita uma vez com o watcher de processos, e está no plano da missão. O que
cabe na suíte é impedir que a chamada volte a existir no repositório.
"""
import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock, skipUnless

from django.conf import settings
from django.test import SimpleTestCase

RAIZ = Path(settings.BASE_DIR)


def _fundo():
    spec = importlib.util.spec_from_file_location("fundo", RAIZ / "scripts" / "fundo.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


fundo = _fundo()


class ORepositorioNaoAbreJanelaTests(SimpleTestCase):
    def test_nenhum_script_pasta_de_trabalho_ou_skill_chama_console_visivel(self):
        achados = fundo.varrer(RAIZ)
        self.assertEqual(
            achados, [],
            "Chamada(s) que abririam janela do Windows Terminal — leve para "
            "scripts/fundo.py ou passe a flag que esconde:\n" + fundo._descrever(achados),
        )

    def test_o_lancador_antigo_de_lembretes_saiu(self):
        """`send_reminders.ps1` era o que a tarefa agendada chamava por PowerShell.

        A ação da tarefa agora é `pythonw scripts/fundo.py lembretes`, e o .ps1
        de volta seria o caminho de alguém recriar a tarefa do jeito velho.
        """
        self.assertFalse((RAIZ / "scripts" / "send_reminders.ps1").exists())
        for nome in ("README.md", "CLAUDE.md"):
            texto = (RAIZ / nome).read_text(encoding="utf-8")
            self.assertNotIn("send_reminders.ps1", texto, nome)


class AVarreduraEnxergaCadaFormaProibidaTests(SimpleTestCase):
    """Controle positivo: se um regex quebrar, é aqui que fica vermelho."""

    def _varrer(self, arquivos):
        with tempfile.TemporaryDirectory() as raiz:
            for relativo, conteudo in arquivos.items():
                caminho = Path(raiz) / relativo
                caminho.parent.mkdir(parents=True, exist_ok=True)
                caminho.write_text(conteudo, encoding="utf-8")
            return sorted((a, n, g) for a, n, g, _ in fundo.varrer(raiz))

    def test_cada_forma_e_detectada_na_linha_certa(self):
        achados = self._varrer({
            "scripts/a.sh": (
                "powershell -c \"Get-Date\"\n"          # 1
                "cmd /c dir\n"                           # 2
                "start powershell\n"                     # 3
                "wt new-tab\n"                           # 4
            ),
            "scripts/b.ps1": (
                "Start-Process python -ArgumentList \"x\"\n"                                    # 1
                "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"x.ps1\"\n"  # 2: o caso das 18:51
                "[console]::beep(784, 180)\n"                                                   # 3
            ),
            "scripts/c.py": (
                "subprocess.run([\"powershell\", \"-File\", \"a.ps1\"])\n"   # 1
                "subprocess.Popen([\"start\", \"x\"], shell=True)\n"          # 2
                "subprocess.run(\n"                                          # 3
                "    [\"cmd\", \"/c\", \"dir\"],\n"                          # 4
                ")\n"
            ),
            ".claude/skills/x/SKILL.md": "```bash\npowershell -File x.ps1\n```\n",  # 2
            ".superpowers/sdd/brief.md": "```\ncmd /c start x\n```\n",              # 2
            "artifacts/notificar.ps1": "[console]::beep(1568, 650)\n",               # 1
        })
        self.assertEqual(
            achados,
            [
                (".claude/skills/x/SKILL.md", 2, "powershell"),
                (".superpowers/sdd/brief.md", 2, "cmd /c"),
                ("artifacts/notificar.ps1", 1, "beep"),
                ("scripts/a.sh", 1, "powershell"),
                ("scripts/a.sh", 2, "cmd /c"),
                ("scripts/a.sh", 3, "powershell"),
                ("scripts/a.sh", 4, "wt"),
                ("scripts/b.ps1", 1, "Start-Process"),
                ("scripts/b.ps1", 2, "powershell"),
                ("scripts/b.ps1", 3, "beep"),
                ("scripts/c.py", 1, "powershell"),
                ("scripts/c.py", 2, "start"),
                ("scripts/c.py", 4, "cmd /c"),
            ],
        )

    def test_o_que_nao_abre_janela_nao_e_acusado(self):
        achados = self._varrer({
            "scripts/ok.sh": (
                "# powershell -c numa linha de comentário\n"
                "pg_ctl start   # start aqui é argumento, e este comentário cita powershell\n"
                "start /B python x.py\n"
            ),
            "scripts/ok.ps1": (
                "Start-Process python -ArgumentList \"y\" -WindowStyle Hidden\n"
                "Start-Process python `\n"
                "  -ArgumentList \"z\" `\n"
                "  -WindowStyle Hidden -PassThru\n"
                "Start-Process notepad -NoNewWindow\n"
            ),
            "scripts/ok.py": (
                "subprocess.Popen(\n"
                "    [\"powershell\", \"-File\", \"b.ps1\"],\n"
                "    creationflags=subprocess.CREATE_NO_WINDOW,\n"
                ")\n"
                "caminho = r\"C:\\windows\\System32\\WindowsPowerShell\\v1.0\"  # pasta, não chamada\n"
            ),
            ".claude/skills/x/SKILL.md": (
                "Em prosa, `powershell -c`, `cmd /c` e `start` são só palavras.\n"
                "Nenhum processo de fundo chama powershell.\n"
            ),
            "scripts/export.html": "<div style={{alignItems:'start'}}>\n",
            "static/x.sh": "powershell -c fora das pastas varridas\n",
        })
        self.assertEqual(achados, [])

    def test_a_flag_na_linha_de_comando_do_powershell_nao_salva(self):
        """É exatamente o que a tarefa agendada tinha, e a janela abria mesmo assim."""
        achados = self._varrer({
            "scripts/tarefa.ps1": "powershell.exe -WindowStyle Hidden -File \"x.ps1\"\n",
        })
        self.assertEqual([g for _, _, g in achados], ["powershell"])

    def test_a_flag_precisa_estar_na_mesma_instrucao(self):
        """Um `Start-Process` pelado não é salvo pelo vizinho de baixo com flag."""
        achados = self._varrer({
            "scripts/dois.ps1": (
                "Start-Process python -ArgumentList \"x\"\n"
                "Start-Process python -ArgumentList \"y\" -WindowStyle Hidden\n"
            ),
            "scripts/dois.py": (
                "subprocess.run([\"powershell\", \"-File\", \"a.ps1\"])\n"
                "subprocess.run([\"powershell\"], creationflags=CREATE_NO_WINDOW)\n"
            ),
        })
        self.assertEqual(achados, [("scripts/dois.ps1", 1, "Start-Process"), ("scripts/dois.py", 1, "powershell")])


class OFundoNaoAbreJanelaTests(SimpleTestCase):
    def test_rodar_pede_console_escondido_e_fecha_o_teclado(self):
        with mock.patch.object(fundo.subprocess, "Popen") as popen:
            fundo.rodar(["x"])
        kwargs = popen.call_args.kwargs
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertTrue(kwargs["creationflags"] & fundo.CREATE_NO_WINDOW)
            self.assertFalse(kwargs["creationflags"] & 0x8, "DETACHED_PROCESS dá console nenhum — os netos abririam janela")
        else:
            self.assertTrue(kwargs["start_new_session"])

    @skipUnless(os.name == "nt", "pythonw e o Agendador são do Windows")
    def test_notificar_lanca_pythonw_e_volta_na_hora(self):
        with mock.patch.object(fundo.subprocess, "Popen") as popen:
            fundo.notificar("oi")
        argv = popen.call_args.args[0]
        self.assertTrue(argv[0].lower().endswith("pythonw.exe"), argv[0])
        self.assertEqual(argv[2], "_avisar")
        self.assertTrue(popen.call_args.kwargs["creationflags"] & fundo.CREATE_NO_WINDOW)

    @skipUnless(os.name == "nt", "pythonw e o Agendador são do Windows")
    def test_a_tarefa_de_lembretes_roda_por_pythonw(self):
        acao = fundo.acao_dos_lembretes()
        self.assertTrue(acao.lower().startswith('"' + fundo.pythonw().lower()), acao)
        self.assertNotIn("powershell", acao.lower())
        self.assertTrue(acao.endswith(" lembretes"))
