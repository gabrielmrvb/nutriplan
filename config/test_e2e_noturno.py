# -*- coding: utf-8 -*-
"""O E2E noturno no staging (21/09/2026): o fluxo do Actions e o roteiro.

Sem navegador aqui — o `agent-browser` é trocado por um fake que grava os
comandos. O que se prende:

* o roteiro tem os passos da missão, na ordem: cadastro → onboarding (3) →
  água → refeição → série → tema claro → excluir → login recusado;
* a conta é descartável (`qa-e2e-<run>-<data>@nutriplan.invalid`), a senha é
  gerada e NUNCA impressa, e o roteiro só aceita um alvo que se anuncie
  como staging;
* falhou um passo, a conta é apagada mesmo assim e o processo sai com 1;
* os dois temas passam pelo `set media`, e há captura por passo;
* o fluxo roda toda noite e pelo botão, contra o staging e só ele, anexa as
  capturas sempre (`if: always()`) e abre issue quando falha.
"""
import io
import re
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from scripts.qa import e2e_staging as e2e

RAIZ = Path(__file__).resolve().parents[1]
FLUXO = (RAIZ / ".github" / "workflows" / "e2e-noturno.yml").read_text(encoding="utf-8")
ROTEIRO = (RAIZ / "scripts" / "qa" / "e2e_staging.py").read_text(encoding="utf-8")


def sem_comentarios(texto):
    return "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))


class NavegadorFalso(e2e.Navegador):
    """Grava cada comando; responde o que o roteiro espera para seguir."""

    def __init__(self, falhar_em=None):
        super().__init__("teste", executar=self._fake)
        self.comandos = []
        self.falhar_em = falhar_em

    def _fake(self, comando, timeout):
        args = comando[3:]
        self.comandos.append(args)
        if self.falhar_em and self.falhar_em in " ".join(args):
            raise RuntimeError("falha simulada em " + self.falhar_em)
        if args[0] == "eval":
            return "0" if "getAnimations" in args[1] else "true"
        if args[0] == "get" and args[1] == "url":
            return "https://staging.exemplo/conta/entrar/"
        if args[0] == "snapshot":
            return "- tela"
        return ""


