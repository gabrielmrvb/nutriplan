# -*- coding: utf-8 -*-
"""A trava de segredo do pre-commit (21/09/2026): o cofre `~/.nutriplan-secrets`
não entra em commit nem pelo nome, nem pelo conteúdo.

Dois scanners, uma regra: `gitleaks git --staged --config .gitleaks.toml`
(quando o binário existe) e `scripts/segredos.py --staged` (Python puro,
sempre). Cada um é provado num repositório de TESTE com um arquivo do cofre
no índice — `render_api_key` com lixo dentro — e tem de recusar; com um
arquivo comum, tem de aceitar. O gitleaks não instalado é `skip` NOMEADO
(ferramenta externa; o Python cobre a régua), nunca falha silenciosa.

As formas de segredo escritas AQUI (uma chave `rnd_…`, uma URL do Neon) são
inventadas e este arquivo está no `[allowlist]` do `.gitleaks.toml` — é o
único lugar do repositório onde uma forma dessas pode aparecer.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from scripts import segredos

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / ".gitleaks.toml"
HOOK = (RAIZ / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
NOMES_DO_COFRE = ("render_api_key", "backup_database_url", "staging_database_url", "staging_database_url_ep-x",
                  "staging_env.json", "tarefas_token", "disparo_token", "vapid-nutriplan-2026-09-16.env")


def gitleaks():
    caminho = shutil.which("gitleaks")
    if caminho:
        return caminho
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for pasta in base.glob("Gitleaks.Gitleaks_*"):
        if (pasta / "gitleaks.exe").exists():
            return str(pasta / "gitleaks.exe")
    return None


def sem_git_no_ambiente():
    """Dentro de um hook o git exporta GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE, e
    todo `git -C <pasta>` passaria a operar no índice do HOOK — foi assim que
    o pre-push viu os arquivos de três repositórios de teste num só (21/09).
    O mesmo motivo do `env -u` em `scripts/backup.sh`."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def repo_de_teste(nome, conteudo):
    """Um repositório novo com UM arquivo no índice."""
    pasta = Path(tempfile.mkdtemp(prefix="nutriplan-segredos-"))
    env = sem_git_no_ambiente()
    subprocess.run(["git", "init", "-q", str(pasta)], check=True, env=env)
    subprocess.run(["git", "-C", str(pasta), "config", "user.email", "t@t"], check=True, env=env)
    subprocess.run(["git", "-C", str(pasta), "config", "user.name", "t"], check=True, env=env)
    arquivo = pasta / nome
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(conteudo, encoding="utf-8")
    # `-f`: o ignore GLOBAL desta máquina já recusa esses nomes; o que se prova
    # aqui é a trava de dentro do repositório, que vale em qualquer máquina.
    subprocess.run(["git", "-C", str(pasta), "add", "-f", nome], check=True, env=env)
    return pasta


class AsRegrasTests(SimpleTestCase):
    def test_o_arquivo_liga_as_regras_padrao_e_tem_as_quatro_do_nutriplan(self):
        texto = CONFIG.read_text(encoding="utf-8")
        self.assertIn("useDefault = true", texto)
        lista, permitidos = segredos.regras(CONFIG)
        self.assertEqual([r["id"] for r in lista], ["nutriplan-cofre", "nutriplan-render-api-key", "nutriplan-neon-url", "nutriplan-brevo-smtp"])
        self.assertTrue(any(p.search("config/test_segredos.py") for p in permitidos), "este arquivo escreve formas de propósito")

    def test_todo_nome_do_cofre_e_barrado_pelo_caminho_em_qualquer_pasta(self):
        lista, _ = segredos.regras(CONFIG)
        cofre = next(r for r in lista if r["id"] == "nutriplan-cofre")
        for nome in NOMES_DO_COFRE:
            for caminho in (nome, "scripts/" + nome, "docs/x/" + nome, ".nutriplan-secrets/" + nome, "a\\b\\" + nome):
                with self.subTest(caminho=caminho):
                    self.assertTrue(cofre["path"].search(caminho), caminho)
        for comum in ("scripts/render_api.py", "config/settings.py", "docs/infra-recuperacao.md", "scripts/incidente.py"):
            with self.subTest(caminho=comum):
                self.assertFalse(cofre["path"].search(comum), comum)

    def test_as_formas_de_segredo_sao_reconhecidas_e_o_texto_comum_nao(self):
        achados = segredos.varrer(
            ["config/settings.py", "notas.md", "docs/x.md"],
            {
                "config/settings.py": "RENDER = 'rnd_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345'\n",
                "notas.md": "postgresql://neondb_owner:segredo123@ep-x.us-west-2.aws.neon.tech/neondb?sslmode=require\n",
                "docs/x.md": "a chave mora em ~/.nutriplan-secrets/render_api_key e é rnd_ curta\n",
            }.__getitem__,
            segredos.regras(CONFIG),
        )
        self.assertEqual([(a, r) for a, _, r in achados], [("config/settings.py", "nutriplan-render-api-key"), ("notas.md", "nutriplan-neon-url")])


