# -*- coding: utf-8 -*-
"""`scripts/render_api.py`: ler nunca dispara.

Em 21/09/2026, procurando o log de build de um deploy, alguém chamou
`render_api.py deploy` — e o verbo DISPAROU um deploy (POST
/services/<id>/deploys, 201). Foi um redeploy do mesmo commit, sem dano; mas
o script tinha o verbo que dispara com o mesmo formato dos que só leem, e o
nome não dizia o que ele fazia. Desde então:

- os verbos vivem em DUAS tabelas, `LEITURA` e `ESCRITA`, sem interseção, e
  os que disparam carregam a palavra: `disparar-deploy`, `disparar-cron`;
- um verbo de leitura roda em modo somente-leitura, e `_req` RECUSA qualquer
  método que não seja GET antes de a rede existir — não é disciplina, é
  construção: um `cmd_status` que um dia ganhe um POST por engano cai aqui;
- `deploy` e `trigger` deixaram de ser verbos, e quem os digitar recebe o
  nome novo em vez de um disparo.

O módulo é carregado do arquivo, com uma chave falsa no ambiente e a rede
trocada por um fake que grava (método, caminho): nenhum teste aqui fala com
o Render, e o arquivo de estado (`~/.nutriplan-secrets/render_estado.json`)
vai para uma pasta temporária.
"""
import contextlib
import importlib.util
import io
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ARQUIVO = Path(settings.BASE_DIR) / "scripts" / "render_api.py"