class ORoteiroTests(SimpleTestCase):
    def _rodar(self, falhar_em=None):
        ab = NavegadorFalso(falhar_em)
        capturas = Path(mock.MagicMock().__str__()) if False else Path(RAIZ / "artifacts" / "_capturas_teste")
        cenario = e2e.E2E("https://staging.exemplo", capturas, "run1", ab=ab)
        saida = io.StringIO()
        with mock.patch.object(Path, "mkdir"), redirect_stdout(saida):
            codigo = cenario.rodar()
        return cenario, ab, saida.getvalue(), codigo

    def test_os_passos_da_missao_na_ordem(self):
        """TREZE passos desde 22/09/2026: `alimentacao` entrou entre a água e
        a refeição, porque a tela Hoje virou duas — o painel do dia e o
        cardápio — e marcar refeição deixou de acontecer na raiz."""
        self.assertEqual(e2e.PASSOS, ("cadastro", "onboarding-1", "onboarding-2", "onboarding-3", "home",
                                      "agua", "alimentacao", "refeicao", "serie", "tema-claro",
                                      "movimento-reduzido", "excluir", "login-recusado"))
        for passo in e2e.PASSOS:
            self.assertTrue(callable(getattr(e2e.E2E, passo.replace("-", "_"))), passo)

    def test_roda_tudo_e_a_senha_nunca_sai_no_stdout(self):
        cenario, ab, saida, codigo = self._rodar()
        self.assertEqual(codigo, 0)
        self.assertEqual(cenario.feitos, list(e2e.PASSOS))
        self.assertNotIn(cenario.senha, saida)
        self.assertIn(cenario.email, saida, "o e-mail da conta de QA é dito, para o relatório")
        self.assertEqual(ab.comandos[-1], ["close"])

    def test_a_conta_e_descartavel_e_a_senha_e_forte(self):
        self.assertEqual(e2e.email_de_qa("77", date(2026, 9, 21)), "qa-e2e-77-20260921@nutriplan.invalid")
        senha = e2e.senha_de_qa()
        self.assertGreaterEqual(len(senha), 16)
        self.assertNotEqual(senha, e2e.senha_de_qa())

    def test_os_dois_temas_e_uma_captura_por_passo(self):
        cenario, ab, saida, codigo = self._rodar()
        medias = [c[2:] for c in ab.comandos if c[:2] == ["set", "media"]]
        self.assertEqual(medias, [["dark"], ["light"], ["light", "reduced-motion"], ["dark"]])
        self.assertTrue(any("reduzido-home" in c[1] for c in ab.comandos if c[0] == "screenshot"))
        capturas = [c[1] for c in ab.comandos if c[0] == "screenshot"]
        self.assertGreaterEqual(len(capturas), len(e2e.PASSOS))
        self.assertTrue(any("claro-home" in c for c in capturas))
        self.assertTrue(any("login-recusado" in c for c in capturas))

    def test_falhou_no_meio_apaga_a_conta_mesmo_assim_e_sai_com_1(self):
        cenario, ab, saida, codigo = self._rodar(falhar_em=".agora__concluir")
        self.assertEqual(codigo, 1)
        self.assertEqual(cenario.feitos[-1], "refeicao")
        self.assertIn("FALHOU serie", saida)
        aberturas = [c[1] for c in ab.comandos if c[0] == "open"]
        self.assertIn("https://staging.exemplo/conta/excluir/", aberturas, "a exclusão roda mesmo depois da falha")
        self.assertIn("conta de QA apagada depois da falha", saida)
        self.assertTrue(any(c[0] == "screenshot" and "erro-serie" in c[1] for c in ab.comandos))

    def test_conta_apagada_que_ainda_entra_e_falha(self):
        ab = NavegadorFalso()
        ab._fake = lambda comando, timeout: ("https://staging.exemplo/" if comando[3:5] == ["get", "url"] else ("true" if comando[3] == "eval" else ""))
        ab.executar = ab._fake
        cenario = e2e.E2E("https://staging.exemplo", RAIZ / "artifacts" / "_capturas_teste", "run2", ab=ab)
        with mock.patch.object(Path, "mkdir"):
            with self.assertRaisesMessage(RuntimeError, "ainda entra"):
                cenario.login_recusado()

    def test_so_roda_contra_staging(self):
        with mock.patch.object(e2e, "ambiente_de", lambda base: ""):
            with self.assertRaisesMessage(SystemExit, "só cria conta em staging"):
                e2e.main(["--base", "https://nutriplan-xxfn.onrender.com"])
        self.assertNotIn("nutriplan-xxfn", ROTEIRO, "o endereço de produção não aparece no roteiro")

    def test_marcar_confere_e_forca_quando_o_check_mente(self):
        """O `promover-lote` das 12:27 e das 17:26 de 24/09/2026 reprovou em
        `onboarding-1` com a SEGUNDA caixa de consentimento desmarcada — o
        snapshot do erro mostra `checked=false` e "Para continuar, marque
        esta caixa" —, e o mesmo roteiro passara 13/13 três horas antes
        contra o MESMO commit do staging. A causa não é o app: `check` do
        agent-browser sai com código 0 mesmo quando a caixa não ficou
        marcada, e as duas caixas moram DENTRO de um `<label>` clicável,
        onde um clique no rótulo pode desfazer o do input.

        Guarda que não confere não é guarda. `marcar` passou a LER o estado
        e a forçar pelo DOM quando ele não é o pedido — e a falhar alto se
        nem assim ficar, que é o que impede a próxima versão de mentir em
        silêncio."""
        estado = {"marcado": False}

        def falso(comando, timeout):
            args = comando[3:]
            if args[0] == "check":          # o `check` que sai 0 sem marcar
                return ""
            if args[0] == "eval":
                if "e.checked = true" in args[1]:
                    estado["marcado"] = True
                    return "true"
                return "true" if estado["marcado"] else "false"
            return ""

        gravados = []
        ab = e2e.Navegador("s", executar=lambda c, t: gravados.append(c[3:]) or falso(c, t))
        ab.marcar("input[name=transferencia]")
        self.assertTrue(estado["marcado"], "a caixa tinha de acabar marcada")
        evals = [c[1] for c in gravados if c[0] == "eval"]
        self.assertTrue(any("e.checked = true" in js for js in evals),
                        "sem a força pelo DOM o roteiro segue com a caixa vazia")

    def test_marcar_falha_alto_quando_nem_o_dom_marca(self):
        """Controle positivo: caixa que não marca de jeito nenhum precisa
        PARAR o roteiro ali, com o nome do seletor — não seguir e reprovar
        três passos depois, onde o diagnóstico já não diz o que houve."""
        ab = e2e.Navegador("s", executar=lambda c, t: "false" if c[3] == "eval" else "")
        with self.assertRaisesMessage(RuntimeError, "input[name=transferencia]"):
            ab.marcar("input[name=transferencia]")

    def test_ir_espera_o_link_aparecer_antes_de_clicar(self):
        """O lote das 15:22 de 24/09/2026 reprovou em `serie` com "Element not
        found: a[href^='/treino/agora/']" — o clique na ficha chegou antes de
        a tela existir. `ir` clicava direto; `marcar` já esperava desde o
        primeiro run do Actions, e a razão é a mesma: o runner é mais lento
        que esta máquina, e o app anima a troca de página (durante a view
        transition o `elementFromPoint` devolve `<html>` por ~300 ms, medido
        no Chrome 153 e escrito no `CLAUDE.md`).

        Reproduzido ao contrário: o caminho painel → primeira ficha → execução
        está ÍNTEGRO com o perfil que o roteiro cria (sete dias, ABC) —
        `scratchpad/repro_e2e_serie.py` devolve o link da execução na ficha.
        Não é o app; é o roteiro clicando cedo demais."""
        gravados = []
        ab = e2e.Navegador("s", executar=lambda c, t: gravados.append(c[3:]) or (
            "https://staging.exemplo/treino/ficha/1/" if c[3:5] == ["get", "url"] else "true"))
        cenario = e2e.E2E("https://staging.exemplo", RAIZ / "artifacts" / "_capturas_teste", "r", ab=ab)
        cenario.ir("a[href^='/treino/agora/']", "/treino/agora/")
        ordem = [c[0] for c in gravados]
        self.assertLess(ordem.index("wait"), ordem.index("click"),
                        "o clique não pode chegar antes de o elemento existir")
        self.assertEqual(gravados[ordem.index("wait")][1], "a[href^='/treino/agora/']")

    def test_o_agent_browser_recebe_a_sessao_em_todo_comando(self):
        gravados = []
        ab = e2e.Navegador("sessao-x", executar=lambda comando, timeout: gravados.append(comando) or "")
        ab("click", "@e1")
        self.assertEqual(gravados[0], ["agent-browser", "--session", "sessao-x", "click", "@e1"])


