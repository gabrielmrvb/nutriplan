"""B7 — PWA: o cache do worker passa a obedecer o `no-store` do servidor.

O contrato manda preservar `/admin/` e `/gestao/` fora do cache, auditar se
existe OUTRA rota autenticada com PII entrando em `CACHE_PAGINAS`, e — se
existir — "corrigir com regra estrutural, não lista frágil de páginas uma por
uma quando possível".

A auditoria encontrou o buraco na forma, e não numa rota: até aqui NADA no
worker consultava a resposta antes de guardá-la. A única proteção era
`ehTelaOperacional`, uma lista de dois prefixos. Qualquer tela privada fora
dessa lista entraria no cache de páginas, e a lista precisa ser lembrada por
quem escrever a próxima view.

O servidor já sabe quais são: `never_cache` responde
`no-cache, no-store, must-revalidate, private`. `podeGuardar` passa a obedecer
`no-store`, que é literalmente "não persista isto" — e daí em diante toda view
marcada com `never_cache` fica protegida sem editar o `sw.js`.

FALSO POSITIVO desta auditoria, registrado para não voltar: a exportação de
dados (`accounts/exportacao.py`) manda `Cache-Control: no-store` e carrega
dados de saúde, mas é `http_method_names = ["post"]` e o worker começa com
`if (request.method !== "GET") return;`. Ela nunca chegou perto do cache.

`private` NÃO entra na condição, e é decisão: ele proíbe cache COMPARTILHADO, e
o cache do service worker é do perfil daquele navegador — o mesmo que faz a
dieta abrir no metrô.
"""
import re

from django.test import TestCase


class ARegraDoNoStoreTests(TestCase):
    """A regra existe, é consultada antes de guardar, e vale nos dois caches.

    Estes testes leem o código do worker porque não há Node neste ambiente e o
    `sw.js` é servido por template. A execução de verdade da função está na
    classe seguinte.
    """

    def setUp(self):
        self.fonte = self.client.get("/sw.js").content.decode()

    def test_existe_uma_funcao_que_decide_se_pode_guardar(self):
        self.assertIn("function podeGuardar(response)", self.fonte)

    def test_a_regra_le_o_cabecalho_da_resposta(self):
        corpo = self._corpo("podeGuardar")

        self.assertIn("Cache-Control", corpo)
        self.assertIn("no-store", corpo)

    def test_a_regra_compara_o_token_e_nao_um_pedaco_de_texto(self):
        """A primeira versão usava expressão regular com limite de palavra, e o
        escape virou CARACTERE DE CONTROLE no arquivo: a expressão passou a
        procurar 0x08 + "no-store" + 0x08 e nunca casou com nada. Comparar o
        token separado por vírgula não tem escape que possa dar errado."""
        corpo = self._corpo("podeGuardar")

        self.assertIn('split(",")', corpo)
        self.assertIn('indexOf("no-store")', corpo)

    def test_o_worker_publicado_nao_tem_caractere_de_controle(self):
        """A guarda geral, e é ela que teria pego o defeito.

        Um 0x08 no meio de uma expressão regular não aparece num `grep`, não
        quebra a sintaxe e não muda o que um teste de texto lê — ele só faz a
        regra parar de casar. O arquivo INTEIRO é conferido, e não só esta
        função: o próximo escape mal escrito pode cair em qualquer linha.
        """
        maus = sorted(
            {ord(c) for c in self.fonte if ord(c) < 32 and c not in "\n\t\r"}
        )

        self.assertEqual(maus, [], "códigos de controle no sw.js: %s" % maus)

    def test_a_regra_exige_resposta_ok_tambem(self):
        """Trocar `response.ok` pela leitura do cabeçalho, e não somar as
        duas, faria o worker guardar 404 e 500."""
        self.assertIn("response.ok", self._corpo("podeGuardar"))

    def test_private_nao_entra_na_condicao(self):
        """`private` proíbe cache COMPARTILHADO. O cache do worker é do perfil
        do navegador daquela pessoa, e é ele que faz o app abrir sem rede —
        tratar `private` como proibição desligaria o app no dia em que alguém
        marcasse uma tela comum com ele."""
        self.assertNotIn("private", self._corpo("podeGuardar"))

    def test_a_navegacao_consulta_a_regra_antes_de_guardar(self):
        """O ponto do defeito: era `if (response.ok)` direto, sem olhar o
        cabeçalho."""
        trecho = self.fonte[self.fonte.index('request.mode === "navigate"'):]
        trecho = trecho[: trecho.index("event.waitUntil")]

        guarda = trecho.index("podeGuardar(response)")
        gravacao = trecho.index("CACHE_PAGINAS).then((c) => c.put")

        self.assertLess(guarda, gravacao)

    def test_o_cache_de_estaticos_usa_a_mesma_regra(self):
        """Uma regra que valesse só para navegação seria meia regra."""
        corpo = self._corpo("store")

        self.assertIn("podeGuardar(response)", corpo)

    def test_a_lista_de_prefixos_continua_existindo(self):
        """A regra COMPLEMENTA a guarda, não a substitui.

        `ehTelaOperacional` faz mais do que impedir o cache: ela faz o pedido
        não passar pelo worker. O contrato manda preservar essa correção.
        """
        self.assertIn('"/admin/"', self.fonte)
        self.assertIn('"/gestao/"', self.fonte)

    def _corpo(self, funcao):
        """O corpo EXECUTÁVEL, sem comentário.

        Sem tirar os comentários, uma asserção como "`private` não aparece
        aqui" passa a falhar no dia em que alguém CITA `private` na
        explicação. Pior: uma asserção positiva pode passar por causa de uma
        palavra escrita num comentário, sem que a linha exista de verdade —
        que é meia distância do defeito que este arquivo documenta.
        """
        inicio = self.fonte.index("function %s(" % funcao)
        bruto = self.fonte[inicio: self.fonte.index("\n}", inicio)]
        sem_bloco = re.sub(r"/\*.*?\*/", " ", bruto, flags=re.S)
        return re.sub(r"//[^\n]*", " ", sem_bloco)


