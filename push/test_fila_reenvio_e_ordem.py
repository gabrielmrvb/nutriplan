# -*- coding: utf-8 -*-
"""O reenvio é o MESMO toque, e o toque online não passa na frente da fila
(04/10/2026; revisão da Task D da Parte 2, achados F6 e N2).

F6. Online, "Concluir série 2". O servidor grava, a resposta se perde e o
aparelho vira `onLine=false`. O `catch` do envio sem recarga (`agora.html`)
refaz com `requestSubmit`, e a fila capturava SORTEANDO um `op_id` novo: na
drenagem gravava uma cópia da série 2 como 3ª, e com o teto do M14 a 4ª de
verdade era recusada calada. O reenvio carrega o `op_id` do formulário; só o
toque novo sorteia.

N2. Wi-Fi da academia oscilando: séries 3 e 4 guardadas offline, a drenagem
falha no item 3 e ele fica, a rede volta sem novo evento `online`. O próximo
toque ia por `fetch` e gravava como 3ª; na drenagem seguinte o item 3 virava
4ª e o item 4 batia no teto — `replay_processado`, fora da fila, série real
perdida. Com item pendente do dono, o toque online entra na fila e ela drena
na hora, em ordem.

Sem Node na suíte (CLAUDE.md): as réguas de cliente são ESTRUTURAIS, como
`push.test_fila_ordem`, e leem o código sem comentários (a armadilha do
seletor que também está no comentário). O comportamento foi medido no
navegador — relatório da tarefa. As réguas de servidor provam o contrato em
que o cliente se apoia: mesmo `op_id` grava uma vez, e a ORDEM decide qual
série o teto recusa.
"""
import re
from decimal import Decimal

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from accounts.replay import CODIGO_OUTRA_SESSAO, CODIGO_SEM_SESSAO
from push.test_cache_privado import sem_comentarios
from push.test_replay import corpo_da_funcao
from workouts import services
from workouts.models import ExerciseLog
from workouts.test_fluxo_do_treino import BaseDoFluxo, pessoa, tornar_hoje

RAIZ = settings.BASE_DIR


def _fila():
    return sem_comentarios((RAIZ / "static" / "js" / "fila.js").read_text(encoding="utf-8"))


def _captura():
    """O ouvinte de `submit` da fila, inteiro."""
    js = _fila()
    inicio = js.index('document.addEventListener("submit"')
    return js[inicio : js.index('window.addEventListener("online"', inicio)]


