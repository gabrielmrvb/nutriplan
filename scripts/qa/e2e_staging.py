# -*- coding: utf-8 -*-
"""O E2E NOTURNO (21/09/2026): uma pessoa de verdade, do cadastro à exclusão,
no STAGING, com o `agent-browser` — o mesmo Chromium headless do QA local.

    E2E_BASE=https://nutriplan-staging.onrender.com python scripts/qa/e2e_staging.py --capturas capturas/

O que ele faz, na ordem (`PASSOS` é a lista que o teste lê):

    cadastro → onboarding 1 (sobre você) → 2 (objetivo e rotina) → 3 (personalização,
    "Calcular minha estimativa") → água (+250 ml) → refeição registrada → treino com UMA série
    concluída → tema claro (as mesmas telas em `prefers-color-scheme: light`) →
    movimento reduzido (com `prefers-reduced-motion` emulado, `getAnimations()`
    não vê nada acima de 50 ms) → excluir a conta pela tela → login recusado

Cada passo tira uma captura (`NN-passo.png`, mobile 390×844); o tema escuro é
o padrão do app (Ferro) e o claro é emulado com `set media light`. A conta é
DESCARTÁVEL — `qa-e2e-<run>-<data>@nutriplan.invalid`, senha gerada aqui e
nunca impressa — e é apagada pela própria tela no fim, inclusive quando um
passo falha (`finally`), porque conta de QA esquecida é o que a política do
CLAUDE.md proíbe. Só roda contra um endereço que se anuncia como staging
(`/saude/` com `"ambiente": "staging"`): produção nunca recebe conta de robô.

Falhou um passo: captura `erro-<passo>.png`, o `snapshot` da tela em texto,
e sai com 1 — o fluxo do Actions anexa a pasta e abre a issue.
"""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date
from json import dumps as json_dumps
from pathlib import Path

#: "alimentacao" entrou em 22/09/2026, entre a água e a refeição: a Hoje
#: virou o orquestrador do dia (o cartão AGORA, o painel de cartões e a
#: ofensiva) e o cardápio ganhou tela própria. Marcar refeição é um passo da
#: tela de Alimentação agora, e chegar lá pela ABA é parte do que este E2E
#: prova — o caminho, não só o efeito.
PASSOS = (
    "cadastro", "onboarding-1", "onboarding-2", "onboarding-3", "home",
    "agua", "alimentacao", "refeicao", "serie", "tema-claro",
    "movimento-reduzido", "excluir", "login-recusado",
)
DOMINIO_DE_QA = "nutriplan.invalid"
VIEWPORT = (390, 844)


def email_de_qa(run_id: str, hoje: date) -> str:
    return "qa-e2e-%s-%s@%s" % (run_id, hoje.strftime("%Y%m%d"), DOMINIO_DE_QA)


def senha_de_qa() -> str:
    return "Qa1!" + secrets.token_urlsafe(16)


def ambiente_de(base: str) -> str:
    with urllib.request.urlopen(base + "/saude/", timeout=90) as resposta:
        return json.loads(resposta.read()).get("ambiente", "")


def _binario(nome: str) -> str:
    """O executável do agent-browser. No Windows o npm instala um `.cmd` que
    passa os argumentos pelo cmd.exe — e o cmd.exe come `||`, `&&` e aspas do
    JavaScript de um `eval` (MEDIDO: "'{}).textContent' não é reconhecido como
    um comando"). O shim só chama o `.exe` ao lado; chamamos o `.exe` direto."""
    caminho = shutil.which(nome) or nome
    if caminho.lower().endswith(".cmd"):
        exe = Path(caminho).parent / "node_modules" / "agent-browser" / "bin" / "agent-browser-win32-x64.exe"
        if exe.exists():
            return str(exe)
    return caminho


