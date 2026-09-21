# -*- coding: utf-8 -*-
"""Staging e promoção (21/09/2026): o segundo serviço no Render recebe todo
merge em `main` sozinho; produção só muda por PROMOÇÃO explícita.

O que este arquivo prende:

* `NUTRIPLAN_AMBIENTE=staging` marca a instância: cabeçalho `X-Robots-Tag`
  (buscador não indexa um app de teste com o mesmo nome do de verdade),
  `<meta name="robots" content="noindex">`, uma faixa visível em toda tela e
  `"ambiente"` no `/saude/`. Sem a variável nada disso existe — produção não
  muda um byte por causa do staging.
* `render.yaml` declara os DOIS serviços, e produção com `autoDeploy: false`:
  o que está no arquivo é a verdade do que existe no painel.
* `.github/workflows/promover.yml` é a promoção manual (`workflow_dispatch`,
  um SHA), com a chave do Render vinda de `secrets` — nunca do repositório.
* o helper da fila prova o staging depois do merge e nunca promove sozinho
  sem ser pedido (`--promover`); `scripts/github.py promover <sha>` existe.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

RAIZ = Path(__file__).resolve().parent.parent


class AInstanciaDeStagingSeAnunciaTests(TestCase):
    @override_settings(NUTRIPLAN_AMBIENTE="staging")
    def test_staging_nao_e_indexado_e_se_anuncia_em_toda_tela(self):
        resposta = self.client.get("/conta/entrar/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["X-Robots-Tag"], "noindex, nofollow")
        html = resposta.content.decode()
        self.assertIn('<meta name="robots" content="noindex">', html)
        self.assertIn('class="faixa-ambiente"', html)
        self.assertIn("STAGING", html)

    @override_settings(NUTRIPLAN_AMBIENTE="staging")
    def test_a_saude_diz_o_ambiente(self):
        from config.tests import semear

        semear()
        dados = self.client.get("/saude/").json()
        self.assertEqual(dados["ambiente"], "staging")

    @override_settings(NUTRIPLAN_AMBIENTE="")
    def test_producao_nao_muda_um_byte(self):
        resposta = self.client.get("/conta/entrar/")
        self.assertNotIn("X-Robots-Tag", resposta)
        html = resposta.content.decode()
        self.assertNotIn('name="robots"', html)
        self.assertNotIn("faixa-ambiente", html)

    def test_a_variavel_vem_do_ambiente_e_o_padrao_e_vazio(self):
        texto = (RAIZ / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertRegex(texto, r'NUTRIPLAN_AMBIENTE = env\("NUTRIPLAN_AMBIENTE", default=""\)')


class OBlueprintDeclaraOsDoisServicosTests(SimpleTestCase):
    def setUp(self):
        self.yaml = (RAIZ / "render.yaml").read_text(encoding="utf-8")
        self.sem_comentario = "\n".join(l for l in self.yaml.splitlines() if not l.strip().startswith("#"))

    def test_producao_nao_deploya_sozinha(self):
        """Produção só muda por promoção: `autoDeploy: false` no serviço `nutriplan`."""
        bloco = self.sem_comentario.split("name: nutriplan\n", 1)[1].split("- type:", 1)[0]
        self.assertIn("autoDeploy: false", bloco)

    def test_staging_deploya_todo_merge_em_main(self):
        self.assertIn("name: nutriplan-staging", self.sem_comentario)
        bloco = self.sem_comentario.split("name: nutriplan-staging\n", 1)[1]
        self.assertIn("branch: main", bloco)
        self.assertIn("autoDeploy: true", bloco)
        self.assertIn("NUTRIPLAN_AMBIENTE", bloco)
        self.assertIn("value: staging", bloco)


class APromocaoEManualTests(SimpleTestCase):
    def setUp(self):
        self.fluxo = (RAIZ / ".github" / "workflows" / "promover.yml").read_text(encoding="utf-8")
        self.helper = (RAIZ / "scripts" / "github.py").read_text(encoding="utf-8")
        self.promover = (RAIZ / "scripts" / "promover.py").read_text(encoding="utf-8")

    def test_o_fluxo_e_manual_com_um_sha(self):
        self.assertIn("workflow_dispatch:", self.fluxo)
        self.assertRegex(self.fluxo, r"inputs:\s*\n\s*sha:")
        self.assertNotIn("schedule:", self.fluxo)
        self.assertNotIn("push:", self.fluxo.split("workflow_dispatch:")[0])

    def test_a_chave_do_render_vem_de_secrets_e_o_fluxo_so_le_o_repositorio(self):
        self.assertIn("${{ secrets.RENDER_API_KEY }}", self.fluxo)
        self.assertRegex(self.fluxo, r"permissions:\s*\n\s*contents: read")
        self.assertNotRegex(self.fluxo, r"rnd_[A-Za-z0-9]{10,}", "chave do Render escrita no fluxo")

    def test_o_fluxo_chama_o_mesmo_script_que_a_sessao_usa(self):
        self.assertIn("scripts/promover.py", self.fluxo)
        self.assertIn("--esperar", self.fluxo)

    def test_o_script_promove_pelo_commit_e_prova_pelo_saude(self):
        self.assertIn('"commitId"', self.promover)
        self.assertIn("/saude/", self.promover)
        self.assertNotRegex(self.promover, r"rnd_[A-Za-z0-9]{10,}")

    def test_o_helper_prova_o_staging_e_so_promove_se_pedido(self):
        self.assertIn('"promover"', self.helper.split("COMANDOS = ", 1)[1].split("\n", 1)[0])
        self.assertIn("def _provar_staging", self.helper)
        enfileirar = self.helper.split("def cmd_enfileirar", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_provar_staging(", enfileirar)
        self.assertIn('"--promover" in args', enfileirar)
        # Sem a flag, o helper NÃO chama a promoção.
        self.assertRegex(enfileirar, r'if "--promover" in args:\s*\n\s+cmd_promover')


class ACONFIGURACAODOSTAGINGEDOCUMENTADATests(SimpleTestCase):
    def test_o_claude_md_descreve_o_fluxo(self):
        texto = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
        for trecho in ("nutriplan-staging.onrender.com", "promover", "NUTRIPLAN_AMBIENTE", "autoDeploy"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, texto)
