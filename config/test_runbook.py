# -*- coding: utf-8 -*-
"""O runbook de incidente (CLAUDE.md, 21/09/2026) e o script que o executa.

Quatro cenários — banco caiu, deploy quebrou, segredo vazou, Actions fora —,
cada um com o comando exato em `scripts/incidente.py`. O que estes testes
prendem, sem rede (a API do Render e a do GitHub são fakes):

* quem ESCREVE exige `--staging` ou `--producao` por extenso — o `--trocar`
  do banco caindo em produção por omissão seria o incidente seguinte;
* o valor de um segredo nunca sai em stdout — nem o gerado, nem o lido de
  arquivo, nem a chave antiga que vai para os FALLBACKS;
* a rotação da `DJANGO_SECRET_KEY` guarda a antiga em
  `DJANGO_SECRET_KEY_FALLBACKS` ANTES de trocar — e o Django continua
  aceitando o que a antiga assinou (a sessão de todo mundo);
* voltar um deploy é a promoção de sempre SEM a prova do staging, e só para
  SHA que já esteve em `main`;
* o CLAUDE.md nomeia os quatro cenários e os quatro verbos.
"""
import io
import json
import re
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from django.core import signing
from django.test import SimpleTestCase, override_settings

from scripts import incidente, promover

RAIZ = Path(__file__).resolve().parents[1]
CLAUDE_MD = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")


class ApiFalsa:
    """Grava cada chamada à API do Render e responde o que o teste mandar."""

    def __init__(self, env=None):
        self.chamadas = []
        self.env = dict(env or {})

    def __call__(self, metodo, caminho, corpo=None):
        self.chamadas.append((metodo, caminho, corpo))
        if metodo == "GET" and caminho.endswith("/env-vars?limit=100"):
            return 200, [{"envVar": {"key": k, "value": v}} for k, v in self.env.items()]
        if metodo == "GET" and "/deploys" in caminho:
            return 200, [{"deploy": {"id": "dep-1", "status": "live", "commit": {"id": "abc1234def"}, "finishedAt": "2026-09-21T05:00:00Z"}}]
        if metodo == "POST" and caminho.endswith("/deploys"):
            return 201, {"id": "dep-novo"}
        return 200, {}


def _rodar(argv, api=None, env=None):
    """Roda `incidente.main(argv)` com a rede falsa e devolve (api, stdout)."""
    api = api or ApiFalsa(env)
    saida = io.StringIO()
    with mock.patch.object(promover, "_api", api), \
            mock.patch.object(incidente, "_servico", lambda alvo: {"producao": "srv-prod", "staging": "srv-stag"}[alvo]), \
            mock.patch.object(incidente, "ROTACAO", Path(tempfile.mkdtemp())), \
            mock.patch.object(incidente, "CANONICO", {}), \
            mock.patch.object(incidente, "STAGING_ENV", Path(tempfile.mkdtemp()) / "nao-existe.json"), \
            mock.patch.object(incidente.subprocess, "run", lambda *a, **k: None), \
            mock.patch.object(incidente, "_ponta_de_main", lambda: "ma1nhead000"), \
            redirect_stdout(saida):
        incidente.main(argv)
    return api, saida.getvalue()


class QuemEscreveDizOndeTests(SimpleTestCase):
    def test_trocar_o_banco_sem_dizer_o_ambiente_e_recusado_antes_de_qualquer_chamada(self):
        api = ApiFalsa()
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as arquivo:
            arquivo.write("postgres://x:y@host/db")
        with self.assertRaisesMessage(SystemExit, "--staging ou --producao"):
            _rodar(["banco", "--trocar", arquivo.name, "--sem-esperar"], api)
        self.assertEqual(api.chamadas, [])

    def test_os_dois_ambientes_ao_mesmo_tempo_e_recusado(self):
        with self.assertRaisesMessage(SystemExit, "não os dois"):
            incidente._alvo(["--staging", "--producao"], escrita=True)

    def test_quem_le_cai_em_producao_por_padrao_e_quem_escreve_nao(self):
        self.assertEqual(incidente._alvo([], escrita=False), "producao")
        self.assertEqual(incidente._alvo(["--staging"], escrita=True), "staging")
        with self.assertRaises(SystemExit):
            incidente._alvo([], escrita=True)


