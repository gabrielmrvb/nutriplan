# -*- coding: utf-8 -*-
"""A REGRA DA PROMOÇÃO (decisão do dono, 21/09/2026): produção só muda no fim
de um lote PROVADO (smoke + E2E verdes no staging), no máximo uma vez por
hora; fora disso, produção não muda.

Sem rede: a API do Render, o `/saude/`, o smoke e o E2E são fakes. O que se
prende, cenário a cenário:

* produção já na ponta de main → nada a fazer, nenhum POST;
* staging atrás de main → nada sobe (e não é "adiado": é "não provado");
* última promoção há menos de 60 min → ADIADO, nenhum POST, saída 0 — é
  isto que faz dois merges seguidos virarem uma promoção só;
* janela aberta + smoke + E2E verdes → a promoção de sempre;
* smoke ou E2E vermelho → NÃO sobe, saída 1 — mesmo com `--forcar-janela`;
* `--forcar-janela` ignora o relógio e nunca a prova;
* a fila chama a regra no fim de todo merge; o cron a chama de meia em meia
  hora; o botão continua sendo a exceção nomeada.
"""
import io
import re
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from scripts import promover

RAIZ = Path(__file__).resolve().parents[1]
LOTE = (RAIZ / ".github" / "workflows" / "promover-lote.yml").read_text(encoding="utf-8")
BOTAO = (RAIZ / ".github" / "workflows" / "promover.yml").read_text(encoding="utf-8")
HELPER = (RAIZ / "scripts" / "github.py").read_text(encoding="utf-8")


def sem_comentarios(texto):
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


class Cenario:
    """Um estado do mundo: ponta de main, commits do staging e de produção,
    idade da última promoção, e o que smoke e E2E respondem."""

    def __init__(self, main="abc1234def", staging="abc1234", producao="0ld0000", idade=120, smoke_ok=True, e2e_ok=True):
        self.main, self.staging, self.producao, self.idade = main, staging, producao, idade
        self.smoke_ok, self.e2e_ok = smoke_ok, e2e_ok
        self.posts, self.e2e_rodou = [], 0

    def api(self, metodo, caminho, corpo=None):
        if metodo == "POST":
            self.posts.append((caminho, corpo))
            return 201, {"id": "dep-novo"}
        return 200, {}

    def saude(self, base, tempo=90):
        if base == promover.STAGING:
            return {"status": "ok", "commit": self.staging, "ambiente": "staging"}
        return {"status": "ok", "commit": self.producao, "ambiente": ""}

    def smoke(self, base):
        return [(rota, 200 if self.smoke_ok else 503) for rota in promover.ROTAS_DO_SMOKE]

    def e2e(self, base):
        self.e2e_rodou += 1
        return self.e2e_ok

    def rodar(self, **kw):
        saida = io.StringIO()
        with mock.patch.object(promover, "_api", self.api), mock.patch.object(promover, "saude", self.saude), \
                mock.patch.object(promover, "smoke", self.smoke), mock.patch.object(promover, "e2e", self.e2e), \
                mock.patch.object(promover, "_ponta_de_main", lambda: self.main), \
                mock.patch.object(promover, "minutos_desde_a_ultima_promocao", lambda: self.idade), \
                mock.patch.object(promover, "esta_em_main", lambda sha: True), \
                mock.patch.object(promover, "esperar_commit", lambda base, curto, minutos, rotulo: self.saude(base) if self.saude(base)["commit"] == curto else None), \
                mock.patch.object(promover.time, "sleep", lambda s: None), redirect_stdout(saida):
            codigo = promover.promover_lote(**kw)
        return codigo, saida.getvalue()


