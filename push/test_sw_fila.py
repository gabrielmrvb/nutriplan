"""A fila drenada pelo service worker: A e B no mesmo aparelho.

## O que estes testes sao, e o que nao sao

Nao existe runtime JavaScript neste ambiente — nao ha Node, nao ha Playwright.
Entao o worker nao e EXECUTADO aqui. O que estes testes fazem e montar, contra
a stack Django real, exatamente o pedido que `drenarFila()` monta (mesmo corpo,
mesmos cabecalhos, sem seguir redirect, com `enforce_csrf_checks`) e aplicar a
resposta a MESMA regra de remocao que esta no arquivo.

E evidencia de classe E: teste automatizado. Prova o contrato do servidor e a
regra do cliente; nao prova que o navegador dispara o `sync`.

## A ordem das camadas, medida

Eu esperava que no worker o CSRF recusasse primeiro, porque o token do item
esta velho. Errado: `CsrfViewMiddleware` valida em `process_view`, que roda
DEPOIS da fase de request de todos os middlewares. A barreira de identidade
fala antes — e num item com dono alheio ela responde `de_outra_sessao`, nao
`csrf_expirado`, nos DOIS clientes.

O CSRF continua sendo quem decide o que a barreira deixa passar: o cliente
publicado, que nao declara dono nenhum.

`fila.js` renova o CSRF antes de enviar; o worker NAO — ele nao tem DOM nem
`document.cookie`. Isso importa para o item de quem ESTA logado: se essa pessoa
entrou de novo depois de enfileirar, o token do item envelheceu e o worker nao
consegue sincronizar. Fica para o `fila.js`, na proxima abertura do app.

Por que o worker nao ganha um endpoint de CSRF: seria superficie nova para um
ganho que ja existe. Com o token velho o servidor responde de forma
preservavel, o item fica, e a proxima abertura do app sincroniza pelo
`fila.js`, que tem o token atual. O worker adianta o que da e nao perde nada —
e o `CLAUDE.md` ja registra que Background Sync nem existe no Safari do iPhone.
"""
import re
from pathlib import Path

from django.test import Client, TestCase

from accounts.models import SyncedOperation
from accounts.replay import CODIGO_OUTRA_SESSAO, STATUS_PRESERVA
from plans.models import HydrationLog
from plans.tests import create_complete_user

RAIZ = Path(__file__).resolve().parent.parent


def o_worker_removeria(resposta) -> bool:
    """A regra de remocao exatamente como `drenarFila()` a escreve.

    O 302 continua preservando. Ele NAO deve mais aparecer para o protocolo
    novo — o servidor traduz o redirect de sucesso em 200 —, e e justamente por
    isso que a regra fica: se um redirect voltar a chegar aqui, e porque algo
    mudou, e preservar e a resposta segura.
    """
    if resposta.status_code in (301, 302, 303, 307, 308):
        return False  # `redirect: "manual"` -> opaqueredirect
    if resposta.status_code in (401, 403):
        return False
    if resposta.status_code >= 500:
        return False
    return resposta.status_code < 400 or 400 <= resposta.status_code < 500