def _pwa():
    return sem_comentarios((RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8"))


def _sem_recarga():
    """O script do envio sem recarga do `agora.html`: (ouvinte, catch)."""
    html = (RAIZ / "templates" / "workouts" / "agora.html").read_text(encoding="utf-8")
    inicio = html.index("var NONCE_DA_PAGINA")
    js = sem_comentarios(html[inicio : html.index("</script>", inicio)])
    ouvinte = js[js.index('document.addEventListener("submit"') :]
    corte = ouvinte.index("}).catch(function () {")
    return ouvinte[:corte], ouvinte[corte:]


class OReenvioEOMesmoToqueTests(SimpleTestCase):
    """F6: o `catch` reenvia o toque que o servidor talvez já gravou."""

    def test_o_reenvio_leva_o_op_id_do_formulario(self):
        """A marca do `catch` chega à fila, e com ela o `op_id` da página
        substitui o sorteado — o servidor reconhece a série 2 e não a copia."""
        captura = _captura()
        self.assertIn('var reenvio = form.hasAttribute("data-recarga-de-sempre");', captura)
        self.assertIn("var daPagina = reenvio && form.elements.op_id;", captura)
        self.assertIn("if (daPagina && daPagina.value) dados.op_id = daPagina.value;", captura)

    def test_o_toque_novo_continua_sorteando(self):
        """Controle: sem a marca, a identidade é do TOQUE. Offline a página não
        recarrega, e três toques com o `op_id` do HTML colapsariam num só."""
        captura = _captura()
        self.assertIn('if (k === "op_id") return;', captura)
        sorteio = captura.index("dados.op_id = identificador();")
        self.assertLess(sorteio, captura.index("dados.op_id = daPagina.value;"))
        self.assertLess(captura.index("dados.op_id = daPagina.value;"), captura.index('pares.push(["op_id", dados.op_id]);'))

    def test_o_op_id_que_a_fila_levou_sai_da_pagina(self):
        """Guardado o reenvio, o `op_id` da página está gasto: o próximo toque
        online sem fila iria por `fetch` com ele, e o servidor o descartaria
        como repetição — calado. Trocado só DEPOIS de guardar: se guardar
        falhar, o toque de novo ainda é o mesmo."""
        captura = _captura()
        depois = captura[captura.index("guardar({") :]
        sucesso = depois[: depois.index(".catch(function (erro)")]
        self.assertIn("if (daPagina) daPagina.value = identificador();", sucesso)

    def test_a_marca_vale_so_durante_o_evento_e_ninguem_a_apaga_no_meio(self):
        """`agora.html` é inline e `fila.js` é `defer`: o ouvinte do agora roda
        ANTES. Ele apagava a marca, e a fila nunca a via. Agora os dois só
        LEEM; o `catch` marca antes do `requestSubmit` (que dispara o `submit`
        síncrono) e desmarca depois — a ordem dos ouvintes é irrelevante."""
        ouvinte, catch = _sem_recarga()
        self.assertIn('form.hasAttribute("data-recarga-de-sempre")', ouvinte)
        self.assertNotIn('removeAttribute("data-recarga-de-sempre")', ouvinte)
        self.assertNotIn('removeAttribute("data-recarga-de-sempre")', _captura())
        marca = catch.index('form.setAttribute("data-recarga-de-sempre", "1");')
        envio = catch.index("form.requestSubmit(")
        desmarca = catch.index('form.removeAttribute("data-recarga-de-sempre");')
        self.assertLess(marca, envio)
        self.assertLess(envio, desmarca)
        # E num `finally` (INFO 1 da revisão, 04/10/2026): se `requestSubmit`
        # lançar, a marca não vaza para o toque seguinte.
        self.assertLess(envio, catch.index("} finally {"))
        self.assertLess(catch.index("} finally {"), desmarca)


class OToqueOnlineNaoPassaAFilaTests(SimpleTestCase):
    """N2: com item do dono na fila, o toque online entra atrás dele."""

    def test_a_contagem_fica_num_valor_que_o_submit_le_sincrono(self):
        """O `preventDefault` não espera IndexedDB: a decisão de capturar lê o
        número que `recontar()` já calcula."""
        recontar = corpo_da_funcao(_fila(), "function recontar() {")
        self.assertIn("pendentes = (itens || []).length;", recontar)
        self.assertIn("pendentes: function () { return pendentes; },", _fila())

    def test_online_so_sai_da_frente_com_a_fila_vazia(self):
        """A guarda ganhou `semSessao` na rodada 1 (I1, 04/10/2026): ver
        `ARecusaDeIdentidadeDevolveOPostNativoTests`."""
        captura = _captura()
        self.assertIn("if (navigator.onLine && (!pendentes || semSessao)) return;", captura)
        self.assertNotIn("if (navigator.onLine) return;", captura)

    def test_guardado_com_rede_a_fila_drena_na_hora(self):
        """A troca sem recarga não dispara `online` nem `DOMContentLoaded`:
        sem esta chamada, o toque ficaria parado atrás do item 3."""
        captura = _captura()
        depois = captura[captura.index("nutriplan:enfileirado") :]
        # Com `.catch` próprio (INFO 5 da revisão, 04/10/2026): a rejeição de
        # `meus()` não fica sem tratamento no console.
        self.assertIn("drenar().catch(function () {", depois[: depois.index(".catch(function (erro)")])

    def test_o_envio_sem_recarga_sai_da_frente_com_pendente(self):
        """O ouvinte do agora roda antes e faria o `fetch` mesmo com a fila
        capturando: ele lê o MESMO sinal, antes do `preventDefault`."""
        ouvinte, _ = _sem_recarga()
        sinal = ouvinte.index("NutriPlanFila.pendentes()")
        self.assertIn("window.NutriPlanFila && NutriPlanFila.pendentes()", ouvinte)
        self.assertLess(sinal, ouvinte.index("evento.preventDefault();"))

    def test_online_com_fila_a_tela_nao_diz_aguardando_rede(self):
        """Rodada 1 (MINOR 2, 04/10/2026): o ternário saiu da série para
        `mostrarNota`, e vale para água, refeição, série e desfazer."""
        pwa = _pwa()
        nota = corpo_da_funcao(pwa, "function mostrarNota(raiz, texto) {")
        self.assertIn('texto + (navigator.onLine ? "enviando…" : "aguardando rede.")', nota)
        funcao = corpo_da_funcao(pwa, "function serieEnfileirada(form, dados) {")
        self.assertIn('mostrarNota(secao, "Série guardada — ");', funcao)
        self.assertIn('mostrarNota(secao, "Desfazer guardado — ");', funcao)
        self.assertNotIn("aguardando rede.", funcao)


class OServidorEOContratoDaFilaTests(BaseDoFluxo):
    """O que o cliente consertado entrega ao servidor, e o que o defeito
    entregava. Faltando duas séries para a ficha fechar."""

    def setUp(self):
        self.user = pessoa("fila-reenvio@exemplo.com")
        tornar_hoje(self.user, "A")
        self.client.force_login(self.user)
        estado = services.estado_do_treino(self.user)
        self.item = next(i for i in estado.itens if not i.exercise.sem_carga)
        self.exercicio = self.item.exercise
        self.n = self.item.sets
        for numero in range(1, self.n - 1):
            services.record_load(self.user, self.exercicio, Decimal("30"), set_number=numero, reps=10)

    def _toque(self, op_id, peso, replay=True, **extra):
        corpo = {"exercise_id": self.exercicio.pk, "weight_kg": peso, "reps": "8", "op_id": op_id}
        corpo.update(extra)
        cabecalhos = {"HTTP_X_REQUESTED_WITH": "fetch"}
        if replay:
            cabecalhos.update(HTTP_X_NUTRIPLAN_REPLAY="1", HTTP_X_NUTRIPLAN_DONO=str(self.user.pk))
        resposta = self.client.post(reverse("workouts:record_set"), corpo, **cabecalhos)
        self.assertLess(resposta.status_code, 400)
        return resposta

    def _pesos(self):
        return [
            int(p) for p in ExerciseLog.objects.filter(user=self.user, exercise=self.exercicio)
            .order_by("set_number").values_list("weight_kg", flat=True)
        ][self.n - 2 :]

    def test_duas_capturas_do_mesmo_toque_gravam_uma_serie(self):
        """F6 consertado: o `fetch` grava (resposta perdida), a fila reenvia o
        MESMO `op_id`, e a última série real entra no lugar dela."""
        self._toque("da-pagina", "41", replay=False)
        self._toque("da-pagina", "41")
        self._toque("toque-novo", "42")
        self.assertEqual(self._pesos(), [41, 42])

    def test_controle_com_op_id_sorteado_a_copia_toma_o_lugar_da_real(self):
        """Controle positivo: o que o cliente velho entregava. Prova que a
        régua acima enxerga a perda — a cópia ocupa o teto e a real some."""
        self._toque("da-pagina", "41", replay=False)
        self._toque("sorteado-no-reenvio", "41")
        self._toque("toque-novo", "42")
        self.assertEqual(self._pesos(), [41, 41])

    def test_na_ordem_dos_toques_o_teto_grava_as_duas(self):
        """N2 consertado: 3 → 4 da fila, depois o toque online (a série a mais
        pedida, `extra=1`). Todas gravadas, cada uma no seu número."""
        self._toque("fila-3", "43")
        self._toque("fila-4", "44")
        self._toque("online-5", "45", extra="1")
        self.assertEqual(self._pesos(), [43, 44, 45])

    def test_controle_o_toque_online_na_frente_perde_a_serie_da_fila(self):
        """Controle positivo: o toque online passando na frente. O item 4 bate
        no teto, sai da fila com 200, e a série de 44 kg nunca existe."""
        self._toque("online-5", "45", replay=False, extra="1")
        self._toque("fila-3", "43")
        resposta = self._toque("fila-4", "44")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self._pesos(), [45, 43])


# ------------------------------------------------- rodada 1 da revisão (04/10/2026)


class ARecusaDeIdentidadeDevolveOPostNativoTests(SimpleTestCase):
    """I1 (IMPORTANT): a série 3 ficou na fila e a sessão do aparelho morreu
    (senha trocada noutro aparelho, saída noutra aba). A drenagem recebe 503
    `replay_offline_sem_sessao` e o item fica. Com a captura online do N2,
    TODO toque seguinte da página entrava atrás dele e ficava também, com a
    tela dizendo "enviando…" — medido no navegador, rodada 1 do relatório.
    Antes do N2, o primeiro toque levava à tela de entrar."""

    def test_a_recusa_de_identidade_levanta_a_marca_e_qualquer_saida_a_desliga(self):
        drena = corpo_da_funcao(_fila(), "function emSerieAtePreservar(itens, i) {")
        envio = drena[drena.index("return enviar(item)") :]
        barreira = envio[envio.index("if (r.status === 503) {") : envio.index('if (veredito(r) === "espera") return;')]
        self.assertIn("return r.json().then(function (j) {", barreira)
        self.assertIn("if (SEM_IDENTIDADE.indexOf(j.code) >= 0) semSessao = true;", barreira)
        # `aplicou` e `recusou` passam pelo mesmo ponto, depois da espera e
        # antes de remover.
        desliga = envio.index("semSessao = false;")
        self.assertLess(envio.index('if (veredito(r) === "espera") return;'), desliga)
        self.assertLess(desliga, envio.index("remover(item.op_id)"))
        self.assertIn("var semSessao = false;", _fila())

    def test_com_a_marca_o_toque_online_segue_o_post_nativo(self):
        """O agora já sai da frente (`pendentes>0`); a fila também sai, e o
        POST nativo cai na tela de entrar sem gravar — nada passa na frente."""
        self.assertIn("if (navigator.onLine && (!pendentes || semSessao)) return;", _captura())

    def test_os_codigos_sao_os_da_barreira(self):
        """Contrato: a lista do cliente é a do servidor. Um código renomeado em
        `accounts/replay.py` desligaria a marca calado."""
        lista = re.search(r"var SEM_IDENTIDADE = \[(.*?)\];", _fila()).group(1)
        self.assertEqual(
            sorted(re.findall(r'"([^"]+)"', lista)),
            sorted([CODIGO_SEM_SESSAO, CODIGO_OUTRA_SESSAO]),
        )


class ARecusaDeIdentidadeNoServidorTests(BaseDoFluxo):
    """O contrato em que a marca `semSessao` se apoia, na rota da série."""

    def setUp(self):
        self.user = pessoa("fila-identidade@exemplo.com")
        tornar_hoje(self.user, "A")
        self.exercicio = next(
            i.exercise for i in services.estado_do_treino(self.user).itens if not i.exercise.sem_carga
        )
        self.corpo = {"exercise_id": self.exercicio.pk, "weight_kg": "40", "reps": "8", "op_id": "na-fila"}

    def _replay(self):
        return self.client.post(
            reverse("workouts:record_set"), self.corpo, HTTP_X_REQUESTED_WITH="fetch",
            HTTP_X_NUTRIPLAN_REPLAY="1", HTTP_X_NUTRIPLAN_DONO=str(self.user.pk),
        )

    def test_sem_sessao_a_drenagem_recebe_503_json_com_o_codigo(self):
        resposta = self._replay()
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta["Content-Type"], "application/json")
        self.assertEqual(resposta.json()["code"], CODIGO_SEM_SESSAO)
        self.assertFalse(ExerciseLog.objects.filter(user=self.user).exists())

    def test_com_outra_conta_a_drenagem_recebe_o_outro_codigo(self):
        outra = pessoa("fila-identidade-b@exemplo.com")
        self.client.force_login(outra)
        resposta = self._replay()
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json()["code"], CODIGO_OUTRA_SESSAO)
        self.assertFalse(ExerciseLog.objects.exists())

    def test_sem_sessao_o_post_nativo_vai_para_entrar_e_nao_grava(self):
        """O caminho que a marca devolve: navegação do formulário (o mesmo
        `op_id` no corpo, sem cabeçalho de replay). Vai para a tela de entrar
        e não grava — por isso não passa na frente do item da fila."""
        resposta = self.client.post(
            reverse("workouts:record_set"), self.corpo,
            HTTP_SEC_FETCH_DEST="document", HTTP_ACCEPT="text/html",
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/entrar/", resposta["Location"])
        self.assertFalse(ExerciseLog.objects.filter(user=self.user).exists())


class AFalhaAoGuardarDevolveOBotaoTests(SimpleTestCase):
    """MINOR 1: com item pendente o toque online é capturado, e se o IndexedDB
    parou (WebKit depois de suspenso) `guardar` falha. A faixa mandava "com
    conexão, toque de novo" com rede, e o botão ficava travado."""

    def test_com_rede_a_faixa_manda_recarregar(self):
        js = _fila()
        ouvinte = js[js.index('addEventListener("nutriplan:fila-falhou"') :]
        ouvinte = ouvinte[: ouvinte.index("});")]
        self.assertIn("navigator.onLine", ouvinte)
        self.assertIn("Recarregue a página e toque de novo.", ouvinte)
        # Sem rede, o texto de antes.
        self.assertIn("Com conexão, toque de novo.", ouvinte)
        # E `pendentes` NÃO é zerado: o toque direto passaria na frente.
        self.assertNotIn("pendentes = 0", ouvinte)

    def test_o_botao_do_formulario_volta(self):
        captura = _captura()
        falha = captura[captura.index(".catch(function (erro)") :]
        self.assertIn('form.dispatchEvent(new CustomEvent("nutriplan:fila-falhou", { bubbles: true', falha)
        pwa = _pwa()
        ouvinte = pwa[pwa.index('document.addEventListener("nutriplan:fila-falhou"') :]
        ouvinte = ouvinte[: ouvinte.index("}, 0);")]
        # Depois do `setTimeout(0)` que trava o botão no `submit`: medido no
        # navegador, a falha imediata chegava antes e o botão voltava a travar.
        adiado = ouvinte[ouvinte.index("setTimeout(function () {") :]
        self.assertIn("b.disabled = false;", adiado)


class ComRedeNenhumaNotaDizAguardandoRedeTests(SimpleTestCase):
    """MINOR 2: água, refeição e a faixa diziam "aguardando rede" e "esperando
    conexão" com rede, e a nota "enviando…" nunca saía."""

    def test_agua_e_refeicao_nao_fixam_aguardando_rede(self):
        pwa = _pwa()
        for assinatura in ("function aguaEnfileirada(form, dados) {", "function refeicaoEnfileirada(form) {"):
            with self.subTest(funcao=assinatura):
                self.assertNotIn("aguardando rede", corpo_da_funcao(pwa, assinatura))

    def test_a_faixa_diz_enviando_com_rede(self):
        js = _fila()
        faixa = js[js.index('document.addEventListener("nutriplan:fila", function (evento) {') :]
        faixa = faixa[: faixa.index("});")]
        self.assertIn('var estado = navigator.onLine && !semSessao ? "enviando…" : "esperando conexão";', faixa)
        self.assertIn('"1 marcação " + estado', faixa)

    def test_a_fila_vazia_esconde_a_nota(self):
        pwa = _pwa()
        ouvinte = pwa[pwa.index('document.addEventListener("nutriplan:fila", function (evento) {') :]
        ouvinte = ouvinte[: ouvinte.index("});")]
        self.assertIn("evento.detail.pendentes !== 0) return;", ouvinte)
        self.assertIn('querySelectorAll("[data-aguardando-rede]")', ouvinte)
        self.assertIn("nota.hidden = true;", ouvinte)


class UmToqueUmDonoTests(SimpleTestCase):
    """MINOR 3: a página velha servida pelo worker não consulta `pendentes`,
    chama `preventDefault` e faz o `fetch`; a fila nova capturava o mesmo
    toque com `op_id` sorteado — duas séries para um toque."""

    def test_a_fila_nao_captura_o_que_outro_ouvinte_levou(self):
        captura = _captura()
        guarda = captura.index("if (evento.defaultPrevented) return;")
        self.assertLess(captura.index("!permitida(form.action)) return;"), guarda)
        self.assertLess(guarda, captura.index("evento.preventDefault();"))
