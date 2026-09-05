# -*- coding: utf-8 -*-
"""A fila drena na ORDEM DOS TOQUES, e os dois lados concordam sobre qual é.

O que estes testes seguram, e por que cada um existe:

A store usa `keyPath: "op_id"`, e `op_id` é um `crypto.randomUUID()`. O
IndexedDB devolve `getAll()` em ordem de CHAVE — ou seja, de UUID. Medido em
navegador real, 300 rodadas: **51,7% de inversão com duas operações** (teórico
50%) e **85,7% com três** (teórico 83,3%). Como somar, zerar e desfazer não
comutam, isso muda o resultado: `+500 → +500 → desfazer` termina em 500, e
drenado ao contrário termina em 1.000.

A correção não foi ordenar pelo `em: Date.now()` que já existia, e isso também
foi medido em vez de decidido no papel: **199 de 200** chamadas seguidas caem no
mesmo milissegundo, e com `em` empatado o `sort` estável preserva a ordem de
entrada do array — que é a ordem do UUID. Ordenar por tempo herdaria o defeito
em 83,5% dos empates, e ainda quebraria quando o relógio do aparelho andasse
para trás.

O que existe é `seq`, um contador monotônico calculado como `maior + 1` DENTRO
da transação de escrita. Medido com 60 gravações disparadas juntas: zero
empates, `seq` de 1 a 60 contíguo, sem lock — o IndexedDB serializa transações
de escopo sobreposto.

Estes testes aqui são de ESTRUTURA: eles leem os dois arquivos e afirmam que as
peças existem e que os dois lados dizem a mesma coisa. O COMPORTAMENTO do
comparador foi medido no navegador, contra o arquivo servido, e não cabe em
teste Python — não existe Node neste ambiente.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from push.test_cache_privado import sem_comentarios
from push.test_replay import corpo_da_funcao


class OsDoisLadosOrdenamIgualTests(TestCase):
    """A mesma fila, drenada por dois programas diferentes.

    `fila.js` drena quando a rede volta; `sw.js` drena num evento `sync`, sem
    aba aberta. Se ordenarem diferente, a mesma sequência de toques produz
    estados diferentes conforme quem chegou primeiro — e ninguém consegue
    reproduzir o relato de quem reclamar.
    """

    #: Funções que TÊM de existir idênticas nos dois arquivos.
    COMPARTILHADAS = (
        "function emOrdemDeToque(itens) {",
        "function corpoDoItem(item, token) {",
    )

    def setUp(self):
        raiz = Path(settings.BASE_DIR)
        self.pagina = (raiz / "static" / "js" / "fila.js").read_text(encoding="utf-8")
        self.worker = self.client.get("/sw.js").content.decode()

    def _normalizada(self, texto, assinatura):
        corpo = corpo_da_funcao(sem_comentarios(texto), assinatura)
        # Sem comentários E sem espaço em branco: `fila.js` vive dentro de uma
        # IIFE e é indentado; `sw.js` é de primeiro nível. Comparar cru
        # reprovaria por indentação, que não é a pergunta.
        return re.sub(r"\s+", " ", corpo).strip()

    def test_as_funcoes_compartilhadas_sao_identicas_nos_dois_arquivos(self):
        for assinatura in self.COMPARTILHADAS:
            with self.subTest(funcao=assinatura):
                self.assertEqual(
                    self._normalizada(self.pagina, assinatura),
                    self._normalizada(self.worker, assinatura),
                    "os dois lados divergiram em %s" % assinatura,
                )

    def test_a_comparacao_enxerga_uma_diferenca_de_um_token(self):
        """Controle positivo do teste acima.

        Normalizar espaço e tirar comentário é o que faz a comparação ser sobre
        a LÓGICA — e é também o que poderia apagar a diferença que ela existe
        para achar. Este teste troca um `-` por um `+` numa das funções e exige
        que a comparação reprove.
        """
        original = self._normalizada(self.pagina, self.COMPARTILHADAS[0])
        mexido = original.replace("return la - lb;", "return lb - la;")

        self.assertNotEqual(original, mexido, "a sabotagem nao mudou nada")
        self.assertNotEqual(mexido, self._normalizada(self.worker, self.COMPARTILHADAS[0]))

    def test_o_desempate_por_op_id_existe_nos_dois(self):
        """O teste de identidade acima NÃO pega isto, e a lacuna foi medida.

        Ele compara os dois arquivos entre si: uma sabotagem que remova o
        desempate DOS DOIS ao mesmo tempo mantém a igualdade e passa verde.
        Sem o desempate, dois itens legados com o mesmo `em` voltam à ordem de
        entrada do array — que é a ordem do UUID —, e a página e o worker
        drenam diferente na prática, cada um recebendo o `getAll()` na sua vez.

        Esta asserção é ESTRUTURAL e está declarada como tal. O comportamento
        do desempate foi medido no navegador contra o arquivo servido: 50
        embaralhamentos da mesma entrada empatada, sempre a mesma saída.
        """
        for nome, texto in (("fila.js", self.pagina), ("sw.js", self.worker)):
            with self.subTest(arquivo=nome):
                corpo = corpo_da_funcao(
                    sem_comentarios(texto), "function emOrdemDeToque(itens) {"
                )
                self.assertIn("if (a.op_id < b.op_id) return -1;", corpo)
                self.assertIn("if (a.op_id > b.op_id) return 1;", corpo)

    def test_nenhum_dos_dois_drena_a_lista_crua(self):
        """`getAll()` devolve em ordem de UUID. Quem drenar o retorno cru dele
        está drenando embaralhado."""
        pagina = sem_comentarios(self.pagina)
        worker = sem_comentarios(self.worker)

        self.assertIn("emOrdemDeToque(", corpo_da_funcao(pagina, "function meus() {"))
        self.assertIn(
            "for (const item of emOrdemDeToque(itens))",
            corpo_da_funcao(worker, "async function drenarFila() {"),
        )


class ANumeracaoDoToqueTests(TestCase):
    def setUp(self):
        raiz = Path(settings.BASE_DIR)
        self.pagina = sem_comentarios(
            (raiz / "static" / "js" / "fila.js").read_text(encoding="utf-8")
        )

    def test_o_numero_e_calculado_DENTRO_da_transacao_de_escrita(self):
        """Ler fora e gravar depois é leitura-modificação-escrita, e duas abas
        leriam o mesmo maior — o mesmo defeito que a soma de água já teve.

        A prova de que funciona é do navegador: 60 gravações disparadas juntas,
        zero empates. O que este teste segura é a FORMA, para ninguém "limpar"
        a numeração para fora da transação e reabrir a janela.
        """
        corpo = corpo_da_funcao(self.pagina, "function guardar(item) {")

        self.assertIn('comLoja("readwrite"', corpo)
        self.assertIn("proximoSeq(", corpo)
        self.assertIn("l.put(item)", corpo)

    def test_a_numeracao_ignora_o_que_nao_e_numero(self):
        """Item legado não tem `seq`, e um `seq` que não seja número não pode
        virar `NaN + 1` e envenenar toda a fila dali para frente."""
        corpo = corpo_da_funcao(self.pagina, "function proximoSeq(itens) {")

        self.assertIn('typeof itens[i].seq === "number"', corpo)


class ACapturaNaoPerdeCampoTests(TestCase):
    """Duas perdas medidas no navegador, as duas no mesmo ponto do código."""

    def setUp(self):
        raiz = Path(settings.BASE_DIR)
        self.pagina = sem_comentarios(
            (raiz / "static" / "js" / "fila.js").read_text(encoding="utf-8")
        )
        self.captura = self.pagina[self.pagina.index('addEventListener("submit"') :]

    def test_o_botao_que_enviou_entra_na_captura(self):
        """`new FormData(form)` NÃO inclui o botão de envio.

        O "Pulei" da refeição manda o `status` no próprio `<button>`, e mais
        nada. Medido: as chaves capturadas eram `["csrfmiddlewaretoken"]`. O
        servidor recusa `status` ausente com um redirect mudo, a barreira de
        replay traduz o 302 em 200, e a fila APAGA o item — a refeição pulada
        sumia sem deixar rastro.
        """
        self.assertIn("evento.submitter", self.captura)
        self.assertIn("pares.push([botao.name, botao.value])", self.captura)

    def test_a_captura_guarda_PARES_e_nao_um_objeto(self):
        """Objeto colapsa chave repetida.

        O "Comi outra coisa" manda três pares `alimento`/`gramas` e o servidor
        lê com `getlist`. Medido: `3 -> 1`, e o que sobrava era a linha VAZIA,
        porque a última vence. O registro nascia com a descrição e macros
        zerados.
        """
        self.assertIn("pares.push([k, v])", self.captura)
        self.assertIn("pares: pares,", self.captura)

    def test_o_objeto_continua_sendo_gravado_para_quem_le_o_formato_antigo(self):
        """Controle da compatibilidade: `dados` não pode sumir enquanto houver
        código — ou item — que só conhece ele."""
        self.assertIn("dados: dados,", self.captura)

    def test_o_envio_le_os_dois_formatos(self):
        corpo = corpo_da_funcao(self.pagina, "function corpoDoItem(item, token) {")

        self.assertIn("var pares = item.pares;", corpo)
        # `!pares.length` junto: `[]` é truthy, então `if (!pares)` sozinho
        # deixaria um item com `pares` vazio ir sem nenhum campo em vez de cair
        # no `dados`. Não é alcançável pela captura de hoje — ela sempre empurra
        # o `op_id` —, e é a guarda certa mesmo assim: registro corrompido em
        # IndexedDB não é hipótese exótica neste projeto.
        self.assertIn("if (!pares || !pares.length) {", corpo)
        self.assertIn("item.dados", corpo)


class ADrenagemParaNoPrimeiroPreservadoTests(TestCase):
    """Ordenar não basta: seguir em frente com o anterior na fila desordena de
    um jeito que SOBREVIVE à drenagem.

    Com `+500` preservado por 503 e `zerar` logo depois aplicado, o dia fica em
    0; na drenagem seguinte o `+500` finalmente passa e o dia termina em 500,
    quando o certo era 0. A pessoa zerou o dia e ele voltou sozinho, horas
    depois, sem que nada tivesse falhado visivelmente.
    """

    def setUp(self):
        raiz = Path(settings.BASE_DIR)
        self.pagina = sem_comentarios(
            (raiz / "static" / "js" / "fila.js").read_text(encoding="utf-8")
        )
        self.worker = sem_comentarios(self.client.get("/sw.js").content.decode())

    def test_a_pagina_so_avanca_depois_de_remover(self):
        """`meus()` já filtrou UM dono, então a página pode parar seco."""
        corpo = corpo_da_funcao(self.pagina, "function emSerieAtePreservar(itens, i) {")

        self.assertIn('if (veredito(r) === "espera") return;', corpo)
        # O avanço mora DENTRO do `.then` da remoção: sem prova de saída da
        # fila, o índice não anda.
        self.assertIn(
            "return remover(item.op_id).then(function () {", corpo
        )
        self.assertIn("return emSerieAtePreservar(itens, i + 1);", corpo)

    #: Os três ramos que PRESERVAM o item. Cada um tem de travar o dono na
    #: própria linha — não em algum lugar da função.
    RAMOS_QUE_PRESERVAM = (
        'if (resposta.type === "opaqueredirect") { travados.add(deQuem); continue; }',
        'if (resposta.status === 401 || resposta.status === 403) '
        "{ travados.add(deQuem); continue; }",
        "if (resposta.status >= 500) { travados.add(deQuem); continue; }",
    )

    def test_o_worker_trava_o_DONO_e_nao_a_fila(self):
        """Ele drena fila de vários donos e não sabe quem está logado.

        Parar a fila inteira faria o primeiro item estrangeiro — que o servidor
        recusa com 503 por não ser a sessão atual — travar para sempre a
        sincronização de quem ESTÁ logado. Por isso a trava é por dono, e por
        isso `push/test_replay.py` proíbe `break;` aqui.
        """
        corpo = corpo_da_funcao(self.worker, "async function drenarFila() {")

        self.assertIn("const travados = new Set();", corpo)
        self.assertIn("if (travados.has(deQuem)) continue;", corpo)
        for ramo in self.RAMOS_QUE_PRESERVAM:
            with self.subTest(ramo=ramo[:40]):
                self.assertIn(ramo, corpo, "este ramo preserva o item e nao trava")

    def test_a_rede_caindo_tambem_trava_o_dono(self):
        """O `catch` é o quarto caminho que preserva, e é o mais comum: a rede
        volta a cair no meio da drenagem."""
        corpo = corpo_da_funcao(self.worker, "async function drenarFila() {")
        # O `catch` DO LAÇO, e não o último do arquivo: `drenarFila` termina
        # com um `try { db.close(); } catch (e) {}` vazio, e `rindex` caía nele
        # — a asserção falhava olhando o bloco errado. O do laço é o primeiro
        # depois da remoção.
        depois_da_remocao = corpo.index("await removerDaFila(db, item.op_id);")
        captura = corpo[corpo.index("} catch (e) {", depois_da_remocao) :]
        captura = captura[: captura.index("continue;") + len("continue;")]

        self.assertIn("travados.add(deQuem);", captura)

    def test_o_caminho_de_SUCESSO_nao_trava_o_dono(self):
        """Contar `travados.add` não bastava, e isso foi MEDIDO.

        A versão anterior deste teste exigia quatro ocorrências na função. Uma
        sabotagem que TIRA a trava do ramo `>= 500` e a PÕE junto da remoção
        mantém quatro — e passou verde na suíte inteira, reintroduzindo o
        defeito que esta campanha existe para corrigir, mais um novo: travar no
        sucesso faz cada sincronização drenar um item por pessoa e parar.

        Contar diz quantos; só olhar ONDE diz se está certo. As asserções agora
        são por ramo, e esta cobre o lado que não pode ter nenhuma.
        """
        corpo = corpo_da_funcao(self.worker, "async function drenarFila() {")
        sucesso = corpo[corpo.index("if (resposta.ok ||") :]
        sucesso = sucesso[: sucesso.index("} catch (e) {")]

        self.assertIn("await removerDaFila(db, item.op_id);", sucesso)
        self.assertNotIn("travados.add", sucesso)


class NinguemFicaEsperandoParaSempreTests(TestCase):
    """`blocked` dispara, e sem handler a promessa não liquida NUNCA.

    Uma subida de versão só acontece quando nenhuma conexão antiga está aberta,
    e o worker segura a dele durante a drenagem inteira. Sem `onblocked`,
    `abrir()` não resolve nem rejeita: o botão fica travado, o evento
    `nutriplan:enfileirado` nunca dispara, e não há uma linha no console.

    Não há versão nova hoje. Isto é para o dia em que houver — que é exatamente
    o dia em que ninguém vai lembrar de olhar aqui.
    """

    def setUp(self):
        raiz = Path(settings.BASE_DIR)
        self.pagina = sem_comentarios(
            (raiz / "static" / "js" / "fila.js").read_text(encoding="utf-8")
        )
        self.worker = sem_comentarios(self.client.get("/sw.js").content.decode())

    def test_os_dois_lados_rejeitam_quando_o_banco_esta_bloqueado(self):
        """REJEITAM, e não apenas "tratam".

        A versão anterior procurava a palavra `onblocked` e nada mais. Um
        handler que só registrasse a ocorrência a satisfazia — e deixaria a
        promessa pendurada, que é o defeito inteiro. Medido: trocar
        `reject(new Error(` por `void (new Error(` passava verde.
        """
        for nome, texto in (("fila.js", self.pagina), ("sw.js", self.worker)):
            with self.subTest(arquivo=nome):
                inicio = texto.index("onblocked")
                # Até o fim da atribuição: o handler é uma expressão só nos dois.
                handler = texto[inicio : texto.index(";", texto.index("Error(", inicio))]
                self.assertIn("reject(", handler)
                self.assertIn("Error(", handler)

    def test_os_dois_lados_soltam_o_banco_quando_o_outro_quer_subir(self):
        """Sem `versionchange`, a conexão aberta é ela própria o bloqueio."""
        # As duas metades numa asserção SÓ. Separadas, a segunda era satisfeita
        # por `db.close()` pré-existente em outros três lugares do arquivo:
        # esvaziar o handler passava verde, e foi medido.
        for nome, texto, forma in (
            ("fila.js", self.pagina,
             "db.onversionchange = function () { db.close(); };"),
            ("sw.js", self.worker, "db.onversionchange = () => db.close();"),
        ):
            with self.subTest(arquivo=nome):
                self.assertIn(forma, texto)