class FilaDoWorkerTests(TestCase):
    """A + B e legado + B, na sessao de B."""

    def setUp(self):
        self.a = create_complete_user(email="sw-a@exemplo.com")
        self.b = create_complete_user(email="sw-b@exemplo.com")
        self.c = Client(enforce_csrf_checks=True)

    def _token_de(self, quem):
        """Entra num cliente separado e devolve o token do formulario."""
        outro = Client(enforce_csrf_checks=True)
        outro.force_login(quem)
        outro.get("/")
        return outro.cookies["csrftoken"].value

    def _como_o_worker_envia(self, item):
        """O pedido que `drenarFila()` monta, campo por campo."""
        cabecalhos = {
            "HTTP_X_REQUESTED_WITH": "fetch",
            "HTTP_X_NUTRIPLAN_REPLAY": "1",
        }
        if item.get("dono"):
            cabecalhos["HTTP_X_NUTRIPLAN_DONO"] = str(item["dono"])
        return self.c.post(
            item["url"],
            item["dados"],
            content_type="application/x-www-form-urlencoded",
            **cabecalhos
        )

    @staticmethod
    def _corpo(ml, op_id, token):
        return "ml=%s&op_id=%s&csrfmiddlewaretoken=%s" % (ml, op_id, token)

    def test_fila_com_a_e_b_na_sessao_de_b(self):
        """O teste principal: A preserva, B sincroniza, e A nao trava B.

        A ordem e deliberada — A vem PRIMEIRO. Se o worker parasse no primeiro
        item recusado, B nunca chegaria a ser tentado, e a pessoa logada
        perderia a sincronizacao por causa de um item que nao e dela.
        """
        token_a = self._token_de(self.a)
        self.c.force_login(self.b)
        self.c.get("/")
        token_b = self.c.cookies["csrftoken"].value

        fila = [
            {"op_id": "de-a", "dono": self.a.pk, "url": "/agua/",
             "dados": self._corpo(750, "de-a", token_a)},
            {"op_id": "de-b", "dono": self.b.pk, "url": "/agua/",
             "dados": self._corpo(250, "de-b", token_b)},
        ]

        sobreviveram, respostas = [], {}
        for item in fila:
            r = self._como_o_worker_envia(item)
            respostas[item["op_id"]] = r
            if not o_worker_removeria(r):
                sobreviveram.append(item["op_id"])

        # ITEM A: preservado, e nada mudou em conta nenhuma.
        self.assertIn("de-a", sobreviveram)
        self.assertFalse(HydrationLog.objects.filter(user=self.a).exists())
        self.assertFalse(SyncedOperation.objects.filter(op_id="de-a").exists())
        self.assertGreaterEqual(respostas["de-a"].status_code, 400)

        # ITEM B: aplicado, e SO em B.
        self.assertNotIn("de-b", sobreviveram)
        self.assertEqual(HydrationLog.objects.get(user=self.b).ml, 250)
        self.assertTrue(
            SyncedOperation.objects.filter(user=self.b, op_id="de-b").exists()
        )
        self.assertFalse(HydrationLog.objects.filter(user=self.a).exists())

    def test_qual_camada_recusa_o_item_de_a(self):
        """Nomear a camada em vez de supor qual foi.

        Eu supus CSRF, porque o token do item esta velho. E a barreira: o CSRF
        so valida em `process_view`, depois da fase de request dos middlewares.
        Este teste existe para que a suposicao nao volte a entrar na
        documentacao sem medicao.
        """
        token_a = self._token_de(self.a)
        self.c.force_login(self.b)
        self.c.get("/")

        r = self._como_o_worker_envia(
            {"op_id": "x", "dono": self.a.pk, "url": "/agua/",
             "dados": self._corpo(750, "x", token_a)}
        )

        self.assertEqual(r.status_code, STATUS_PRESERVA)
        self.assertEqual(r.json()["code"], CODIGO_OUTRA_SESSAO)

    def test_legado_sem_dono_nao_bloqueia_o_item_de_b(self):
        """Item enfileirado antes da separacao: sem dono e com token velho."""
        token_velho = self._token_de(self.a)
        self.c.force_login(self.b)
        self.c.get("/")
        token_b = self.c.cookies["csrftoken"].value

        fila = [
            {"op_id": "legada", "dono": None, "url": "/agua/",
             "dados": self._corpo(500, "legada", token_velho)},
            {"op_id": "de-b", "dono": self.b.pk, "url": "/agua/",
             "dados": self._corpo(250, "de-b", token_b)},
        ]
        sobreviveram = [
            i["op_id"] for i in fila
            if not o_worker_removeria(self._como_o_worker_envia(i))
        ]

        self.assertEqual(sobreviveram, ["legada"])
        self.assertEqual(HydrationLog.objects.get(user=self.b).ml, 250)
        self.assertFalse(SyncedOperation.objects.filter(op_id="legada").exists())

    def test_o_worker_nao_inventa_dono_para_o_item_legado(self):
        """Adotar o legado para a sessao atual seria recriar o vazamento."""
        fonte = self.client.get("/sw.js").content.decode()
        corpo = fonte[fonte.index("async function drenarFila"):][:2800]

        self.assertIn("if (item.dono)", corpo)
        self.assertNotIn("item.dono || ", corpo)


