# -*- coding: utf-8 -*-
"""O gate saiu da máquina, e desde 18/09/2026 ele é RÁPIDO.

Decisão do dono de 17/09/2026: o gate de verdade é o GitHub Actions, não o
pre-push de uma máquina só. Decisão de 18/09/2026: esse gate leva menos de
10 minutos. A suíte inteira, serial, executava em ~31 min (medido nos
últimos 10 runs: instalar ~10 s com cache, o resto é o `manage.py test`), e
com a fila local empilhando PRs cada um esperava ~32 min de runner. O
repositório é PRIVADO — minuto de Actions é metered —, então PR de 32 min é
espera E custo.

São DOIS fluxos:

  * `suite-rapida.yml` → check "suíte rápida": o GATE. `--parallel auto`
    (um processo por vCPU; o `RunnerUnico` conta os clones) e
    `--exclude-tag lento` (os testes pesados de estatística/estresse). Roda
    em todo PR. É o check que `scripts/github.py` (CHECK) espera antes de
    mergear;
  * `suite.yml` → check "suíte completa": TUDO, inclusive `lento`, DEPOIS do
    merge (`push: main`), à noite (`schedule`) e à mão (`workflow_dispatch`).
    Não barra PR.

Estes testes são TEXTUAIS, como os de `backup.yml`: não rodam o Actions,
mas prendem o contrato que ele executa, e o contrato do helper que espera e
mergeia sem `gh`.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
FLUXO_RAPIDA = RAIZ / ".github" / "workflows" / "suite-rapida.yml"
FLUXO_COMPLETA = RAIZ / ".github" / "workflows" / "suite.yml"
HOOK = RAIZ / "scripts" / "hooks" / "pre-push"
HELPER = RAIZ / "scripts" / "github.py"


def _sem_comentarios(texto):
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


class OGateRapidoTests(SimpleTestCase):
    """`suite-rapida.yml`: o check que barra o merge, em < 10 min."""

    def _fluxo(self):
        return _sem_comentarios(FLUXO_RAPIDA.read_text(encoding="utf-8"))

    def test_o_nome_do_job_e_o_check_que_o_helper_espera(self):
        """O job tem o nome que `scripts/github.py` (CHECK) aguarda: se um
        renomear e o outro não, todo PR fica esperando um check que nunca
        vem — e como o repositório é privado não há branch protection do
        servidor para avisar, só a fila local."""
        from scripts import github

        self.assertRegex(self._fluxo(), r"\n\s+name:\s*\"?%s\"?\s*\n" % re.escape(github.CHECK))
        self.assertEqual(github.CHECK, "suíte rápida")

    def test_roda_em_pull_request_para_main(self):
        self.assertRegex(self._fluxo(), r"pull_request:\s*\n\s+branches:\s*\[?\s*-?\s*\"?main")

    def test_e_fatiada_e_exclui_os_lentos(self):
        """O ganho vem de FATIAR (`ci/shard.py`), cada fatia serial e os jobs
        em paralelo — não de `--parallel` do Django, que morre com `cannot
        pickle 'traceback'` quando um teste de ordem-de-PK cai (medido no PR
        #33). E `--exclude-tag lento` tira os pesados do caminho de todo PR."""
        fluxo = FLUXO_RAPIDA.read_text(encoding="utf-8")
        self.assertIn("manage.py test", fluxo)
        self.assertIn("ci/shard.py", fluxo)
        self.assertIn("--exclude-tag lento", fluxo)
        self.assertIn("--verbosity=1 --noinput", fluxo)
        self.assertIn("pipefail", fluxo)
        # O comentário EXPLICA por que não usamos `--parallel`; o que importa é
        # que o COMANDO não o traga.
        self.assertNotIn("--parallel", _sem_comentarios(fluxo))

    def test_o_gate_fica_verde_so_com_todas_as_fatias(self):
        """O job `gate` (o check que o helper espera) depende das fatias e só
        passa se todas passarem — senão uma fatia vermelha entraria em `main`
        pela porta do check verde."""
        fluxo = self._fluxo()
        self.assertRegex(fluxo, r"needs:\s*\[?\s*fatia")
        self.assertIn("needs.fatia.result", fluxo)

    def test_a_particao_cobre_todo_modulo_sem_orfao(self):
        """Fatiar por lista escrita à mão esqueceria um arquivo novo — e um
        módulo em NENHUMA fatia nunca roda no gate (buraco de cobertura). A
        partição de `ci/shard.py` cobre TODO módulo descoberto, sem repetir."""
        import re as _re

        from ci import shard

        fluxo = FLUXO_RAPIDA.read_text(encoding="utf-8")
        m = _re.search(r"ci/shard\.py \$\{\{ matrix\.i \}\} (\d+)", fluxo)
        self.assertIsNotNone(m, "o comando tem de chamar ci/shard.py com o total de fatias")
        n = int(m.group(1))
        matriz = _re.search(r"matrix:\s*\n\s*i:\s*\[([0-9,\s]+)\]", fluxo)
        self.assertIsNotNone(matriz)
        indices = [int(x) for x in matriz.group(1).split(",")]
        self.assertEqual(sorted(indices), list(range(n)), "a matriz tem de ter uma entrada por fatia")

        todos = shard.modulos()
        self.assertIn("config.test_ci", todos)
        fatias = shard.particionar(n)
        uniao = sorted(x for f in fatias for x in f)
        self.assertEqual(uniao, todos, "toda fatia coberta, sem órfão")
        self.assertEqual(len(uniao), len(set(uniao)), "sem módulo em duas fatias")

    def test_o_teto_da_fatia_e_curto(self):
        m = re.search(r"timeout-minutes:\s*(\d+)", self._fluxo())
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 20)

    def test_sem_segredo_postgres_de_producao_e_cache(self):
        fluxo = self._fluxo()
        self.assertNotIn("secrets.", fluxo)
        self.assertRegex(fluxo, r"permissions:\s*\n\s+contents:\s*read")
        self.assertRegex(fluxo, r"image:\s*postgres:16")
        self.assertRegex(fluxo, r"python-version:\s*\"?3\.12")
        self.assertRegex(fluxo, r"cache:\s*\"?pip")
        self.assertIn("pip install -r requirements-dev.txt", fluxo)
        chave = re.search(r"DJANGO_SECRET_KEY:\s*\"?([^\"\n]+)", fluxo)
        self.assertIsNotNone(chave)
        self.assertGreaterEqual(len(chave.group(1).strip()), 50)