class ARegraRodaDeVerdadeTests(TestCase):
    """A função executada, e não só lida.

    Ler o texto do worker prova que a linha está lá; não prova que ela decide
    certo. Aqui `podeGuardar` é extraída do `sw.js` publicado e avaliada num
    motor JavaScript de verdade, com objetos `Response` de mentira que
    respondem `headers.get` como o real.

    Sem motor disponível, o teste é PULADO em vez de passar em silêncio —
    teste que não roda e diz OK é pior que teste nenhum.
    """

    #: As respostas que importam: (rótulo, ok, Cache-Control, pode guardar?)
    CASOS = (
        ("página comum do app, sem cabeçalho", True, None, True),
        ("página comum, cabeçalho vazio", True, "", True),
        ("painel com never_cache", True,
         "max-age=0, no-cache, no-store, must-revalidate, private", False),
        ("no-store sozinho", True, "no-store", False),
        ("NO-STORE em caixa alta", True, "NO-STORE", False),
        ("no-store com espaço", True, "private, no-store", False),
        ("só private, que NÃO proíbe", True, "private", True),
        ("no-cache não é no-store", True, "no-cache", True),
        ("max-age não é no-store", True, "max-age=600", True),
        ("erro do servidor", False, None, False),
        ("404 sem cabeçalho", False, "", False),
    )

    def test_a_regra_decide_certo_em_cada_caso(self):
        motor = self._motor()
        fonte = self.client.get("/sw.js").content.decode()
        inicio = fonte.index("function podeGuardar(")
        funcao = fonte[inicio: fonte.index("\n}", inicio) + 2]

        for rotulo, ok, diretiva, esperado in self.CASOS:
            with self.subTest(caso=rotulo):
                obtido = motor(funcao, ok, diretiva)
                self.assertEqual(obtido, esperado, rotulo)

    def test_o_caso_do_painel_e_o_que_motivou_a_regra(self):
        """O controle positivo do conjunto: se este passasse, a regra não
        estaria fazendo nada."""
        motor = self._motor()
        fonte = self.client.get("/sw.js").content.decode()
        inicio = fonte.index("function podeGuardar(")
        funcao = fonte[inicio: fonte.index("\n}", inicio) + 2]

        self.assertFalse(
            motor(funcao, True,
                  "max-age=0, no-cache, no-store, must-revalidate, private")
        )

    def _motor(self):
        """Devolve `avaliar(funcao, ok, diretiva) -> bool`, ou pula o teste."""
        import json
        import shutil
        import subprocess

        binario = shutil.which("node") or shutil.which("deno")
        if binario is None:
            self.skipTest(
                "sem motor JavaScript neste ambiente — a decisão da regra "
                "fica provada só pela leitura do código"
            )

        def avaliar(funcao, ok, diretiva):
            programa = (
                funcao
                + "\nconst resposta = {ok: %s, headers: {get: () => %s}};"
                % (json.dumps(ok), json.dumps(diretiva))
                + "\nconsole.log(podeGuardar(resposta) ? '1' : '0');"
            )
            saida = subprocess.run(
                [binario, "-e", programa] if "deno" not in binario
                else [binario, "eval", programa],
                capture_output=True, text=True, timeout=30,
            )
            return saida.stdout.strip().endswith("1")

        return avaliar