class BancoCaiuTests(SimpleTestCase):
    def test_trocar_grava_a_url_do_arquivo_no_servico_certo_e_nao_a_imprime(self):
        url = "postgres://role:SENHA-QUE-NAO-PODE-SAIR@ep-x.neon.tech/db?sslmode=require"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as arquivo:
            arquivo.write(url + "\n")
        api, saida = _rodar(["banco", "--trocar", arquivo.name, "--staging", "--sem-esperar"])
        self.assertIn(("PUT", "/services/srv-stag/env-vars/DATABASE_URL", {"value": url}), api.chamadas)
        self.assertNotIn("SENHA-QUE-NAO-PODE-SAIR", saida)
        self.assertIn("DATABASE_URL", saida)

    def test_a_variavel_nova_so_vale_com_redeploy_e_ele_repete_o_commit_que_esta_no_ar(self):
        """MEDIDO em 21/09/2026 no staging: o PUT pela API não redeploya (o token
        novo respondia 403 até o deploy). E o redeploy leva `commitId` do deploy
        LIVE — sem ele o Render subiria a ponta de main, que em produção seria
        uma promoção escondida dentro de uma troca de segredo."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as arquivo:
            arquivo.write("postgres://a:b@c/d")
        api, saida = _rodar(["banco", "--trocar", arquivo.name, "--producao", "--sem-esperar"])
        self.assertEqual([c[0] for c in api.chamadas], ["PUT", "GET", "POST"])
        self.assertEqual(api.chamadas[-1], ("POST", "/services/srv-prod/deploys", {"commitId": "abc1234def", "clearCache": "do_not_clear"}))
        # O staging segue main, como o autoDeploy faria.
        api, saida = _rodar(["banco", "--trocar", arquivo.name, "--staging", "--sem-esperar"])
        self.assertEqual(api.chamadas[-1], ("POST", "/services/srv-stag/deploys", {"commitId": "ma1nhead000", "clearCache": "do_not_clear"}))

    def test_arquivo_sem_url_postgres_nao_troca_nada(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as arquivo:
            arquivo.write("isto não é uma url")
        api = ApiFalsa()
        with self.assertRaisesMessage(SystemExit, "nada foi trocado"):
            _rodar(["banco", "--trocar", arquivo.name, "--producao", "--sem-esperar"], api)
        self.assertEqual(api.chamadas, [])


class DeployQuebrouTests(SimpleTestCase):
    def test_voltar_reaproveita_o_deploy_anterior_do_commit_quando_o_render_ainda_o_tem(self):
        """MEDIDO no free em 21/09/2026: `POST /rollback {deployId}` responde 201 com
        `trigger: rollback` e vai direto a `update_in_progress` — sem build."""
        with mock.patch.object(promover, "esta_em_main", lambda sha: True):
            api, saida = _rodar(["deploy", "--voltar", "abc1234def", "--producao", "--sem-esperar"])
        self.assertEqual(api.chamadas[-1], ("POST", "/services/srv-prod/rollback", {"deployId": "dep-1"}))
        self.assertIn("rollback", saida)

    def test_voltar_sem_deploy_anterior_pede_um_deploy_novo_do_commit(self):
        with mock.patch.object(promover, "esta_em_main", lambda sha: True):
            api, saida = _rodar(["deploy", "--voltar", "0000000fff", "--staging", "--sem-esperar"])
        self.assertEqual(api.chamadas[-1], ("POST", "/services/srv-stag/deploys", {"commitId": "0000000fff"}))

    def test_voltar_nunca_passa_pela_prova_do_staging(self):
        with mock.patch.object(promover, "esta_em_main", lambda sha: True), \
                mock.patch.object(promover, "promover") as promocao, \
                mock.patch.object(promover, "saude") as saude:
            _rodar(["deploy", "--voltar", "abc1234def", "--producao", "--sem-esperar"])
        promocao.assert_not_called()
        saude.assert_not_called()

    def test_voltar_para_sha_fora_de_main_e_recusado(self):
        with mock.patch.object(promover, "esta_em_main", lambda sha: False):
            api = ApiFalsa()
            with self.assertRaisesMessage(SystemExit, "não está em origin/main"):
                _rodar(["deploy", "--voltar", "deadbeef", "--producao", "--sem-esperar"], api)
        self.assertEqual([c[0] for c in api.chamadas], ["GET"], "só a listagem; nada foi pedido")

    def test_sem_voltar_so_lista_os_deploys(self):
        api, saida = _rodar(["deploy", "--staging"])
        self.assertEqual([c[0] for c in api.chamadas], ["GET"])
        self.assertIn("abc1234", saida)


class SegredoVazouTests(SimpleTestCase):
    def test_a_secret_key_antiga_vai_para_os_fallbacks_antes_da_nova_entrar_e_nada_e_impresso(self):
        antiga = "CHAVE-ANTIGA-" + "a" * 50
        api, saida = _rodar(["rotacionar", "DJANGO_SECRET_KEY", "--staging", "--sem-esperar"], env={"DJANGO_SECRET_KEY": antiga})
        puts = [c for c in api.chamadas if c[0] == "PUT"]
        self.assertEqual([c[1] for c in puts], ["/services/srv-stag/env-vars/DJANGO_SECRET_KEY_FALLBACKS", "/services/srv-stag/env-vars/DJANGO_SECRET_KEY"])
        self.assertEqual(puts[0][2]["value"], antiga)
        nova = puts[1][2]["value"]
        self.assertGreaterEqual(len(nova), 50, "o Django exige 50+ caracteres (accounts.E005)")
        self.assertNotEqual(nova, antiga)
        self.assertNotIn(antiga, saida)
        self.assertNotIn(nova, saida)

    def test_o_django_aceita_o_que_a_chave_antiga_assinou_enquanto_ela_esta_nos_fallbacks(self):
        antiga, nova = "antiga-" * 10, "nova-" * 12
        with override_settings(SECRET_KEY=antiga, SECRET_KEY_FALLBACKS=[]):
            assinado = signing.dumps({"sessao": 1})
        with override_settings(SECRET_KEY=nova, SECRET_KEY_FALLBACKS=[antiga]):
            self.assertEqual(signing.loads(assinado), {"sessao": 1})
        with override_settings(SECRET_KEY=nova, SECRET_KEY_FALLBACKS=[]):
            with self.assertRaises(signing.BadSignature):
                signing.loads(assinado)

    def test_encerrar_apaga_os_fallbacks(self):
        api, saida = _rodar(["rotacionar", "--encerrar", "DJANGO_SECRET_KEY", "--producao", "--sem-esperar"])
        self.assertEqual(api.chamadas[0], ("DELETE", "/services/srv-prod/env-vars/DJANGO_SECRET_KEY_FALLBACKS", None))
        self.assertEqual(api.chamadas[-1][:2], ("POST", "/services/srv-prod/deploys"), "sem redeploy a antiga continua valendo")

    def test_segredo_de_terceiro_entra_por_arquivo_e_nunca_por_argumento(self):
        api = ApiFalsa()
        with self.assertRaisesMessage(SystemExit, "--de-arquivo"):
            _rodar(["rotacionar", "EMAIL_HOST_PASSWORD", "--staging", "--sem-esperar"], api)
        self.assertEqual(api.chamadas, [])
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as arquivo:
            arquivo.write("xsmtpsib-SEGREDO-DA-BREVO\n")
        api, saida = _rodar(["rotacionar", "EMAIL_HOST_PASSWORD", "--staging", "--de-arquivo", arquivo.name, "--sem-esperar"])
        self.assertEqual(api.chamadas[0], ("PUT", "/services/srv-stag/env-vars/EMAIL_HOST_PASSWORD", {"value": "xsmtpsib-SEGREDO-DA-BREVO"}))
        self.assertNotIn("SEGREDO-DA-BREVO", saida)

    def test_o_token_das_tarefas_em_producao_tambem_regrava_o_segredo_do_actions(self):
        chamadas = []
        with mock.patch.object(promover, "_api", ApiFalsa()), \
                mock.patch.object(incidente, "_servico", lambda alvo: "srv-prod"), \
                mock.patch.object(incidente, "ROTACAO", Path(tempfile.mkdtemp())), \
                mock.patch.object(incidente, "CANONICO", {}), \
                mock.patch.object(incidente.subprocess, "run", lambda cmd, **k: chamadas.append(cmd)), \
                redirect_stdout(io.StringIO()):
            incidente.main(["rotacionar", "NUTRIPLAN_TAREFAS_TOKEN", "--producao", "--sem-esperar"])
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0][1:4], [str(RAIZ / "scripts" / "github.py"), "segredo", "NUTRIPLAN_TAREFAS_TOKEN"])

    def test_nome_que_nao_e_segredo_do_app_e_recusado(self):
        with self.assertRaisesMessage(SystemExit, "não é segredo do app"):
            _rodar(["rotacionar", "QUALQUER_COISA", "--staging", "--sem-esperar"])

    def test_todo_segredo_do_app_tem_onde_mais_mora(self):
        for nome in ("DJANGO_SECRET_KEY", "NUTRIPLAN_TAREFAS_TOKEN", "NUTRIPLAN_DISPARO_TOKEN", "DATABASE_URL",
                     "EMAIL_HOST_PASSWORD", "GOOGLE_CLIENT_SECRET", "VAPID_PRIVATE_KEY", "RENDER_API_KEY"):
            self.assertIn(nome, incidente.ONDE_MAIS)


class ActionsForaTests(SimpleTestCase):
    def test_diz_a_idade_do_ultimo_run_de_cada_fluxo(self):
        from scripts import github

        def api(metodo, caminho, corpo=None):
            return 200, {"workflow_runs": [{"status": "completed", "conclusion": "success", "updated_at": "2026-09-21T05:00:00Z"}]}

        with mock.patch.object(github, "_api", api), mock.patch.object(github, "_repo", lambda: "x/y"), \
                mock.patch.object(incidente, "_get_json", lambda url, tempo=20: (200, {"components": [{"name": "Actions", "status": "operational"}]})), \
                mock.patch.object(incidente, "datetime", _Relogio):
            texto = incidente.actions(imprimir=False)
        for fluxo in incidente.FLUXOS:
            self.assertIn("%s: completed/success há 30 min" % fluxo, texto)
        self.assertIn("githubstatus Actions: operational", texto)


class _Relogio(incidente.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 21, 5, 30, tzinfo=tz)


class LembretesAMaoTests(SimpleTestCase):
    def test_manda_o_token_da_maquina_no_authorization(self):
        pedidos = []

        class Resposta:
            status = 200

            def read(self):
                return b'{"enviados": 0}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(pedido, timeout=0):
            pedidos.append(pedido)
            return Resposta()

        with mock.patch.object(incidente, "_ler_arquivo", lambda caminho: "TOKEN-DA-MAQUINA"), \
                mock.patch.object(incidente.urllib.request, "urlopen", urlopen), redirect_stdout(io.StringIO()):
            self.assertEqual(incidente.lembretes("producao"), 200)
        self.assertEqual(pedidos[0].get_header("Authorization"), "Bearer TOKEN-DA-MAQUINA")
        self.assertEqual(pedidos[0].full_url, promover.PRODUCAO + "/tarefas/lembretes/")
        self.assertEqual(pedidos[0].get_method(), "POST")


class ORunbookEstaEscritoTests(SimpleTestCase):
    def _secao(self):
        inicio = CLAUDE_MD.index("## Runbook de incidente")
        fim = CLAUDE_MD.find("\n## ", inicio + 1)
        return CLAUDE_MD[inicio:fim if fim > 0 else None]

    def test_os_quatro_cenarios_estao_no_claude_md_com_o_verbo_de_cada_um(self):
        secao = self._secao()
        for cenario, verbo in (("banco caiu", "incidente.py banco"), ("deploy quebrou", "incidente.py deploy --voltar"),
                               ("segredo vazou", "incidente.py rotacionar"), ("Actions fora", "incidente.py actions")):
            self.assertIn(cenario.lower(), secao.lower(), cenario)
            self.assertIn(verbo, secao, verbo)

    def test_todo_verbo_do_script_esta_no_runbook_e_vice_versa(self):
        secao = self._secao()
        for verbo in incidente.COMANDOS:
            self.assertIn("incidente.py " + verbo, secao, verbo)
        for verbo in re.findall(r"incidente\.py (\w+)", secao):
            self.assertIn(verbo, incidente.COMANDOS, verbo)

    def test_o_runbook_diz_que_cada_cenario_foi_ensaiado_no_staging(self):
        self.assertIn("ensaiado", self._secao().lower())

    def test_o_script_nao_imprime_valor_de_segredo(self):
        """Guarda textual, além da comportamental: nenhum `print` recebe `valor`, `url`, `token` ou `antiga` inteiros."""
        texto = (RAIZ / "scripts" / "incidente.py").read_text(encoding="utf-8")
        for linha in texto.splitlines():
            if "print(" in linha:
                # Só identificadores: fora das aspas e fora de `len(...)`.
                limpa = re.sub(r"len\(\w+\)", "", re.sub(r'"[^"]*"', '""', linha))
                self.assertIsNone(re.search(r"\b(valor|url|token|antiga)\b", limpa), linha)