class Navegador:
    """Fina camada sobre o CLI: `ab("click", "@e1")` → `agent-browser --session X click @e1`."""

    def __init__(self, sessao: str, executar=None):
        self.sessao = sessao
        self.executar = executar or self._executar

    @staticmethod
    def _executar(comando, timeout):
        # `shutil.which`: no Windows o npm instala `agent-browser.cmd`, que o
        # subprocess sem shell não resolve sozinho.
        comando = [_binario(comando[0]), *comando[1:]]
        # Saída em ARQUIVO e stdin fechado, nunca pipe: o primeiro comando sobe
        # o daemon do agent-browser, que herda os descritores — e um pipe
        # espera um EOF que o daemon nunca manda (CLAUDE.md, "Limites reais").
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as saida, \
                tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as erro:
            r = subprocess.run(comando, stdin=subprocess.DEVNULL, stdout=saida, stderr=erro, timeout=timeout)
            saida.seek(0)
            erro.seek(0)
            texto, texto_erro = saida.read(), erro.read()
        if r.returncode != 0:
            raise RuntimeError("%s -> %s\n%s" % (" ".join(comando[3:5]), r.returncode, (texto_erro or texto)[-800:]))
        return texto.strip()

    def __call__(self, *args, timeout=120):
        return self.executar(["agent-browser", "--session", self.sessao, *map(str, args)], timeout)

    def eval(self, js, timeout=60):
        return self("eval", js, timeout=timeout)

    def marcar(self, seletor):
        """`check`, com o plano B do rádio escondido (a divisão só aparece com N dias).

        `wait` antes: no runner (MEDIDO no primeiro run do Actions) o `check`
        chegava com a tela ainda carregando e o plano B achava `null`."""
        try:
            self("wait", seletor, "--timeout", "30000")
            self("check", seletor)
        except RuntimeError:
            self.eval("(function(){var e=document.querySelector(%s);e.checked=true;e.dispatchEvent(new Event('change',{bubbles:true}));return e.checked})()" % json.dumps(seletor))

    def preencher(self, seletor, valor):
        """`fill`, conferido — o `<input type=date>` não aceita `fill` (MEDIDO:
        ficou "dd/mm/aaaa"); quando o valor não pegou, entra pelo DOM."""
        try:
            self("wait", seletor, "--timeout", "30000")
            self("fill", seletor, valor)
        except RuntimeError:
            pass
        js = "(function(){var e=document.querySelector(%s);if(e.value!==%s){e.value=%s;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}return e.value===%s})()" % (
            json.dumps(seletor), json.dumps(valor), json.dumps(valor), json.dumps(valor))
        if self.eval(js).strip() != "true":
            raise RuntimeError("não consegui preencher %s" % seletor)

    def esperar_url(self, padrao, ms=90000):
        self("wait", "--url", padrao, "--timeout", str(ms), timeout=ms // 1000 + 30)

    def esperar_js(self, js, segundos=30, rotulo=""):
        fim = time.time() + segundos
        ultimo = ""
        while time.time() < fim:
            ultimo = self.eval(js)
            if ultimo.strip().strip('"') in ("true", "True"):
                return
            time.sleep(1)
        raise RuntimeError("esperando %s: %r" % (rotulo or js, ultimo))


class E2E:
    def __init__(self, base, capturas: Path, run_id: str, ab: Navegador = None):
        self.base = base.rstrip("/")
        self.capturas = capturas
        self.email = email_de_qa(run_id, date.today())
        self.senha = senha_de_qa()
        self.ab = ab or Navegador("e2e-%s" % run_id)
        self.feitos = []

    # ----------------------------------------------------------- utilidades
    def captura(self, nome):
        self.capturas.mkdir(parents=True, exist_ok=True)
        self.ab("screenshot", str(self.capturas / ("%02d-%s.png" % (len(self.feitos) + 1, nome))))

    FORM = "main form:not([action]), main form[action='']"

    def enviar(self, fica=False):
        """Clica no botão de enviar do formulário principal e confere que a
        página SAIU dele. No runner (terceiro run do Actions) o clique deixou o
        formulário parado com os valores intactos e sem erro na tela; quando
        isso acontece, o diagnóstico vai para o arquivo de erro e o envio é
        repetido por `requestSubmit()` — que ainda passa pela validação do
        navegador, então um formulário inválido continua parado e é achado."""
        self.ab("click", self.FORM.replace(", ", " button[type=submit], ") + " button[type=submit]")
        if fica:  # o login recusado FICA na mesma tela, e é isso que se quer
            return
        antes = self.ab.eval("location.pathname").strip()
        try:
            self.ab.esperar_js("location.pathname !== %s" % json_dumps(antes), segundos=12, rotulo="sair de " + antes)
        except RuntimeError:
            self.diagnostico_do_formulario = self.ab.eval(
                "(function(){var f=document.querySelector(%s);if(!f)return 'sem form';var ruins=[].slice.call(f.elements)"
                ".filter(function(e){return e.willValidate&&!e.checkValidity()}).map(function(e){return e.name+': '+e.validationMessage});"
                "return JSON.stringify({valido:f.checkValidity(),ruins:ruins,action:f.getAttribute('action'),method:f.method,"
                "botao:(f.querySelector('button[type=submit]')||{}).outerHTML})})()" % json_dumps(self.FORM))
            self.ab.eval("document.querySelector(%s).requestSubmit()" % json_dumps(self.FORM))

    def acionar(self, seletor, condicao, rotulo, segundos=45):
        """Clica num botão de ação e espera a condição; se ela não vem em 20 s,
        clica DE NOVO uma vez. Seguro por construção: água, refeição e série
        são idempotentes (op_id / update_or_create), e o segundo toque com o
        mesmo op_id é recusado como repetição pelo servidor. No runner (quarto
        run do Actions) o primeiro clique no "+250" não submeteu — na máquina,
        em dez execuções, nunca deixou de submeter."""
        self.ab("click", seletor)
        try:
            self.ab.esperar_js(condicao, segundos=20, rotulo=rotulo)
        except RuntimeError:
            print("     (clique repetido em %s)" % seletor, flush=True)
            self.ab("click", seletor)
            self.ab.esperar_js(condicao, segundos=segundos, rotulo=rotulo)

    # ----------------------------------------------------------- passos
    def cadastro(self):
        self.ab("open", "about:blank")
        self.ab("set", "viewport", *VIEWPORT)
        self.ab("set", "media", "dark")
        self.ab("open", self.base + "/conta/cadastro/", timeout=180)
        self.ab("fill", "input[name=first_name]", "QA E2E")
        self.ab("fill", "input[name=email]", self.email)
        self.ab("fill", "input[name=password1]", self.senha)
        self.ab("fill", "input[name=password2]", self.senha)
        self.ab.marcar("input[name=termos]")  # o aceite dos Termos e da Política (21/09/2026)
        self.captura("cadastro")
        self.enviar()
        self.ab.esperar_url("**/conta/onboarding/1/")

    def onboarding_1(self):
        self.ab.marcar("input[name=sex][value=M]")
        self.ab.preencher("input[name=birth_date]", "1999-01-15")
        self.ab.preencher("input[name=height_cm]", "180")
        self.ab.preencher("input[name=weight_kg]", "82")
        # As duas caixas de consentimento (dados de saúde, transferência
        # internacional) moram aqui desde 21/09/2026; a dos Termos só aparece
        # para quem veio pelo Google — o cadastro por e-mail já a pediu.
        self.ab.marcar("input[name=saude]")
        self.ab.marcar("input[name=transferencia]")
        self.captura("onboarding-1")
        self.enviar()
        self.ab.esperar_url("**/conta/onboarding/2/")

    def onboarding_2(self):
        # "Você faz musculação?" veio antes do bloco da academia (22/09/2026).
        for nome, valor in (("goal", "cut"), ("activity_level", "light"), ("musculacao", "sim"), ("experiencia", "intermediario"), ("equipamento", "completa")):
            self.ab.marcar("input[name=%s][value=%s]" % (nome, valor))
        for dia in range(7):  # todo dia é dia de treino: o E2E roda em qualquer dia da semana
            self.ab.marcar("input[name=weekdays][value='%d']" % dia)
        self.ab("wait", "500")
        self.ab.marcar("input[name=split_preference][value=three]")
        self.captura("onboarding-2")
        self.enviar()
        self.ab.esperar_url("**/conta/onboarding/3/")

    def onboarding_3(self):
        self.ab.marcar("input[name=meal_style][value=quick]")
        self.ab.marcar("input[name=interesses][value=treino]")
        self.ab.marcar("input[name=interesses][value=hidratacao]")
        self.ab.marcar("input[name=prioridade][value=treino]")
        self.captura("onboarding-3")
        self.enviar()  # "Calcular minha estimativa": monta os dois planos e navega para a Home
        # `wait --url <raiz>` casa por PREFIXO e voltava na hora, ainda na etapa 3
        # (MEDIDO no segundo run do Actions); a raiz é conferida pelo pathname,
        # com o tempo que montar os dois planos leva num staging frio.
        self.ab.esperar_js("location.pathname === '/'", segundos=180, rotulo="a Home depois de calcular a estimativa")

    def home(self):
        """A Hoje é o PAINEL DO DIA desde 22/09/2026.

        Ela tinha o cardápio (`.meal`) e o cartão de água; hoje tem o cartão
        AGORA e a grade de cartões, com a água como uma das células. O
        cardápio foi para `/alimentacao/`, e é lá que o passo `alimentacao`
        o cobra.
        """
        self.ab.esperar_js("[document.querySelector('.agua'), document.querySelector('.painel__cartao')].every(function(e){return e!==null})", segundos=90, rotulo="Home com o painel do dia e a água")
        # O convite de instalação (PWA) cobre o rodapé da tela nova; "Agora não"
        # o dispensa — é o que uma pessoa faz, e as capturas ficam limpas.
        self.ab.eval("(function(){var b=[].slice.call(document.querySelectorAll('button')).filter(function(x){return /Agora n/.test(x.textContent)})[0];if(b){b.click();return true}return false})()")
        self.captura("home")

    def agua(self):
        # `[data-agua-total]` e não `.agua__valor`: o cabeçalho do cartão
        # antigo saiu com o redesenho de 22/09/2026 (na célula do painel o
        # número é `.painel__valor`), e o atributo de dados é o mesmo que o
        # `pwa.js` e a fila offline já usavam — contrato, não classe.
        self.acionar(".agua__botao", "(function(){var e=document.querySelector('[data-agua-total]');return e?/250/.test(e.textContent):false})()", "250 ml registrados")
        self.captura("agua")

    def alimentacao(self):
        """A tela do cardápio, alcançada pela ABA — que é o caminho de quem usa.

        A barra tem cinco itens desde 22/09/2026, e o segundo é Alimentação. A
        aba e a tela têm de concordar: até aqui ela dizia "Alimentação" e
        abria uma página chamada "Hoje".
        """
        self.ir("a.tabbar__item[href='/alimentacao/']", "/alimentacao/")
        self.ab.esperar_js("document.querySelector('.meal') !== null", segundos=60, rotulo="o cardápio na tela de Alimentação")
        self.captura("alimentacao")

    def refeicao(self):
        self.ab.eval("(function(){var m=document.querySelector('.meal:not(.meal--done)');m.querySelectorAll('details').forEach(function(d){d.open=true});return !!m})()")
        self.ab("wait", "300")
        self.acionar(".meal:not(.meal--done) form.option-par__acao button[type=submit]", "document.querySelector('.meal--done') !== null", "refeição marcada")
        self.captura("refeicao")

    def ir(self, seletor, trecho, segundos=45):
        """Clica num link e espera a URL trazer `trecho`; se o clique não navegou
        (MEDIDO: o CTA "Começar pelo primeiro" da ficha nova ficou parado atrás
        do convite de instalação), navega pelo próprio href."""
        self.ab("click", seletor)
        try:
            self.ab.esperar_js("location.pathname.indexOf(%s)!==-1" % json.dumps(trecho), segundos=15, rotulo=trecho)
        except RuntimeError:
            href = self.ab.eval("document.querySelector(%s).getAttribute('href')" % json.dumps(seletor)).strip().strip('"')
            self.ab("open", self.base + href.replace("&amp;", "&"))
            self.ab.esperar_js("location.pathname.indexOf(%s)!==-1" % json.dumps(trecho), segundos=segundos, rotulo=trecho)

    def serie(self):
        self.ab("open", self.base + "/treino/")
        self.ir("a[href^='/treino/ficha/']", "/treino/ficha/")
        self.ir("a[href^='/treino/agora/']", "/treino/agora/")
        self.ab.preencher("input[name=weight_kg]", "40")
        self.ab.preencher("input[name=reps]", "10")
        self.acionar(".agora__concluir", "(function(){var e=document.querySelector('.series__titulo .num');return e?e.textContent.trim()==='2':false})()", "série 2 na tela")
        self.captura("serie")

    def tema_claro(self):
        self.ab("set", "media", "light")
        # A Alimentação entra na varredura do tema claro: ela é uma tela nova
        # (22/09/2026) e a mais longa do app depois do Progresso.
        for rota, nome in (("/", "home"), ("/alimentacao/", "alimentacao"),
                           ("/treino/", "treino"), ("/treino/agora/", "agora")):
            self.ab("open", self.base + rota)
            self.ab("wait", "500")
            self.captura("claro-" + nome)

    def movimento_reduzido(self):
        """Com `prefers-reduced-motion: reduce` emulado, nenhuma animação de
        verdade roda: `document.getAnimations()` só vê durações de ~0 ms."""
        self.ab("set", "media", "light", "reduced-motion")
        self.ab.esperar_js("matchMedia('(prefers-reduced-motion: reduce)').matches", rotulo="emulação de movimento reduzido")
        for rota, nome in (("/", "home"), ("/treino/agora/", "agora")):
            self.ab("open", self.base + rota)
            self.ab("wait", "800")
            lentas = self.ab.eval("document.getAnimations().filter(function(a){return a.effect.getTiming().duration>50}).length").strip()
            if lentas != "0":
                raise RuntimeError("%s: %s animações com mais de 50 ms sob prefers-reduced-motion" % (rota, lentas))
            self.captura("reduzido-" + nome)
        self.ab("set", "media", "dark")

    def excluir(self):
        self.ab("open", self.base + "/conta/excluir/")
        self.ab("fill", "input[name=senha]", self.senha)
        self.captura("excluir")
        self.enviar()
        self.ab("wait", "1500")

    def login_recusado(self):
        self.ab("open", self.base + "/conta/entrar/")
        self.ab("fill", "input[name=login], input[name=username], input[name=email]", self.email)
        self.ab("fill", "input[name=password]", self.senha)
        self.enviar(fica=True)
        self.ab("wait", "1500")
        url = self.ab("get", "url")
        if "/conta/entrar/" not in url:
            raise RuntimeError("a conta apagada ainda entra: %s" % url)
        self.captura("login-recusado")

    # ----------------------------------------------------------- laço
    def rodar(self):
        codigo = 0
        try:
            for passo in PASSOS:
                inicio = time.time()
                getattr(self, passo.replace("-", "_"))()
                self.feitos.append(passo)
                print("ok   %-16s %5.1fs" % (passo, time.time() - inicio), flush=True)
        except Exception as erro:
            passo = PASSOS[len(self.feitos)]
            print("FALHOU %-14s %s" % (passo, str(erro)[:600]), flush=True)
            self._registrar_erro(passo)
            codigo = 1
            if "excluir" not in self.feitos:
                self._apagar_a_conta_mesmo_assim()
        finally:
            try:
                self.ab("close")
            except Exception:
                pass
        print("conta de QA:", self.email, "| passos:", len(self.feitos), "de", len(PASSOS))
        return codigo

    def _registrar_erro(self, passo):
        try:
            self.capturas.mkdir(parents=True, exist_ok=True)
            self.ab("screenshot", str(self.capturas / ("erro-%s.png" % passo)))
            diagnostico = getattr(self, "diagnostico_do_formulario", "")
            (self.capturas / ("erro-%s.txt" % passo)).write_text(
                "url: %s\nformulario: %s\n\n%s" % (self.ab("get", "url"), diagnostico, self.ab("snapshot")), encoding="utf-8")
        except Exception as erro:
            print("(sem captura do erro: %s)" % str(erro)[:200])

    def _apagar_a_conta_mesmo_assim(self):
        """Conta de QA nunca fica para trás — nem quando o passo que falhou foi antes da exclusão."""
        try:
            self.excluir()
            self.login_recusado()
            print("conta de QA apagada depois da falha (login recusado)", flush=True)
        except Exception as erro:
            print("ATENÇÃO: não consegui apagar a conta de QA %s: %s" % (self.email, str(erro)[:300]), flush=True)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):  # o Windows imprime em cp1252 e o agent-browser responde com ✗
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default=os.environ.get("E2E_BASE", "https://nutriplan-staging.onrender.com"))
    parser.add_argument("--capturas", default="capturas")
    parser.add_argument("--run", default=os.environ.get("GITHUB_RUN_ID") or secrets.token_hex(3))
    args = parser.parse_args(argv)
    ambiente = ambiente_de(args.base)
    if ambiente != "staging":
        raise SystemExit("%s responde ambiente=%r — o E2E só cria conta em staging." % (args.base, ambiente))
    return E2E(args.base, Path(args.capturas), args.run).rodar()


if __name__ == "__main__":
    sys.exit(main())