class NenhumaOutraRotaPrivadaEntraNoCacheTests(TestCase):
    """A auditoria que o contrato pede, escrita como teste.

    "Não assumir que corrigir apenas Admin/Gestao resolveu todas as superfícies
    privadas." Uma view marcada com `never_cache` é a declaração do servidor de
    que aquilo não pode ser guardado — e agora o worker obedece a declaração.
    Este teste garante que a declaração continua sendo emitida por quem já a
    emitia, para a regra ter no que se apoiar.
    """

    def test_as_tres_rotas_do_painel_respondem_no_store(self):
        """A ponta que importa: o cabeçalho de verdade, na resposta de verdade.

        É dele que a regra do worker depende.
        """
        for rota in ("/gestao/", "/gestao/pessoas/", "/gestao/atividade/"):
            with self.subTest(rota=rota):
                resposta = self.client.get(rota)
                self.assertIn(
                    "no-store", resposta.headers.get("Cache-Control", "")
                )

    def test_a_tela_de_offline_continua_guardavel(self):
        """O contra-controle, e não é uma tela qualquer.

        Se tudo respondesse `no-store`, a regra desligaria o cache inteiro e o
        app pararia de abrir sem rede. `/offline/` é o caso extremo: ela É o
        que o worker serve quando não há rede, está no `SHELL` pré-cacheado, e
        se ela deixasse de poder ser guardada o modo offline morreria.

        A primeira versão deste teste usava `/conta/entrar/` como "tela comum"
        — e falhou, porque ela responde `no-store`. Ver
        `AsTelasDeAutenticacaoJaDiziamNoStoreTests`: o teste estava errado, e
        errado de um jeito que revelou a superfície que faltava.
        """
        resposta = self.client.get("/offline/")

        self.assertNotIn("no-store", resposta.headers.get("Cache-Control", ""))

    def test_a_exportacao_de_dados_nao_e_alcancavel_por_get(self):
        """O falso positivo desta auditoria.

        Ela manda `no-store` e carrega dado de saúde — mas é POST, e o worker
        ignora tudo que não é GET. Se um dia virar GET, ela passa a depender da
        regra nova, e este teste é o aviso.
        """
        from accounts.exportacao import ExportarDadosView

        self.assertEqual(ExportarDadosView.http_method_names, ["post"])

    def test_o_worker_so_olha_pedido_get(self):
        fonte = self.client.get("/sw.js").content.decode()
        cabeca = fonte[fonte.index('addEventListener("fetch"'):][:400]

        self.assertIn('request.method !== "GET"', cabeca)
        self.assertLess(
            cabeca.index('request.method !== "GET"'),
            cabeca.index("ehTelaOperacional"),
        )


class ATelaDeLoginJaDiziaNoStoreTests(TestCase):
    """A superfície que a auditoria do contrato pedia para procurar, e achou.

    "Auditar se existe outra rota autenticada contendo PII que ainda entra em
    CACHE_PAGINAS. Não assumir que corrigir apenas Admin/Gestao resolveu todas
    as superfícies privadas."

    Existe uma, e não é uma rota esquecida: a tela de ENTRAR. O `LoginView` do
    Django vem decorado com `never_cache`, então ela responde
    `no-cache, no-store, must-revalidate, private` desde sempre — e o worker
    vinha guardando, porque a única proteção era uma lista com dois prefixos que
    não a incluía.

    Ela não traz dado de outra pessoa, mas traz o formulário de credencial e o
    framework diz explicitamente para não persistir. Com a regra, ela para de
    ser guardada sem que ninguém precise listá-la.

    Medido rota a rota, e NÃO generalizado: `/conta/cadastro/` e
    `/conta/senha/` respondem sem `Cache-Control` nenhum. A primeira versão
    deste teste afirmava "as telas de credencial" no plural e falhou nas duas —
    o teste estava errado, e errar assim é como se descobre onde a decisão de
    fato mora.
    """

    def test_a_tela_de_entrar_pede_para_nao_ser_guardada(self):
        resposta = self.client.get("/conta/entrar/")

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("no-store", resposta.headers.get("Cache-Control", ""))

    def test_o_cadastro_e_o_esqueci_a_senha_nao_pedem(self):
        """O mapa honesto do que a regra alcança hoje.

        Registrado como medição, não como julgamento: se um dia essas duas
        também forem decoradas, a regra as protege sozinha — que é exatamente o
        ponto de ser regra e não lista.
        """
        for rota in ("/conta/cadastro/", "/conta/senha/"):
            with self.subTest(rota=rota):
                cabecalho = self.client.get(rota).headers.get(
                    "Cache-Control", ""
                )
                self.assertNotIn("no-store", cabecalho)

    def test_o_shell_pre_cacheado_nao_tem_pagina_de_credencial(self):
        """Se uma delas entrasse no `SHELL`, o `addAll` a guardaria por fora da
        regra — pré-cache não passa por `podeGuardar`."""
        fonte = self.client.get("/sw.js").content.decode()
        shell = fonte[fonte.index("const SHELL = ["):]
        shell = shell[: shell.index("]")]

        for rota in ("/conta/entrar/", "/conta/cadastro/", "/conta/senha/"):
            with self.subTest(rota=rota):
                self.assertNotIn(rota, shell)

    def test_o_shell_ainda_guarda_a_tela_de_offline(self):
        """O controle: o pré-cache continua fazendo o que existe para fazer."""
        fonte = self.client.get("/sw.js").content.decode()
        shell = fonte[fonte.index("const SHELL = ["):]
        shell = shell[: shell.index("]")]

        self.assertIn("OFFLINE_URL", shell)