def carregar(pasta):
    os.environ.setdefault("RENDER_API_KEY", "chave-de-teste-nunca-real")
    spec = importlib.util.spec_from_file_location("render_api_em_teste", ARQUIVO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    modulo.ESTADO = Path(pasta) / "render_estado.json"
    return modulo


class RedeFalsa:
    """Responde o bastante para cada verbo terminar, e anota o que recebeu."""

    def __init__(self):
        self.chamadas = []
        self.params_de_logs = {}

    def __call__(self, metodo, caminho, corpo=None, params=None):
        self.chamadas.append((metodo, caminho))
        if metodo != "GET":
            if caminho == "/services/srv-web/deploys":
                return 201, {"id": "dep-novo", "status": "build_in_progress"}
            return 201, {"id": "novo"}
        if caminho == "/owners":
            return 200, [{"owner": {"id": "own-1", "type": "user", "name": "dono"}, "cursor": "c1"}]
        if caminho == "/services":
            return 200, [{"service": {"id": "srv-web", "name": "nutriplan", "type": "web_service", "repo": "r",
                                      "branch": "main", "autoDeploy": "yes",
                                      "serviceDetails": {"region": "oregon", "plan": "free"}}, "cursor": "c2"}]
        if caminho == "/services/srv-web/env-vars":
            return 200, [{"envVar": {"key": "DATABASE_URL", "value": "segredo"}, "cursor": "c3"}]
        if caminho == "/services/srv-web/deploys":
            return 200, [{"deploy": {"id": "dep-1", "status": "live", "commit": {"id": "abcdef0123"},
                                     "createdAt": "2026-09-21T05:00:00Z", "finishedAt": "2026-09-21T05:03:00Z"}}]
        if caminho == "/logs":
            self.params_de_logs = dict(params or {})
            return 200, {"logs": [{"timestamp": "2026-09-21T05:00:00Z", "message": "==> Build successful"}]}
        return 404, {}


class VerbosDeLeituraNaoEscrevemTests(SimpleTestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="render-api-teste-")
        self.api = carregar(self.pasta)
        self.rede = RedeFalsa()
        self.api._http = self.rede

    def rodar(self, *args):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            self.api.executar(list(args))
        return saida.getvalue()

    def test_as_duas_tabelas_nao_se_cruzam_e_o_disparo_carrega_a_palavra(self):
        leitura, escrita = set(self.api.LEITURA), set(self.api.ESCRITA)
        self.assertEqual(leitura & escrita, set())
        self.assertIn("status", leitura)
        self.assertIn("logs", leitura)
        self.assertIn("disparar-deploy", escrita)
        self.assertNotIn("deploy", leitura | escrita, "'deploy' sem dizer o que faz foi o que disparou por engano")
        self.assertNotIn("trigger", leitura | escrita)
        for verbo in escrita:
            if "deploy" in verbo or "rodada" in verbo:
                self.assertTrue(verbo.startswith("disparar-"), verbo)

    def test_nenhum_verbo_de_leitura_manda_nada_alem_de_get(self):
        """A prova que o dono pediu: ler não cria deploy. Cada verbo de leitura
        roda inteiro contra a rede falsa, e tudo o que chegou nela é GET —
        e chegou alguma coisa, senão o teste seria vazio."""
        for verbo in self.api.LEITURA:
            self.rede.chamadas.clear()
            # `runs` termina em "sem cron" (não há cron em produção, decisão do
            # dono): sair com mensagem é resposta de leitura, não escrita.
            with contextlib.suppress(SystemExit):
                self.rodar(verbo)
            metodos = {m for m, _ in self.rede.chamadas}
            self.assertGreater(len(self.rede.chamadas), 0, "%s não falou com a API — teste vazio" % verbo)
            self.assertEqual(metodos, {"GET"}, "%s mandou %s" % (verbo, self.rede.chamadas))
            self.assertNotIn(("POST", "/services/srv-web/deploys"), self.rede.chamadas)

    def test_o_modo_de_leitura_recusa_escrita_antes_da_rede(self):
        """Por construção, não por disciplina: com o modo de leitura ligado,
        `_req` levanta antes de `_http` existir — o fake não vê nada."""
        self.api.MODO["somente_leitura"] = True
        with self.assertRaises(self.api.EscritaEmVerboDeLeitura):
            self.api._req("POST", "/services/srv-web/deploys", {"clearCache": "do_not_clear"})
        self.assertEqual(self.rede.chamadas, [])
        # controle positivo: o mesmo pedido, fora do modo de leitura, chega na rede
        self.api.MODO["somente_leitura"] = False
        self.api._req("POST", "/services/srv-web/deploys", {"clearCache": "do_not_clear"})
        self.assertEqual(self.rede.chamadas, [("POST", "/services/srv-web/deploys")])

    def test_so_disparar_deploy_cria_deploy(self):
        saida = self.rodar("disparar-deploy")
        posts = [c for c in self.rede.chamadas if c[0] != "GET"]
        self.assertEqual(posts, [("POST", "/services/srv-web/deploys")])
        self.assertIn("dep-novo", saida)

    def test_o_nome_antigo_nao_dispara_e_ensina_o_novo(self):
        for antigo, novo in (("deploy", "disparar-deploy"), ("trigger", "disparar-cron")):
            self.rede.chamadas.clear()
            with self.assertRaises(SystemExit) as saiu:
                self.rodar(antigo)
            self.assertIn(novo, str(saiu.exception))
            self.assertEqual([c for c in self.rede.chamadas if c[0] != "GET"], [], antigo)

    def test_logs_le_o_web_por_padrao_e_aceita_o_numero_de_linhas(self):
        """`logs` sem serviço caía em 'sem serviço' porque o padrão era o cron,
        que não existe; e o número de linhas era ignorado."""
        saida = self.rodar("logs")
        self.assertEqual(self.rede.params_de_logs["resource"], ["srv-web"])
        self.assertIn("Build successful", saida)
        self.rodar("logs", "srv-web", "200")
        self.assertEqual(self.rede.params_de_logs["limit"], 200)

    def test_a_ajuda_do_arquivo_lista_os_verbos_que_existem(self):
        doc = self.api.__doc__
        for verbo in list(self.api.LEITURA) + list(self.api.ESCRITA):
            self.assertIn(verbo, doc, verbo)
        self.assertNotRegex(doc, r"\n  deploy ", "a ajuda não pode anunciar o verbo que saiu")
