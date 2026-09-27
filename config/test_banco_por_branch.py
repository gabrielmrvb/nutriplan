# -*- coding: utf-8 -*-
"""Cada branch tem o seu banco de teste — e a rodada percebe quem entra nele.

Medido em 27/09/2026: o nome do banco de teste era `test_` + o NAME do `.env`
de cada worktree, disciplina manual. `nutriplan-execucao` e `nutriplan-design`
dividiam `test_nutriplan_design`; quatro worktrees caíam em `test_nutriplan`; e
o `pre-push` copiava o `.env` da raiz e testava no MESMO banco da sessão que
empurrava (colisão no ledger, 24/09). E o `RunnerUnico` conferia conexões UMA
vez, antes de criar o banco: quem entrasse depois passava despercebido e a
rodada saía verde com o resultado embaralhado.
"""
import contextlib
import importlib.util
import os
import re
import subprocess
import threading
from io import StringIO
from pathlib import Path
from unittest import mock

from django.db import connections
from django.test import SimpleTestCase

from config import branch, runner

RAIZ = Path(__file__).resolve().parent.parent
HOOK = RAIZ / "scripts" / "hooks" / "pre-push"
VARIAVEIS = (
    "NUTRIPLAN_BANCO_DE_TESTE", "NUTRIPLAN_BRANCH", "NUTRIPLAN_BANCO_SUFIXO", runner.IGNORAR,
)


def ambiente(**valores):
    """O teste controla as próprias variáveis.

    O `pre-push` exporta `NUTRIPLAN_BRANCH` e `NUTRIPLAN_BANCO_SUFIXO` para a
    rodada inteira: um teste que lesse o ambiente de quem chamou passaria — ou
    falharia — por um motivo que não é o dele.
    """
    limpo = {k: v for k, v in os.environ.items() if k not in VARIAVEIS}
    limpo.update(valores)
    return mock.patch.dict(os.environ, limpo, clear=True)


class OSlugTests(SimpleTestCase):
    def test_barra_e_hifen_viram_sublinhado(self):
        """Nome de branch tem `/` e `-`, e identificador do Postgres sem aspas
        não aceita nenhum dos dois."""
        self.assertEqual(branch.slug("missao-b/quem-entra-fica"), "missao_b_quem_entra_fica")

    def test_nome_longo_cabe_no_teto_com_hash_estavel(self):
        """O Postgres corta identificador em 63 bytes SEM avisar: duas branches
        longas com o mesmo começo virariam o mesmo banco, que é a colisão que
        isto existe para acabar. Prefixo + slug + `_push` + clone do
        `--parallel` tem de caber."""
        longo = "missao-mae/onda-1/um-nome-de-branch-comprido-demais-para-o-postgres"
        s = branch.slug(longo)

        self.assertLessEqual(len(s), 38)
        self.assertEqual(s, branch.slug(longo))
        self.assertRegex(s, r"^[a-z0-9_]{30}_[0-9a-f]{7}$")
        self.assertLessEqual(len("test_nutriplan_" + s + "_push" + "_12"), 63)

    def test_dois_nomes_longos_com_o_mesmo_comeco_nao_colidem(self):
        """Cortar sem o hash juntaria `.../onda-1/a` e `.../onda-1/b` no mesmo
        banco — a colisão entre sessões que isto existe para acabar."""
        comeco = "missao-mae/onda-1/um-nome-de-branch-comprido-demais-"
        a, b = branch.slug(comeco + "a"), branch.slug(comeco + "b")

        self.assertEqual(a[:30], b[:30])
        self.assertNotEqual(a, b)