class ARegraDoLoteTests(SimpleTestCase):
    def test_producao_ja_na_ponta_de_main_nao_faz_nada(self):
        c = Cenario(producao="abc1234")
        codigo, saida = c.rodar()
        self.assertEqual(codigo, 0)
        self.assertEqual(c.posts, [])
        self.assertIn("nada a promover", saida)

    def test_staging_atras_de_main_nao_sobe_e_nao_e_adiado(self):
        c = Cenario(staging="1111111")
        codigo, saida = c.rodar()
        self.assertEqual(codigo, 2)
        self.assertEqual(c.posts, [])
        self.assertIn("NÃO PROVADO", saida)
        self.assertEqual(c.e2e_rodou, 0)

    def test_janela_fechada_adia_o_lote_e_producao_nao_muda(self):
        """Dois merges seguidos: o primeiro promoveu há 20 min; o segundo é ADIADO
        e vai junto no próximo `--lote` — uma promoção só."""
        c = Cenario(idade=20)
        codigo, saida = c.rodar()
        self.assertEqual(codigo, 0)
        self.assertEqual(c.posts, [], "produção não muda fora da janela")
        self.assertIn("LOTE ADIADO", saida)
        self.assertIn("há 20 min", saida)
        self.assertEqual(c.e2e_rodou, 0, "não gasta E2E num lote que não vai subir agora")

    def test_janela_aberta_com_prova_verde_promove(self):
        c = Cenario(idade=61)
        with mock.patch.object(promover, "promover", return_value=0) as promocao:
            codigo, saida = c.rodar()
        self.assertEqual(codigo, 0)
        promocao.assert_called_once_with("abc1234def", esperar=True, minutos=15, forcar_janela=True)
        self.assertEqual(c.e2e_rodou, 1)
        self.assertIn("LOTE PROVADO", saida)

    def test_no_limite_da_janela_59_min_adia_e_60_promove(self):
        with mock.patch.object(promover, "promover", return_value=0) as promocao:
            codigo, saida = Cenario(idade=59).rodar()
            self.assertIn("LOTE ADIADO", saida)
            promocao.assert_not_called()
            codigo, saida = Cenario(idade=60).rodar()
            promocao.assert_called_once()

    def test_e2e_vermelho_nao_sobe_e_sai_com_1(self):
        c = Cenario(e2e_ok=False)
        with mock.patch.object(promover, "promover") as promocao:
            codigo, saida = c.rodar()
        self.assertEqual(codigo, 1)
        promocao.assert_not_called()
        self.assertIn("REPROVADO no E2E", saida)

    def test_smoke_vermelho_nao_sobe_nem_gasta_e2e(self):
        c = Cenario(smoke_ok=False)
        with mock.patch.object(promover, "promover") as promocao:
            codigo, saida = c.rodar()
        self.assertEqual(codigo, 1)
        promocao.assert_not_called()
        self.assertEqual(c.e2e_rodou, 0)
        self.assertIn("REPROVADO no smoke", saida)

    def test_forcar_janela_ignora_o_relogio_mas_nunca_a_prova(self):
        c = Cenario(idade=5, e2e_ok=False)
        with mock.patch.object(promover, "promover") as promocao:
            codigo, saida = c.rodar(forcar_janela=True)
        self.assertEqual(codigo, 1)
        promocao.assert_not_called()
        self.assertIn("JANELA FORÇADA", saida)
        self.assertIn("REPROVADO no E2E", saida)
        c = Cenario(idade=5)
        with mock.patch.object(promover, "promover", return_value=0) as promocao:
            codigo, saida = c.rodar(forcar_janela=True)
        promocao.assert_called_once()

    def test_sem_e2e_fica_dito_no_log(self):
        c = Cenario()
        with mock.patch.object(promover, "promover", return_value=0):
            codigo, saida = c.rodar(sem_e2e=True)
        self.assertEqual(c.e2e_rodou, 0)
        self.assertIn("E2E PULADO", saida)

    def test_a_janela_e_de_uma_hora(self):
        self.assertEqual(promover.JANELA_MIN, 60)

    def test_o_smoke_cobre_as_rotas_publicas_e_o_readiness(self):
        for rota in ("/", "/conta/entrar/", "/saude/", "/demo/"):
            self.assertIn(rota, promover.ROTAS_DO_SMOKE)


