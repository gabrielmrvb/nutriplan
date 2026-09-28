# -*- coding: utf-8 -*-
"""`corrida.js` não pode apagar a corrida ao seguir o redirect do consentimento
(achado 1 da revisão de 28/09/2026, Task F, Parte 2).

`SalvarCorridaView` passou a usar `OnboardingRequiredMixin` (item 11): uma
conta com o consentimento vencido recebe 302 para `/conta/consentimento/`.
`fetch()` SEM `redirect: "manual"` segue esse 302 sozinho e chega numa
resposta 200 (a tela de consentimento) — `salvar()` só olhava `r.ok`, então
lia isso como sucesso, chamava `esquecer()` e apagava a ÚNICA cópia local da
corrida, mesmo o servidor nunca tendo gravado nada. `static/js/fila.js:431`
já evita exatamente isso com `redirect: "manual"` + `veredito()`; `corrida.js`
tem o próprio mecanismo de retomada em `localStorage` e não herdava a guarda
por não passar pela fila.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent


def sem_comentarios(texto):
    """O código sem os comentários — uma asserção que procura um texto que só
    existe dentro de um comentário passaria mesmo com o código sabotado.
    Mesma função de `push.test_cache_privado.sem_comentarios`, copiada aqui
    para este arquivo não depender de outro app só por causa dela."""
    sem_bloco = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"^\s*//.*$", "", sem_bloco, flags=re.M)


def corpo_da_funcao(texto, assinatura):
    """O texto entre as chaves da função, contando profundidade — e não um
    número fixo de caracteres, que quebraria a cada linha acrescentada antes
    do fim da função. Mesmo padrão de `push.test_replay.corpo_da_funcao`."""
    texto = sem_comentarios(texto)
    inicio = texto.index(assinatura)
    profundidade = 0
    for fim in range(inicio, len(texto)):
        if texto[fim] == "{":
            profundidade += 1
        elif texto[fim] == "}":
            profundidade -= 1
            if profundidade == 0:
                return texto[inicio:fim + 1]
    raise AssertionError("chave nao fechada em %r" % assinatura)


class CorridaJsNaoSeguRedirectTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = (RAIZ / "static" / "js" / "corrida.js").read_text(encoding="utf-8")
        cls.salvar = corpo_da_funcao(cls.js, "function salvar(")

    def test_o_envio_nao_segue_redirect_automaticamente(self):
        """A mesma guarda de `fila.js:431`: sem isto, o 302 do consentimento
        vira uma resposta 200 que `r.ok` leria como sucesso."""
        self.assertIn('redirect: "manual"', self.salvar)

    def _bloco_do_redirecionamento(self):
        inicio = self.salvar.index('if (r.type === "opaqueredirect")')
        fim = self.salvar.index("if (r.ok)", inicio)
        return self.salvar[inicio:fim]

    def test_o_redirecionamento_de_consentimento_nao_apaga_a_corrida_local(self):
        bloco = self._bloco_do_redirecionamento()
        self.assertNotIn("esquecer()", bloco)
        self.assertNotIn("location.reload", bloco)

    def test_o_redirecionamento_de_consentimento_devolve_o_botao_de_comecar(self):
        """Sem isto a pessoa ficaria com a tela travada: `encerrar()` esconde
        `comecar` antes de tentar salvar, e só os outros dois desfechos (ok,
        recusa) o devolviam."""
        bloco = self._bloco_do_redirecionamento()
        self.assertIn("el.comecar.hidden = false", bloco)

    def test_o_redirecionamento_de_consentimento_mostra_o_link_e_avisa_em_pt_br(self):
        bloco = self._bloco_do_redirecionamento()
        self.assertIn("el.consentir.hidden = false", bloco)
        self.assertIn("termos", bloco)
        self.assertIn("guardada", bloco)

    def test_o_sucesso_de_verdade_continua_apagando_a_copia_local(self):
        """Controle positivo: a régua nova não pode ter desligado a limpeza
        do caminho feliz — só o redirecionamento de consentimento é
        preservado."""
        inicio = self.salvar.index("if (r.ok)")
        fim = self.salvar.index("}", self.salvar.index("return;", inicio))
        bloco = self.salvar[inicio:fim]
        self.assertIn("esquecer()", bloco)
        self.assertIn("location.reload", bloco)


class LinkDeConsentirNoTemplateTests(SimpleTestCase):
    def setUp(self):
        self.html = (
            RAIZ / "templates" / "workouts" / "corridas.html"
        ).read_text(encoding="utf-8")

    def test_o_link_existe_escondido_e_aponta_para_o_consentimento(self):
        trecho = self.html[self.html.index("data-corrida-consentir") - 200:][:250]
        self.assertIn("hidden", trecho)
        self.assertIn("{% url 'accounts:consentimento' %}", self.html)

    def test_o_link_volta_para_corridas_depois_de_consentir(self):
        """M2 da re-revisão de 28/09/2026: sem `?next=` a pessoa consentia e
        caía na Home, não em Corridas — que é a ÚNICA tela onde `recuperar()`
        reenvia a corrida pendente. Ancorado na tag `<a>` que carrega
        `data-corrida-consentir`, e não numa busca solta no arquivo inteiro:
        o `href` de QUALQUER outro link, ou um trecho dentro de um futuro
        `<script>`, não deve fazer este teste passar por acidente."""
        tag = re.search(r"<a\b[^>]*data-corrida-consentir[^>]*>", self.html)
        self.assertIsNotNone(tag, "a tag <a data-corrida-consentir> não foi encontrada")
        href = re.search(r'href="([^"]*)"', tag.group(0))
        self.assertIsNotNone(href, "a tag não tem href")
        self.assertIn("{% url 'accounts:consentimento' %}", href.group(1))
        self.assertIn("?next={% url 'workouts:corridas' %}", href.group(1))


class ComecarNaoSobrescreveCorridaPendenteTests(SimpleTestCase):
    """M3 da re-revisão de 28/09/2026, mesmo peso do achado crítico original —
    e RESTRITO pela rodada 3 do controlador.

    A primeira versão desta correção recusava `comecar()` sempre que havia
    uma corrida `estado.opId && estado.terminou` pendente, sem olhar POR QUE
    ela ainda não subiu. Isso prendia a pessoa em dois casos que já existiam
    ANTES desta tarefa e não são o achado M3:

    - **4xx** (o servidor recusou o CONTEÚDO — "insistir não conserta"):
      bloquear "Começar" prenderia a pessoa numa corrida que o servidor
      nunca vai aceitar, mesmo depois de recarregar a página (`recuperar()`
      traria o mesmo registro de volta).
    - **Falha de rede/offline**: quem já tinha uma corrida encerrada sem
      subir e quer registrar uma SEGUNDA corrida sem sinal perderia essa
      opção — "Começar" sobrescrever aqui já era o comportamento de antes
      desta PR.

    A régua da rodada 3: só o redirecionamento de CONSENTIMENTO (o achado
    M3 de verdade) bloqueia "Começar" — via uma bandeira própria,
    `estado.pendeConsentimento`, ligada só dentro do ramo `opaqueredirect`
    de `salvar()` e limpa no início de toda tentativa nova. 4xx e a falha de
    rede continuam exatamente como estavam antes desta tarefa — a troca
    deles é decisão pendente do dono, não desta correção.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = (RAIZ / "static" / "js" / "corrida.js").read_text(encoding="utf-8")
        cls.comecar = corpo_da_funcao(cls.js, "function comecar(")
        cls.salvar = corpo_da_funcao(cls.js, "function salvar(")

    def test_comecar_recusa_sobrescrever_quando_pende_consentimento(self):
        guarda = self.comecar.index("if (estado.pendeConsentimento)")
        reset = self.comecar.index("estado.opId = identificador()")
        self.assertLess(
            guarda, reset,
            "a guarda precisa vir ANTES do reset que zera estado.opId/estado.distancia",
        )
        bloco = self.comecar[guarda:reset]
        self.assertIn("salvar()", bloco)
        self.assertIn("return", bloco)

    def test_comecar_ainda_comeca_do_zero_quando_nao_ha_corrida_pendente(self):
        """Controle positivo: a guarda nova não pode ter engolido o reset —
        a primeira corrida do carregamento (`estado.opId` nasce `null`)
        continua chamando `identificador()` e zerando os acumuladores."""
        self.assertIn("estado.opId = identificador()", self.comecar)
        self.assertIn("estado.distancia = 0", self.comecar)

    def test_a_bandeira_e_limpa_no_inicio_de_toda_tentativa(self):
        """Sem isto, uma corrida que já passou pelo redirecionamento de
        consentimento uma vez ficaria bloqueando "Começar" para sempre —
        mesmo depois de um sucesso (que recarrega a página, então não
        importa) ou de uma recusa de conteúdo sem relação com consentimento."""
        antes_do_fetch = self.salvar[:self.salvar.index("fetch(")]
        self.assertIn("estado.pendeConsentimento = false", antes_do_fetch)

    def test_a_bandeira_so_liga_no_redirecionamento_de_consentimento(self):
        """A régua da rodada 3: 4xx e a falha de rede NÃO ligam a bandeira —
        só o `opaqueredirect` liga."""
        inicio_redirect = self.salvar.index('if (r.type === "opaqueredirect")')
        fim_redirect = self.salvar.index("if (r.ok)", inicio_redirect)
        bloco_redirect = self.salvar[inicio_redirect:fim_redirect]
        self.assertIn("estado.pendeConsentimento = true", bloco_redirect)

        inicio_4xx = self.salvar.index("if (r.ok)")
        inicio_catch = self.salvar.index(".catch(function", inicio_4xx)
        bloco_4xx = self.salvar[inicio_4xx:inicio_catch]
        bloco_catch = self.salvar[inicio_catch:]

        self.assertNotIn(
            "estado.pendeConsentimento = true", bloco_4xx,
            "4xx não pode travar Começar — decisão pendente do dono, fora desta correção",
        )
        self.assertNotIn(
            "estado.pendeConsentimento = true", bloco_catch,
            "falha de rede não pode travar Começar — decisão pendente do dono, fora desta correção",
        )