class ASuiteCompletaTests(SimpleTestCase):
    """`suite.yml`: tudo, depois do merge e à noite — não barra PR."""

    def _fluxo(self):
        return _sem_comentarios(FLUXO_COMPLETA.read_text(encoding="utf-8"))

    def test_o_job_e_a_suite_completa(self):
        self.assertRegex(self._fluxo(), r"\n\s+name:\s*\"?suíte completa\"?\s*\n")

    def test_roda_depois_do_merge_a_noite_e_a_mao(self):
        """Pós-merge prova o commit que entrou; o cron noturno pega quebra
        que dependa de calendário antes do primeiro PR do dia; o dispatch é
        o gatilho manual."""
        fluxo = self._fluxo()
        self.assertRegex(fluxo, r"push:\s*\n\s+branches:\s*\[?\s*-?\s*\"?main")
        self.assertRegex(fluxo, r"schedule:\s*\n\s+-\s*cron:")
        self.assertIn("workflow_dispatch:", fluxo)

    def test_roda_a_suite_inteira_fatiada_sem_excluir_nada(self):
        """A completa NÃO exclui `lento` — é onde os pesados rodam. E é
        fatiada como a rápida (cada fatia serial), senão o pós-merge levaria
        os ~31 min de antes."""
        fluxo = FLUXO_COMPLETA.read_text(encoding="utf-8")
        self.assertIn("manage.py test", fluxo)
        self.assertIn("ci/shard.py", fluxo)
        self.assertIn("--verbosity=1 --noinput", fluxo)
        self.assertIn("pipefail", fluxo)
        # Os `--parallel`/`--exclude-tag` do comentário (que explicam a
        # escolha) não contam: o que importa é o COMANDO da completa.
        sem = _sem_comentarios(fluxo)
        self.assertNotIn("--parallel", sem)
        self.assertNotIn("--exclude-tag", sem)

    def test_teto_de_quarenta_minutos_e_log_sempre(self):
        fluxo = self._fluxo()
        m = re.search(r"timeout-minutes:\s*(\d+)", fluxo)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 40)
        self.assertIn("actions/upload-artifact", fluxo)
        self.assertIn("if: always()", fluxo)
        self.assertIn(".log", fluxo)

    def test_sem_segredo_e_contents_read(self):
        fluxo = self._fluxo()
        self.assertNotIn("secrets.", fluxo)
        self.assertRegex(fluxo, r"permissions:\s*\n\s+contents:\s*read")


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
        texto = _sem_comentarios(self._texto())
        self.assertIn("git", texto)
        self.assertIn("credential", texto)
        self.assertIn("fill", texto)
        self.assertNotRegex(texto, r"print\([^)]*token")
        self.assertNotIn("--token", texto)

    def test_o_check_que_o_helper_espera_e_o_gate_rapido(self):
        from scripts import github

        self.assertEqual(github.CHECK, "suíte rápida")

    def test_esperar_aceita_sha_do_head_que_acabou_de_subir(self):
        """A fila mergeia o head certo: `esperar --sha X` conta só o check
        DESSE commit, não o de um head velho cancelado (achado do PR #32)."""
        texto = self._texto()
        self.assertIn("--sha", texto)
        self.assertIn("_esperar_head", texto)

    def test_a_fila_roda_num_worktree_proprio_e_nao_trava_a_sessao(self):
        """`enfileirar` faz merge/push/merge num WORKTREE descartável, não na
        árvore da sessão — assim a sessão segue trabalhando enquanto a fila
        anda (18/09/2026). Não exige mais a branch em HEAD, e o push do
        worktree pula o atalho local (`--no-verify`): o gate é o check do CI
        que a fila espera sobre o mesmo SHA."""
        texto = _sem_comentarios(self._texto())
        self.assertIn("worktree", texto)
        self.assertIn('"worktree", "add", "--detach"', texto)
        self.assertIn("worktree", texto.split("remove", 1)[0])  # tem remove no finally
        self.assertNotIn("rode na árvore com ela em HEAD", texto)
        self.assertIn("--no-verify", texto)

    def test_a_protecao_e_a_fila_apontam_para_o_check_do_gate(self):
        """Proteção clássica e ruleset (os dois hoje inertes — o repositório é
        privado e a API recusa ambos com 403; ficam prontos para o dia em que
        o repositório morar numa organização) exigem o MESMO check que o
        helper espera."""
        from scripts import github

        self.assertEqual(
            github.corpo_da_protecao()["required_status_checks"],
            {"strict": True, "contexts": [github.CHECK]},
        )
        regras = {r["type"]: r.get("parameters", {}) for r in github.corpo_da_fila()["rules"]}
        checks = regras["required_status_checks"]["required_status_checks"]
        self.assertEqual([c["context"] for c in checks], [github.CHECK])

    def test_o_merge_e_por_merge_commit(self):
        from scripts import github

        self.assertEqual(github.METODO_DE_MERGE, "merge")

    def test_os_subcomandos_que_as_sessoes_usam_existem(self):
        from scripts import github

        for nome in ("pr", "status", "esperar", "merge", "proteger", "protecao", "enfileirar", "fila", "fila-ativar"):
            self.assertIn(nome, github.COMANDOS, nome)

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

    def test_a_fila_do_github_e_por_merge_commit_em_lotes_pequenos(self):
        """O ruleset (inerte hoje — repositório privado): merge commit, lotes
        de no máximo dois, sem `strict` (a fila é quem atualiza), sem push
        direto nem apagar, sem revisor obrigatório."""
        from scripts import github

        corpo = github.corpo_da_fila()
        self.assertEqual(corpo["enforcement"], "active")
        self.assertEqual(corpo["bypass_actors"], [])
        regras = {r["type"]: r.get("parameters", {}) for r in corpo["rules"]}
        self.assertIn("deletion", regras)
        self.assertIn("non_fast_forward", regras)
        self.assertEqual(regras["pull_request"]["required_approving_review_count"], 0)
        self.assertEqual(regras["pull_request"]["allowed_merge_methods"], ["merge"])
        self.assertIs(regras["required_status_checks"]["strict_required_status_checks_policy"], False)
        fila = regras["merge_queue"]
        self.assertEqual(fila["merge_method"], "MERGE")
        self.assertLessEqual(fila["max_entries_to_merge"], 2)