class OWorkerNaoSeAutoDerrubaTests(TestCase):
    """O `db` precisa viver na funcao inteira, e nao dentro do `try`.

    Isto nao e teste de string: ele localiza a declaracao, descobre onde o
    bloco que a contem FECHA, e exige que todo uso esteja antes disso. Um
    `const db` movido para dentro de qualquer bloco reprova, seja qual for a
    forma como o codigo em volta esteja escrito.

    O bug que motivou o teste: com `const db` dentro do `try`,
    `removerDaFila(db, ...)` lancava `ReferenceError` — engolido pelo `catch`
    do laco, entao nenhum item saia da fila — e `db.close()` lancava solto,
    rejeitando `drenarFila()`. Quem chama e `event.waitUntil`, entao o
    Background Sync lia falha e REAGENDAVA: gravava, nao removia, tentava de
    novo.
    """

    def setUp(self):
        fonte = self.client.get("/sw.js").content.decode()
        inicio = fonte.index("async function drenarFila")
        bruto = fonte[inicio: fonte.index("\n}", inicio) + 2]
        self.corpo = self._sem_comentarios(bruto)

    @staticmethod
    def _sem_comentarios(codigo):
        """Analise de estrutura nao pode ler comentario.

        O primeiro corte deste teste achou `db.close()` DENTRO do comentario
        que explica o bug, dez linhas antes da chamada de verdade, e reprovou
        o codigo certo. Comentario e texto SOBRE o codigo, nao codigo — e um
        teste estrutural que le comentario mede a documentacao.
        """
        return re.sub(r"/\*.*?\*/", " ", codigo, flags=re.S)

    def _fim_do_bloco(self, indice):
        """Onde fecha o bloco que contem `indice`."""
        profundidade = 0
        for i in range(indice, len(self.corpo)):
            if self.corpo[i] == "{":
                profundidade += 1
            elif self.corpo[i] == "}":
                if profundidade == 0:
                    return i
                profundidade -= 1
        return len(self.corpo)

    def test_o_db_vive_ate_o_fim_da_funcao(self):
        declaracao = re.search(r"\b(?:let|const|var)\s+db\b", self.corpo)
        self.assertIsNotNone(declaracao, "onde foi parar a declaracao do `db`?")

        alcance = self._fim_do_bloco(declaracao.end())
        usos = [m.start() for m in re.finditer(r"\bdb\b", self.corpo)]

        fora = [u for u in usos if u > alcance]
        self.assertEqual(
            fora,
            [],
            "`db` e usado depois do bloco onde foi declarado: ReferenceError em "
            "tempo de execucao, engolido pelo catch do laco.",
        )

    def test_fechar_o_banco_nao_derruba_o_sync(self):
        """Uma excecao no `close()` viraria sync falhado e reagendamento.

        Medido pela estrutura, e nao por proximidade de texto: o `close()`
        precisa estar dentro de um bloco que tenha um `catch`.
        """
        onde = self.corpo.index("db.close()")
        abertura = self.corpo.rfind("try {", 0, onde)
        self.assertNotEqual(abertura, -1, "`db.close()` fora de qualquer try")

        fecha = self._fim_do_bloco(abertura + len("try {"))
        self.assertGreater(fecha, onde, "o try fecha antes do `db.close()`")
        self.assertIn("catch", self.corpo[fecha: fecha + 40])