class OFluxoNoturnoTests(SimpleTestCase):
    def test_toda_noite_e_pelo_botao(self):
        corpo = sem_comentarios(FLUXO)
        self.assertRegex(corpo, r'cron:\s*"30 7 \* \* \*"')
        self.assertIn("workflow_dispatch:", corpo)

    def test_contra_o_staging_e_so_ele(self):
        corpo = sem_comentarios(FLUXO)
        self.assertIn("E2E_BASE: https://nutriplan-staging.onrender.com", corpo)
        self.assertNotIn("nutriplan-xxfn", corpo)

    def test_usa_o_agent_browser_e_o_roteiro(self):
        corpo = sem_comentarios(FLUXO)
        self.assertRegex(corpo, r"npm install -g agent-browser@\d+\.\d+\.\d+")
        self.assertIn("agent-browser install --with-deps", corpo)
        self.assertIn("python scripts/qa/e2e_staging.py --capturas capturas", corpo)

    def test_as_capturas_sobem_sempre_e_a_falha_abre_issue(self):
        corpo = sem_comentarios(FLUXO)
        artefato = corpo.index("upload-artifact")
        self.assertIn("if: always()", corpo[artefato - 200:artefato])
        self.assertIn("path: capturas/", corpo)
        self.assertIn("if: failure()", corpo)
        self.assertRegex(corpo, r"issues:\s*write")
        self.assertIn("gh issue create", corpo)

    def test_acorda_o_staging_antes(self):
        self.assertIn("/saude/vivo/", sem_comentarios(FLUXO))
