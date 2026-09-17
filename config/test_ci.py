# -*- coding: utf-8 -*-
"""O gate saiu da máquina: o CI roda a suíte inteira, e `main` só recebe PR.

Decisão do dono de 17/09/2026, depois de um push chegar ao GitHub sem
passar pelo reflog de nenhuma sessão: o pre-push local não é prova de
nada que outra pessoa consiga conferir. O gate de verdade passa a ser o
GitHub Actions — a suíte completa, o MESMO comando do pre-push, sobre o
merge do PR —, e a branch `main` ganha proteção pela API: check verde
obrigatório, branch atualizada, ninguém empurra direto (nem admin). O hook
local vira atalho: um subconjunto rápido no worktree descartável do SHA
que sobe, com a suíte inteira por trás de `NUTRIPLAN_SUITE_COMPLETA=1`.

Estes testes são TEXTUAIS, como os de `backup.yml`: eles não rodam o
Actions, mas prendem o contrato que o Actions executa — o comando, o
banco, o teto de tempo, o artefato — e o contrato do helper que abre,
espera e faz merge dos PRs sem `gh`.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
FLUXO = RAIZ / ".github" / "workflows" / "suite.yml"
HOOK = RAIZ / "scripts" / "hooks" / "pre-push"
HELPER = RAIZ / "scripts" / "github.py"

#: O comando da suíte, o mesmo nos dois lugares. Mudar aqui é mudar o gate.
COMANDO = "manage.py test --verbosity=1 --noinput"


def _sem_comentarios(texto):
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


class OFluxoDoActionsTests(SimpleTestCase):
    def _fluxo(self):
        return FLUXO.read_text(encoding="utf-8")

    def test_roda_em_push_e_pull_request_para_main(self):
        fluxo = _sem_comentarios(self._fluxo())
        self.assertRegex(fluxo, r"pull_request:\s*\n\s+branches:\s*\[?\s*-?\s*\"?main")
        self.assertRegex(fluxo, r"push:\s*\n\s+branches:\s*\[?\s*-?\s*\"?main")

    def test_a_suite_e_o_mesmo_comando_do_pre_push(self):
        """Um comando, dois lugares: o CI e o hook em modo completo. O
        `pipefail` existe porque `manage.py test | tee` devolveria o status
        do `tee` — o mesmo engano que o CLAUDE.md registra para `tail`."""
        fluxo = self._fluxo()
        self.assertIn(COMANDO, fluxo)
        self.assertIn("pipefail", fluxo)
        hook = _sem_comentarios(HOOK.read_text(encoding="utf-8"))
        self.assertIn("--verbosity=1 --noinput", hook)

    def test_o_banco_e_o_postgres_de_producao(self):
        """Neon roda 16.x em produção (CLAUDE.md, "O banco saiu do Render");
        o serviço do CI é a mesma maior."""
        fluxo = _sem_comentarios(self._fluxo())
        self.assertRegex(fluxo, r"image:\s*postgres:16")
        self.assertIn("DATABASE_URL", fluxo)

    def test_o_teto_e_quarenta_minutos_e_o_log_vira_artefato_sempre(self):
        fluxo = _sem_comentarios(self._fluxo())
        m = re.search(r"timeout-minutes:\s*(\d+)", fluxo)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 40)
        self.assertIn("actions/upload-artifact", fluxo)
        self.assertIn("if: always()", fluxo)
        self.assertIn("suite.log", fluxo)

    def test_o_fluxo_nao_le_segredo_nenhum_e_so_le_o_repositorio(self):
        """A suíte não precisa de segredo: SECRET_KEY fictícia (com os 50
        caracteres que o check E005 exige), sem DATABASE_URL de produção.
        `permissions: contents: read` é o que impede o token do fluxo de
        escrever — a mesma decisão de `backup.yml`."""
        fluxo = _sem_comentarios(self._fluxo())
        self.assertNotIn("secrets.", fluxo)
        self.assertRegex(fluxo, r"permissions:\s*\n\s+contents:\s*read")
        chave = re.search(r"DJANGO_SECRET_KEY:\s*\"?([^\"\n]+)", fluxo)
        self.assertIsNotNone(chave)
        self.assertGreaterEqual(len(chave.group(1).strip()), 50)

    def test_o_nome_do_check_e_o_que_a_protecao_exige(self):
        """O job tem o nome que a branch protection pede por texto: se um
        renomear o outro não, todo PR fica esperando um check que nunca vem."""
        from scripts import github

        fluxo = _sem_comentarios(self._fluxo())
        self.assertRegex(fluxo, r"\n\s+name:\s*\"?%s\"?\s*\n" % re.escape(github.CHECK))

    def test_a_fila_de_merge_dispara_a_suite_no_grupo(self):
        """A fila cria uma branch temporária por grupo e dispara `merge_group`;
        sem esse gatilho o check "suíte completa" nunca chega e a fila espera
        até o tempo esgotar (medido no PR #13: com `strict` e quatro sessões
        mergeando, a branch ficava "behind" no meio do check duas vezes)."""
        fluxo = _sem_comentarios(self._fluxo())
        self.assertRegex(fluxo, r"\n\s+merge_group:")
        self.assertIn("checks_requested", fluxo)

    def test_a_dependencia_tem_cache_e_o_python_e_o_do_projeto(self):
        fluxo = _sem_comentarios(self._fluxo())
        self.assertIn("actions/setup-python", fluxo)
        self.assertRegex(fluxo, r"python-version:\s*\"?3\.12")
        self.assertRegex(fluxo, r"cache:\s*\"?pip")

    def test_a_suite_roda_com_as_dependencias_de_desenvolvimento(self):
        """`config/test_requisitos_dev.py` cobra que tudo em `requirements-dev.txt`
        esteja instalado onde a suíte roda; o CI instalava só o de produção e
        o PR #4 caiu em `pillow` e `websocket-client`. O arquivo de
        desenvolvimento puxa o de produção, então a suíte vê os dois."""
        fluxo = _sem_comentarios(self._fluxo())
        self.assertIn("pip install -r requirements-dev.txt", fluxo)
        self.assertNotRegex(fluxo, r"pip install -r requirements\.txt\b")
        self.assertIn("requirements-dev.txt", fluxo.split("cache-dependency-path", 1)[1].split("- name", 1)[0])


class OHookLocalEAtalhoTests(SimpleTestCase):
    def _hook(self):
        return HOOK.read_text(encoding="utf-8")

    def test_o_atalho_roda_no_worktree_do_sha_com_um_subconjunto_nomeado(self):
        """O subconjunto é o que pega regressão cara em minutos: a régua de
        design e disciplina (`config`), o teste dourado, a doutrina, o gate
        por letra e os orçamentos de consulta."""
        hook = _sem_comentarios(self._hook())
        for alvo in ("config", "workouts.test_ficha_de_verdade", "workouts.test_treino_md",
                     "workouts.test_catalogo", "plans.test_stress"):
            self.assertIn(alvo, hook)
        self.assertIn("NUTRIPLAN_SUITE_COMPLETA", hook)

    def test_o_hook_diz_que_o_gate_e_o_ci(self):
        self.assertIn("gate", self._hook().lower())
        self.assertIn("CI", self._hook())


class OHelperDoGitHubTests(SimpleTestCase):
    def _texto(self):
        return HELPER.read_text(encoding="utf-8")

    def test_o_token_vem_do_credential_manager_e_nunca_e_impresso(self):
        """`git credential fill` é a única fonte; nenhum `print` recebe o
        token e nenhum argumento de linha de comando o carrega (ele iria
        para o histórico do shell e para o relatório)."""
        texto = _sem_comentarios(self._texto())
        self.assertIn("git", texto)
        self.assertIn("credential", texto)
        self.assertIn("fill", texto)
        self.assertNotRegex(texto, r"print\([^)]*token")
        self.assertNotIn("--token", texto)

    def test_a_protecao_exige_o_check_verde_a_branch_atualizada_e_vale_para_admin(self):
        from scripts import github

        corpo = github.corpo_da_protecao()
        self.assertEqual(corpo["required_status_checks"], {"strict": True, "contexts": [github.CHECK]})
        self.assertIs(corpo["enforce_admins"], True)
        self.assertIsNone(corpo["required_pull_request_reviews"])
        self.assertIsNone(corpo["restrictions"])
        self.assertIs(corpo["allow_force_pushes"], False)
        self.assertIs(corpo["allow_deletions"], False)

    def test_o_merge_e_por_merge_commit(self):
        """Merge commit, não squash nem rebase: os SHAs testados no PR
        continuam existindo em `main`, e o merge commit é o que `/saude/`
        mostra."""
        from scripts import github

        self.assertEqual(github.METODO_DE_MERGE, "merge")

    def test_o_check_que_conta_e_o_do_head_que_subiu(self):
        """#24 (17/09/2026): quatro minutos depois do push a API ainda
        devolvia o head antigo, já verde, e o merge saiu com o check do
        head novo `in_progress`. `_esperar_head` espera a API refletir o
        SHA local; `enfileirar` passa esse SHA a `esperar` e recusa mergear
        se o head mudar embaixo."""
        from unittest import mock

        from scripts import github

        respostas = iter([{"head": {"sha": "velho"}}, {"head": {"sha": "velho"}}, {"head": {"sha": "novo"}}])
        with mock.patch.object(github, "_pr", side_effect=lambda repo, numero: next(respostas)),                 mock.patch.object(github.time, "sleep"):
            self.assertEqual(github._esperar_head("dono/repo", 1, "novo"), "novo")
        with mock.patch.object(github, "_pr", return_value={"head": {"sha": "velho"}}),                 mock.patch.object(github.time, "sleep"),                 mock.patch.object(github.time, "time", side_effect=[0, 0, 10_000, 10_000]):
            with self.assertRaises(SystemExit) as saida:
                github._esperar_head("dono/repo", 1, "novo", minutos=1)
            self.assertEqual(saida.exception.code, 2)
        fonte = HELPER.read_text(encoding="utf-8")
        self.assertIn('"--sha", head_local.strip()', fonte)
        self.assertIn("o head mudou embaixo", fonte)

    def test_um_ticket_de_processo_morto_nao_e_vez_na_fila(self):
        """Depois do reboot de 17/09/2026 dois tickets de processos mortos
        ficaram na frente da fila, ninguém de posse, e `minha_vez` era falso
        para todo mundo, para sempre. Ticket órfão é apagado ao ser visto;
        o do processo vivo (este) continua."""
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock

        from scripts import github

        with tempfile.TemporaryDirectory() as pasta:
            fila = Path(pasta)
            (fila / "pr-1.ticket").write_text("1.0 1 %d" % os.getpid(), encoding="utf-8")
            (fila / "pr-2.ticket").write_text("0.5 2 4194304", encoding="utf-8")  # pid que não existe
            with mock.patch.object(github, "FILA", fila):
                tickets = github._tickets()
            self.assertEqual([n for _, n, _, _ in tickets], [1])
            self.assertFalse((fila / "pr-2.ticket").exists(), "o ticket órfão tinha de ser apagado")
            self.assertTrue((fila / "pr-1.ticket").exists())
        self.assertTrue(github._vivo(os.getpid()))
        self.assertFalse(github._vivo(4194304))

    def test_os_subcomandos_que_as_sessoes_usam_existem(self):
        from scripts import github

        for nome in ("pr", "status", "esperar", "merge", "proteger", "protecao", "enfileirar", "fila", "fila-ativar"):
            self.assertIn(nome, github.COMANDOS, nome)

    def test_a_fila_de_merge_e_o_gate_de_main(self):
        """O ruleset de `main`: PR obrigatório (sem push direto, admin
        inclusive — `bypass_actors` vazio), o check "suíte completa" SEM
        `strict` (a fila é quem atualiza), fila por merge commit em lotes
        pequenos, sem apagar nem forçar."""
        from scripts import github

        corpo = github.corpo_da_fila()
        self.assertEqual(corpo["enforcement"], "active")
        self.assertEqual(corpo["bypass_actors"], [])
        self.assertEqual(corpo["conditions"]["ref_name"]["include"], ["refs/heads/main"])
        regras = {r["type"]: r.get("parameters", {}) for r in corpo["rules"]}
        self.assertIn("deletion", regras)
        self.assertIn("non_fast_forward", regras)
        self.assertEqual(regras["pull_request"]["required_approving_review_count"], 0)
        self.assertEqual(regras["pull_request"]["allowed_merge_methods"], ["merge"])
        checks = regras["required_status_checks"]
        self.assertIs(checks["strict_required_status_checks_policy"], False)
        self.assertEqual([c["context"] for c in checks["required_status_checks"]], [github.CHECK])
        fila = regras["merge_queue"]
        self.assertEqual(fila["merge_method"], "MERGE")
        self.assertLessEqual(fila["max_entries_to_merge"], 2, "lote pequeno")
        self.assertLessEqual(fila["max_entries_to_build"], 2)
        self.assertGreaterEqual(fila["check_response_timeout_minutes"], 45, "a suíte leva até 40 min")