class OBancoDeTesteTests(SimpleTestCase):
    def test_a_branch_vira_o_nome_do_banco(self):
        """Antes o nome vinha do `.env` de cada worktree, e dois worktrees com o
        mesmo NAME dividiam o banco sem saber (medido em 27/09)."""
        with ambiente(NUTRIPLAN_BRANCH="harness/banco-por-branch"):
            nome = branch.banco_de_teste("test_nutriplan", RAIZ)

        self.assertEqual(nome, "test_nutriplan_harness_banco_por_branch")

    def test_o_push_tem_banco_proprio_pelo_sufixo(self):
        """O `pre-push` roda no mesmo instante em que a sessão da mesma branch
        pode estar rodando a dela: o sufixo separa os dois bancos."""
        with ambiente(NUTRIPLAN_BRANCH="harness/banco-por-branch", NUTRIPLAN_BANCO_SUFIXO="_push"):
            nome = branch.banco_de_teste("test_nutriplan", RAIZ)

        self.assertEqual(nome, "test_nutriplan_harness_banco_por_branch_push")

    def test_nome_explicito_no_ambiente_vence_a_branch(self):
        """A saída manual: quem precisa de um banco específico (o controle
        negativo do Step 9, por exemplo) diz o nome e não depende da branch."""
        with ambiente(NUTRIPLAN_BANCO_DE_TESTE="x", NUTRIPLAN_BRANCH="harness/banco-por-branch"):
            self.assertEqual(branch.banco_de_teste("test_nutriplan", RAIZ), "x")

    def test_head_destacado_fica_no_nome_de_sempre(self):
        """CI em PR, fila e o worktree do push estão em HEAD destacado: sem
        branch, o nome é o de hoje e o CI não muda."""
        with ambiente(NUTRIPLAN_BRANCH="HEAD"):
            self.assertEqual(branch.banco_de_teste("test_nutriplan", RAIZ), "test_nutriplan")

    def test_sem_variavel_a_branch_vem_do_git(self):
        """Na sessão comum ninguém exporta nada: o nome tem de sair sozinho
        do checkout, ou a disciplina manual volta."""
        feito = subprocess.CompletedProcess([], 0, stdout="harness/banco-por-branch\n")
        with ambiente(), mock.patch.object(branch.subprocess, "run", return_value=feito):
            self.assertEqual(
                branch.banco_de_teste("test_nutriplan", RAIZ), "test_nutriplan_harness_banco_por_branch"
            )

    def test_git_destacado_ou_ausente_fica_no_nome_de_sempre(self):
        """`HEAD` não é branch (viraria `test_nutriplan_head` para todo mundo
        destacado), e sem git não saber não pode derrubar a suíte."""
        destacado = subprocess.CompletedProcess([], 0, stdout="HEAD\n")
        with ambiente(), mock.patch.object(branch.subprocess, "run", return_value=destacado):
            self.assertIsNone(branch.branch_atual(RAIZ))
            self.assertEqual(branch.banco_de_teste("test_nutriplan", RAIZ), "test_nutriplan")
        with ambiente(), mock.patch.object(branch.subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(branch.branch_atual(RAIZ))
            self.assertEqual(branch.banco_de_teste("test_nutriplan", RAIZ), "test_nutriplan")


    def test_branch_terminada_em_numero_nao_se_passa_por_clone_de_outra(self):
        """`fase-1-2` dava `..._fase_1_2`, a cara de um clone `--parallel` de
        `..._fase_1`: o runner de uma branch recusava (ou gritava INTRUSO
        contra) a rodada legítima da outra — e branch de retentativa com `-2`
        é comum aqui. O `_b` desfaz a semelhança e o pior caso ainda cabe nos
        63 do Postgres."""
        nomes = []
        for ramo in ("missao-b/fase-1", "missao-b/fase-1-2", "feature", "feature-2"):
            with ambiente(NUTRIPLAN_BRANCH=ramo):
                nomes.append(branch.banco_de_teste("test_nutriplan", RAIZ))
        for a in nomes:
            for b in nomes:
                self.assertIsNone(re.match("^" + re.escape(a) + "_[0-9]+$", b), (a, b))
        self.assertEqual(nomes[3], "test_nutriplan_feature_2_b")

        # Slug de 38 terminado em número, sem hash: 15 + 38 + 2 + 5 + 3 = 63.
        with ambiente(NUTRIPLAN_BRANCH="a" * 36 + "-1", NUTRIPLAN_BANCO_SUFIXO="_push"):
            self.assertLessEqual(len(branch.banco_de_teste("test_nutriplan", RAIZ) + "_12"), 63)


class ONomeQueORunnerUsaTests(SimpleTestCase):
    class Conexao:
        vendor = "postgresql"

        def __init__(self, nome_de_teste=None):
            self.settings_dict = {"NAME": "nutriplan", "TEST": {"NAME": nome_de_teste}}

    def test_test_name_do_settings_vence_a_branch(self):
        """Regra 6: quem escreveu `TEST.NAME` no settings escolheu — e o
        próprio runner grava o nome ali, então a segunda pergunta da rodada
        precisa devolver o mesmo nome sem chamar o git de novo."""
        with ambiente(NUTRIPLAN_BRANCH="harness/banco-por-branch"):
            self.assertEqual(runner.nome_do_banco_de_teste(self.Conexao("fixo")), "fixo")

    def test_sem_test_name_vale_o_derivado_da_branch(self):
        """É o nome que a checagem de antes e o vigia usam: se ele não
        seguisse a branch, os dois olhariam um banco e a rodada usaria outro."""
        with ambiente(NUTRIPLAN_BRANCH="harness/banco-por-branch"):
            nome = runner.nome_do_banco_de_teste(self.Conexao())

        self.assertEqual(nome, "test_nutriplan_harness_banco_por_branch")

    def test_nome_e_etiqueta_ja_estao_gravados_quando_o_django_cria_o_banco(self):
        """Derivar o nome não basta: o Django cria `test_` + NAME a menos que
        `TEST.NAME` diga outra coisa — a checagem olharia um banco e a rodada
        criaria outro. E a etiqueta (`PGAPPNAME`) é como o vigia separa as
        conexões DESTA rodada das de fora; gravada depois, as conexões da
        criação sairiam sem ela."""
        conexao = self.Conexao()
        visto = {}

        def criou(*_, **__):
            visto["nome"] = conexao.settings_dict["TEST"]["NAME"]
            visto["etiqueta"] = os.environ.get("PGAPPNAME")
            return []

        with ambiente(NUTRIPLAN_BRANCH="harness/banco-por-branch"), \
                mock.patch.object(runner, "connections", {"default": conexao}), \
                mock.patch.object(runner, "conexoes_ativas", return_value=[]) as perguntou, \
                mock.patch("django.test.runner.DiscoverRunner.setup_databases", side_effect=criou):
            runner.RunnerUnico().setup_databases()

        self.assertEqual(visto, {
            "nome": "test_nutriplan_harness_banco_por_branch",
            "etiqueta": "nutriplan-teste-%d" % os.getpid(),
        })
        perguntou.assert_called_once_with(conexao, "test_nutriplan_harness_banco_por_branch")


class OVigiaTests(SimpleTestCase):
    """Quem entra no banco de teste NO MEIO da rodada invalida a rodada."""

    def test_intruso_no_meio_da_rodada_soma_uma_falha_e_avisa(self):
        """O caso de 24/09: duas execuções no mesmo banco, e a que saiu verde
        tinha medido o dado da outra. Verde com intruso é mentira."""
        r = runner.RunnerUnico()

        def suite(*_, **__):
            r._conferir("test_nutriplan_x", "nutriplan-teste-1")
            return 2

        with mock.patch.object(runner, "intrusos", return_value=[(4242, "psql")]), \
                mock.patch("django.test.runner.DiscoverRunner.run_tests", side_effect=suite), \
                mock.patch("sys.stderr", new_callable=StringIO) as erro:
            falhas = r.run_tests([])

        self.assertEqual(falhas, 3)
        self.assertIn("INTRUSO no banco de teste test_nutriplan_x: pid 4242 (app 'psql')", erro.getvalue())

    def test_sem_intruso_o_numero_de_falhas_nao_muda(self):
        """O controle positivo do teste de cima: sem intruso, o vigia não pode
        inventar falha nem escrever no stderr de uma rodada limpa."""
        r = runner.RunnerUnico()

        def suite(*_, **__):
            r._conferir("test_nutriplan_x", "nutriplan-teste-1")
            return 0

        with mock.patch.object(runner, "intrusos", return_value=[]), \
                mock.patch("django.test.runner.DiscoverRunner.run_tests", side_effect=suite), \
                mock.patch("sys.stderr", new_callable=StringIO) as erro:
            falhas = r.run_tests([])

        self.assertEqual(falhas, 0)
        self.assertEqual(erro.getvalue(), "")

    def test_o_vigia_liga_depois_de_criar_o_banco_e_para_antes_de_apagar(self):
        """Ligado antes, ele veria a própria criação; desligado depois, o DROP
        do fim encontraria o vigia no caminho. E ele pergunta pelo banco
        certo, com a etiqueta desta rodada."""
        r = runner.RunnerUnico()
        r.intervalo_do_vigia = 0.01
        perguntou = threading.Event()
        with ambiente(), \
                mock.patch.object(runner, "conexoes_ativas", return_value=[]), \
                mock.patch.object(runner, "intrusos", side_effect=lambda *a: perguntou.set() or []) as intrusos, \
                mock.patch("django.test.runner.DiscoverRunner.setup_databases", return_value=["criou"]), \
                mock.patch("django.test.runner.DiscoverRunner.teardown_databases"):
            r.setup_databases()
            self.assertTrue(perguntou.wait(5), "o vigia não perguntou nada")
            vigia = r._vigia
            r.teardown_databases(["criou"])

        self.assertFalse(vigia.is_alive())
        nome = connections["default"].settings_dict["TEST"]["NAME"]
        intrusos.assert_called_with(nome, "nutriplan-teste-%d" % os.getpid())


class OQueOVigiaPerguntaTests(SimpleTestCase):
    """O SQL de verdade, com um cursor falso — no molde de
    `OQueORunnerPerguntaTests` (`config/test_b9_disciplina.py`): os testes do
    vigia trocam `intrusos` inteiro, e sem isto os filtros que separam "nós" de
    "intruso" podiam sumir com a suíte verde."""

    class Falso:
        vendor = "postgresql"

        def __init__(self, explode=False):
            self.explode = explode
            self.sql = self.params = None

        @contextlib.contextmanager
        def _nodb_cursor(self):
            if self.explode:
                raise RuntimeError("banco fora do ar")
            yield self

        def cursor(self):
            return self._nodb_cursor()

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [(4242, "psql")]

    def _intrusos(self, falso):
        with mock.patch.object(runner, "connections", {"default": falso}):
            return runner.intrusos("test_nutriplan_x", "nutriplan-teste-1")

    def test_o_vigia_so_conta_cliente_de_fora_da_rodada_no_banco_e_nos_clones(self):
        """Sem `backend_type`, um autovacuum no banco de teste vira INTRUSO
        intermitente — a falha mais difícil de diagnosticar; sem a etiqueta, a
        própria rodada seria o intruso e TODA rodada reprovaria. Nome e regex
        dos clones vão como parâmetro, nunca colados no SQL."""
        falso = self.Falso()

        self.assertEqual(self._intrusos(falso), [(4242, "psql")])
        self.assertIn("backend_type = 'client backend'", falso.sql)
        self.assertIn("COALESCE(application_name, '') <> %s", falso.sql)
        self.assertIn("datname = %s OR datname ~ %s", falso.sql)
        self.assertEqual(
            falso.params, ["test_nutriplan_x", r"^test_nutriplan_x_[0-9]+$", "nutriplan-teste-1"]
        )

    def test_falha_ao_perguntar_nao_vira_intruso(self):
        """A filosofia de `conexoes_ativas`: um Postgres piscando não pode
        reprovar uma rodada limpa."""
        self.assertIsNone(self._intrusos(self.Falso(explode=True)))

    def test_a_checagem_de_antes_tambem_so_conta_cliente(self):
        """Com `--keepdb` o banco do push persiste entre pushes: um autovacuum
        nele na hora do próximo push aparecia como "alguém conectado" e
        recusava um push legítimo."""
        falso = self.Falso()

        runner.conexoes_ativas(falso, "test_nutriplan_x")

        self.assertIn("backend_type = 'client backend'", falso.sql)


class OPrePushUsaOBancoDaBranchTests(SimpleTestCase):
    """Leitura textual, como `config/test_ci.py` faz com o mesmo hook."""

    def _codigo(self):
        texto = HOOK.read_text(encoding="utf-8")
        return "\n".join(x for x in texto.splitlines() if not x.lstrip().startswith("#"))

    def _linha_do_teste(self):
        linhas = [x for x in self._codigo().splitlines() if "manage.py test" in x]
        self.assertEqual(len(linhas), 1, linhas)
        return linhas[0]

    def test_o_push_testa_no_banco_da_branch_que_sobe_com_sufixo(self):
        """O worktree do push está destacado, e o `.env` copiado é o da raiz:
        sem a branch exportada do `remote_ref`, o push cairia no banco de outra
        sessão — a colisão de 24/09."""
        codigo = self._codigo()

        self.assertIn('ramo="${remote_ref#refs/heads/}"', codigo)
        self.assertRegex(codigo, r'export NUTRIPLAN_BRANCH="\$ramo" NUTRIPLAN_BANCO_SUFIXO=_push')
        self.assertLess(codigo.index("export NUTRIPLAN_BRANCH"), codigo.index("manage.py test"))

    def test_o_push_reaproveita_o_banco_com_keepdb(self):
        """45 s de migração a cada push viram segundos: o banco do push é
        dele, então mantê-lo entre um push e outro não embaralha ninguém."""
        self.assertIn("--noinput --keepdb", self._linha_do_teste())

    def test_o_log_do_push_leva_o_slug_da_branch(self):
        """Dois pushes de branches diferentes ao mesmo tempo escreviam no
        mesmo log — e o `tee` com `pipefail` mantém o código de saída do
        teste mandando. O caminho sai ANTES do teste: com `errexit`, um push
        reprovado nunca chegava ao `echo` do fim, e é na falha que o log vale."""
        codigo = self._codigo()

        self.assertIn('LOG="${TMPDIR:-/tmp}/nutriplan-push-$slug.log"', codigo)
        self.assertLess(codigo.index('echo "→ log: $LOG"'), codigo.index("manage.py test"))
        self.assertRegex(codigo, r"from config\.branch import slug")
        self.assertIn('| tee "$LOG"', self._linha_do_teste())
        self.assertIn("pipefail", codigo)

    def test_o_slug_vem_do_sha_que_sobe_e_sha_antigo_nao_barra_o_push(self):
        """A `$RAIZ` pode ser o checkout principal, sem `config/branch.py`
        antes do merge — e o `python -c` morto derrubaria o push pelo
        `errexit`. O `$WT` é o SHA que sobe, o mesmo commit do hook; um SHA
        antigo sem o arquivo cai em `sem_branch` em vez de recusar."""
        codigo = self._codigo()
        linha = next(x for x in codigo.splitlines() if "from config.branch import slug" in x)

        self.assertIn('[ -f "$WT/config/branch.py" ] && slug=', linha)
        self.assertIn('"$WT" "$ramo"', linha)
        self.assertNotIn("$RAIZ", linha)
        self.assertIn("slug=sem_branch", codigo)
        self.assertLess(codigo.index("git worktree add"), codigo.index("from config.branch import slug"))


class OLogDoFundoLevaABranchTests(SimpleTestCase):
    def test_log_padrao_separa_por_branch_e_sem_branch_fica_como_era(self):
        """Duas sessões em branches diferentes notificando ao mesmo tempo
        escreviam no mesmo `nutriplan-notificar.log`."""
        spec = importlib.util.spec_from_file_location("fundo", RAIZ / "scripts" / "fundo.py")
        fundo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fundo)

        with mock.patch.object(branch, "branch_atual", return_value="harness/banco-por-branch"):
            self.assertEqual(fundo._log_padrao("x").name, "nutriplan-harness_banco_por_branch-x.log")
        with mock.patch.object(branch, "branch_atual", return_value=None):
            self.assertEqual(fundo._log_padrao("x").name, "nutriplan-x.log")