class APromocaoAMaoRespeitaAJanelaTests(SimpleTestCase):
    """Uma sessão promoveu o próprio SHA 10 min depois do lote (20:17Z, 21/09):
    a janela vale para `promover.py <sha>` também. `--forcar-janela` é a
    porta do hotfix e do rollback."""

    def _promover(self, idade, **kw):
        posts = []
        with mock.patch.object(promover, "esta_em_main", lambda sha: True), \
                mock.patch.object(promover, "minutos_desde_a_ultima_promocao", lambda: idade), \
                mock.patch.object(promover, "saude", lambda base, tempo=90: {"commit": "abc1234", "ambiente": "staging"}), \
                mock.patch.object(promover, "_api", lambda m, c, corpo=None: (posts.append((m, c)), (201, {"id": "dep"}))[1]), \
                redirect_stdout(io.StringIO()):
            codigo = promover.promover("abc1234def", **kw)
        return codigo, posts

    def test_dentro_da_janela_e_recusada(self):
        with self.assertRaisesMessage(SystemExit, "janela de 60"):
            self._promover(idade=10)

    def test_fora_da_janela_ou_forcada_promove(self):
        codigo, posts = self._promover(idade=61)
        self.assertEqual([c for _, c in posts], ["/services/%s/deploys" % promover.SERVICO_PRODUCAO])
        codigo, posts = self._promover(idade=10, forcar_janela=True)
        self.assertEqual(len(posts), 1)

    def test_o_botao_tem_a_porta_do_hotfix(self):
        self.assertIn("forcar_janela:", BOTAO)
        self.assertIn("--forcar-janela", BOTAO)


class QuemRodaARegraTests(SimpleTestCase):
    def test_a_fila_tenta_o_lote_no_fim_de_todo_merge_e_nao_promove_direto(self):
        enfileirar = HELPER[HELPER.index("def cmd_enfileirar"):HELPER.index("def _provar_staging")]
        self.assertIn("_provar_staging(sha_merge)", enfileirar)
        self.assertIn("_promover_lote(", enfileirar)
        self.assertNotIn("cmd_promover([sha_merge", enfileirar, "o merge não promove um SHA direto: é a regra do lote")
        self.assertIn('"promover-lote"', HELPER.split("COMANDOS = ", 1)[1].split("\n", 1)[0])

    def test_o_cron_roda_a_regra_de_meia_em_meia_hora_com_o_e2e(self):
        corpo = sem_comentarios(LOTE)
        self.assertRegex(corpo, r'cron:\s*"\*/30 \* \* \* \*"')
        self.assertIn("workflow_dispatch:", corpo)
        self.assertIn("python scripts/promover.py --lote", corpo)
        self.assertIn("agent-browser install --with-deps", corpo, "o E2E é parte da prova")
        self.assertIn("${{ secrets.RENDER_API_KEY }}", corpo)
        self.assertIn("set -o pipefail", corpo)
        self.assertRegex(corpo, r"concurrency:\s*\n\s*group: promover-producao", "lote e botão nunca ao mesmo tempo")

    def test_o_botao_continua_sendo_a_excecao_nomeada(self):
        corpo = sem_comentarios(BOTAO)
        self.assertRegex(corpo, r"inputs:\s*\n\s*sha:")
        self.assertNotIn("schedule:", corpo)
        self.assertIn("set -o pipefail", corpo)
        self.assertIn("EXCEÇÃO", BOTAO)


class ORegraEstaEscritaTests(SimpleTestCase):
    def test_o_claude_md_diz_a_regra_com_os_numeros(self):
        texto = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
        i = texto.index("A REGRA DA PROMOÇÃO")
        trecho = texto[i:i + 2500]
        for pedaco in ("promover-lote", "uma vez por hora", "E2E", "smoke", "ADIADO", "--forcar-janela"):
            self.assertIn(pedaco, trecho, pedaco)