class OScannerEmPythonTests(SimpleTestCase):
    def _rodar(self, pasta):
        r = subprocess.run([str(RAIZ / ".venv" / "Scripts" / "python.exe") if (RAIZ / ".venv" / "Scripts" / "python.exe").exists() else "python",
                            str(RAIZ / "scripts" / "segredos.py"), "--staged", "--repo", str(pasta), "--config", str(CONFIG)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=sem_git_no_ambiente())
        return r.returncode, r.stdout

    def test_barra_o_arquivo_do_cofre_pelo_nome_e_aceita_um_arquivo_comum(self):
        pasta = repo_de_teste("scripts/render_api_key", "lixo\n")
        codigo, saida = self._rodar(pasta)
        self.assertEqual(codigo, 1)
        self.assertIn("nutriplan-cofre", saida)
        self.assertIn("render_api_key", saida)
        self.assertNotIn("lixo", saida, "o valor nunca é impresso")
        pasta = repo_de_teste("docs/nota.md", "só texto\n")
        codigo, saida = self._rodar(pasta)
        self.assertEqual(codigo, 0, saida)

    def test_barra_a_forma_de_segredo_dentro_de_um_arquivo_comum(self):
        pasta = repo_de_teste("config/local.py", "URL = 'postgres://u:p@ep-y.c-2.us-west-2.aws.neon.tech/db'\n")
        codigo, saida = self._rodar(pasta)
        self.assertEqual(codigo, 1)
        self.assertIn("nutriplan-neon-url", saida)
        self.assertNotIn("ep-y", saida)


class OGitleaksTests(SimpleTestCase):
    def setUp(self):
        self.binario = gitleaks()
        if not self.binario:
            self.skipTest("gitleaks não instalado nesta máquina (WinGet Gitleaks.Gitleaks / apt / brew); o scanner em Python cobre a régua")

    def _rodar(self, pasta):
        r = subprocess.run([self.binario, "git", "--staged", "--config", str(CONFIG), "--no-banner", "--redact", "--verbose", "--exit-code", "1"],
                           cwd=str(pasta), capture_output=True, text=True, encoding="utf-8", errors="replace", env=sem_git_no_ambiente())
        return r.returncode, r.stdout + r.stderr

    def test_o_gitleaks_barra_o_arquivo_do_cofre_pelo_nome(self):
        pasta = repo_de_teste("scripts/render_api_key", "lixo\n")
        codigo, saida = self._rodar(pasta)
        self.assertEqual(codigo, 1, saida[-800:])
        self.assertIn("nutriplan-cofre", saida)

    def test_o_gitleaks_aceita_um_arquivo_comum(self):
        pasta = repo_de_teste("docs/nota.md", "só texto\n")
        codigo, saida = self._rodar(pasta)
        self.assertEqual(codigo, 0, saida[-800:])


class OHookChamaATravaTests(SimpleTestCase):
    def test_o_pre_commit_roda_o_gitleaks_ou_o_scanner_em_python_antes_de_tudo(self):
        corpo = "\n".join(l for l in HOOK.splitlines() if not l.lstrip().startswith("#"))
        self.assertIn('gitleaks git --staged --config .gitleaks.toml', corpo.replace('"$GITLEAKS" ', "gitleaks "))
        self.assertIn("scripts/segredos.py --staged", corpo)
        self.assertLess(corpo.index("segredos no commit"), corpo.index("migrações pendentes"), "o segredo é a primeira coisa a barrar")
