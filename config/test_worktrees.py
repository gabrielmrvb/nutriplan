# -*- coding: utf-8 -*-
"""A poda semanal de worktrees e bancos de teste (`scripts/worktrees.py`,
21/09/2026) — as regras de classificação, a régua do banco órfão e a
guarda que mais importa: **apagar um worktree nunca atravessa uma junção**.

Medido em 21/09: 46 worktrees registrados, e quase todos com `.venv` como
JUNÇÃO para o venv compartilhado do checkout principal. `os.walk` e um
`rmtree` ingênuo seguem a junção — o primeiro contava 0,18 GB por worktree
de 0,02, e o segundo apagaria o venv de todo mundo. Os testes aqui criam
uma junção DE VERDADE (`_winapi.CreateJunction`) e provam que o alvo fica.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock, skipUnless

from django.test import SimpleTestCase

from scripts import worktrees as w

RAIZ = Path(__file__).resolve().parents[1]
CLAUDE = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")


def _junction(origem, destino):
    import _winapi
    _winapi.CreateJunction(str(origem), str(destino))


class ClassificacaoTests(SimpleTestCase):
    """Cada regra do docstring do script, uma por teste, com git falso."""

    def _wt(self, **extra):
        base = {"caminho": "C:/x/wt-um", "head": "abc", "branch": "feat/um", "destacado": False, "trancado": False, "principal": False}
        base.update(extra)
        return base

    def _classificar(self, wt, origem=("feat/um", "main"), citados=(), aqui="c:/x/aqui", status=(0, ""), ancestral=0, existe=True):
        def git(*args, cwd=None):
            if args[0] == "status":
                return status
            if args[0] == "merge-base":
                return ancestral, ""
            raise AssertionError(args)
        with mock.patch.object(w, "_git", side_effect=git), mock.patch.object(w.Path, "exists", return_value=existe):
            return w.classificar(wt, set(origem), set(citados), aqui)

    def test_o_checkout_principal_e_o_worktree_de_onde_o_script_roda_ficam_sempre(self):
        self.assertEqual(self._classificar(self._wt(principal=True))[0], "preservar")
        self.assertEqual(self._classificar(self._wt(caminho="C:/x/aqui"))[0], "preservar")

    def test_trancado_e_citado_no_ledger_ficam_mesmo_mergeados(self):
        self.assertEqual(self._classificar(self._wt(trancado=True), ancestral=0)[0], "preservar")
        veredito, motivo = self._classificar(self._wt(), citados={"wt-um"}, ancestral=0)
        self.assertEqual(veredito, "preservar")
        self.assertIn("ledger", motivo)

    def test_arvore_suja_nunca_e_apagada(self):
        """Trabalho não commitado é o que a poda existe para NÃO perder."""
        veredito, motivo = self._classificar(self._wt(), status=(0, " M config/settings.py"), ancestral=0)
        self.assertEqual(veredito, "preservar")
        self.assertIn("não commitadas", motivo)

    def test_git_status_que_falha_preserva(self):
        self.assertEqual(self._classificar(self._wt(), status=(128, "fatal: not a git repository"))[0], "preservar")

    def test_diretorio_que_nao_existe_e_so_registro_e_sai_no_prune(self):
        veredito, motivo = self._classificar(self._wt(), existe=False)
        self.assertEqual(veredito, "apagar")
        self.assertIn("prune", motivo)

    def test_destacado_e_limpo_e_descartavel(self):
        self.assertEqual(self._classificar(self._wt(destacado=True, branch=""))[0], "apagar")

    def test_branch_ausente_no_origin_apaga_e_branch_mergeada_apaga(self):
        self.assertEqual(self._classificar(self._wt(), origem=("main",))[0], "apagar")
        self.assertEqual(self._classificar(self._wt(), ancestral=0)[0], "apagar")

    def test_branch_com_trabalho_nao_mergeado_fica(self):
        veredito, motivo = self._classificar(self._wt(), ancestral=1)
        self.assertEqual(veredito, "preservar")
        self.assertIn("não mergeado", motivo)


class LedgerTests(SimpleTestCase):
    def test_so_linhas_recentes_contam_e_o_nome_e_o_da_pasta(self):
        agora = time.localtime()
        recente = time.strftime("%Y-%m-%d %H:%M", agora)
        velha = "2026-09-01 10:00"
        texto = ("%s · ops · scripts/worktrees.py · nutriplan-design vai podar\n"
                 "%s · antiga · x · wt-velho terminou\n"
                 "linha sem data com wt-sem-data\n" % (recente, velha))
        with tempfile.TemporaryDirectory() as pasta:
            ledger = Path(pasta) / "ledger.md"
            ledger.write_text(texto, encoding="utf-8")
            with mock.patch.object(w, "LEDGER", ledger):
                self.assertEqual(w.citados_no_ledger(12), {"nutriplan-design"})
                self.assertEqual(w.citados_no_ledger(24 * 365), {"nutriplan-design", "wt-velho"})


class BancosTests(SimpleTestCase):
    def test_banco_sem_conexao_e_orfao_e_banco_conectado_e_suite_viva(self):
        """A régua é `pg_stat_activity`: uma suíte viva está conectada."""
        saida = "test_nutriplan_a_ci|1000|0\ntest_nutriplan_b_acc|2000|3\n"
        with mock.patch.object(w.subprocess, "run", return_value=mock.Mock(returncode=0, stdout=saida)), \
             mock.patch.object(w, "_git", return_value=(0, "")), \
             mock.patch.object(w, "worktrees", return_value=[]):
            relatorio = w.podar(executar=False, psql="psql-falso")
        vereditos = {b["nome"]: b["veredito"] for b in relatorio["bancos"]}
        self.assertEqual(vereditos, {"test_nutriplan_a_ci": "apagar", "test_nutriplan_b_acc": "preservar"})

    def test_apagar_banco_recusa_nome_fora_do_prefixo(self):
        """`nutriplan` (o banco de desenvolvimento) nunca passa por aqui."""
        with self.assertRaises(AssertionError):
            w.apagar_banco("psql-falso", "nutriplan")

    def test_psql_fora_do_ar_vira_aviso_e_nao_erro(self):
        with mock.patch.object(w.subprocess, "run", return_value=mock.Mock(returncode=2, stdout="", stderr="connection refused")), \
             mock.patch.object(w, "_git", return_value=(0, "")), mock.patch.object(w, "worktrees", return_value=[]):
            relatorio = w.podar(executar=False, psql="psql-falso")
        self.assertIn("bancos_erro", relatorio)
        self.assertEqual(relatorio["bancos"], [])


@skipUnless(os.name == "nt", "junção é coisa do Windows; no Linux o mesmo caminho é o symlink")
class JuncaoTests(SimpleTestCase):
    """A guarda que protege o venv compartilhado, provada com junção real."""

    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="poda-"))
        self.alvo = self.pasta / "venv-compartilhado"
        (self.alvo / "Lib").mkdir(parents=True)
        (self.alvo / "Lib" / "grande.bin").write_bytes(b"x" * 100_000)
        self.wt = self.pasta / "wt-um"
        (self.wt / "config").mkdir(parents=True)
        (self.wt / "config" / "settings.py").write_text("x = 1\n", encoding="utf-8")
        _junction(self.alvo, self.wt / ".venv")
        self.assertTrue(w.e_link(self.wt / ".venv"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_tamanho_nao_atravessa_a_juncao(self):
        """0,18 GB por worktree de 0,02 era a junção sendo contada."""
        self.assertLess(w.tamanho(self.wt), 1_000)
        self.assertGreaterEqual(w.tamanho(self.alvo), 100_000)

    def test_desligar_links_tira_a_entrada_e_deixa_o_alvo_inteiro(self):
        removidos = w.desligar_links(self.wt)
        self.assertEqual([Path(r) for r in removidos], [self.wt / ".venv"])
        self.assertFalse((self.wt / ".venv").exists())
        self.assertTrue((self.alvo / "Lib" / "grande.bin").exists())

    def test_apagar_arvore_com_juncao_dentro_preserva_o_alvo(self):
        w._apagar_arvore(self.wt)
        self.assertFalse(self.wt.exists())
        self.assertTrue((self.alvo / "Lib" / "grande.bin").exists(), "o rmtree atravessou a junção")

    def test_apagar_worktree_desliga_o_link_antes_de_chamar_o_git(self):
        """A ordem é a guarda: o git só vê a árvore depois de a junção sair."""
        ordem = []

        def git(*args, cwd=None):
            ordem.append(("git", (self.wt / ".venv").exists()))
            return 1, "não é worktree"
        with mock.patch.object(w, "_git", side_effect=git):
            self.assertEqual(w.apagar_worktree(str(self.wt)), (True, ""))
        self.assertEqual(ordem, [("git", False)])
        self.assertTrue((self.alvo / "Lib" / "grande.bin").exists())


class DiretorioSeguradoTests(SimpleTestCase):
    def test_diretorio_que_um_processo_segura_e_reportado_e_a_poda_segue(self):
        """Primeira execução real (21/09): `wt-seg` era cwd de algum shell —
        conteúdo apagado, `WinError 32` no rmdir da pasta, e o script morreu
        no 27º de 29. Hoje é erro no item, não no script."""
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "wt-preso"
            alvo.mkdir()
            with mock.patch.object(w, "_git", return_value=(1, "recusou")), \
                 mock.patch.object(w, "_apagar_arvore", side_effect=PermissionError(32, "em uso", str(alvo))):
                sumiu, erro = w.apagar_worktree(str(alvo))
            self.assertFalse(sumiu)
            self.assertIn("em uso", erro)


class ContratoTests(SimpleTestCase):
    def test_o_script_tem_dry_run_por_padrao_e_json(self):
        r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "worktrees.py"), "--help"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=str(RAIZ))
        self.assertEqual(r.returncode, 0)
        for flag in ("--podar", "--executar", "--json", "--ledger-horas", "--psql"):
            self.assertIn(flag, r.stdout)

    def test_o_claude_md_documenta_a_cadencia_semanal(self):
        """Poda que ninguém lembra de rodar é acúmulo com script."""
        for frase in ("scripts/worktrees.py --podar", "--executar"):
            self.assertTrue(frase in CLAUDE, "CLAUDE.md não cita %r" % frase)
        self.assertTrue(re.search(r"(?i)semanal|toda segunda", CLAUDE), "CLAUDE.md não diz a cadência")
