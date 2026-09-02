"""Todo link interno que o app oferece precisa responder.

O bug que motivou este teste: a politica de privacidade dizia "voce pode baixar
uma copia em <a href="/conta/exportar/">Exportar meus dados</a>" — e aquela rota
so aceita POST, de proposito. Com GET, uma pagina de terceiro faria o navegador
de quem esta logado baixar o proprio historico de saude sem um clique sequer.

Entao o link estava errado, nao a rota: quem clicasse recebia 405 na pagina que
explica justamente como exercer esse direito. Encontrado varrendo os links no
navegador, nao lendo o codigo.

O teste segue o `<a href>` como uma pessoa seguiria. Nao substitui revisao, mas
fecha a porta para "link que aponta para rota que nao aceita GET" — que e um
erro silencioso: o template compila, a URL existe, e so quem clica descobre.
"""
import re

from django.core.management import call_command

from plans.tests import CatalogFixture, create_complete_user

#: Telas que oferecem navegacao. Se uma tela nova aparecer e nao entrar aqui,
#: os links dela nao sao varridos — por isso a lista fica junto do teste, e nao
#: escondida numa fixture.
TELAS = (
    "/",
    "/treino/",
    "/treino/agora/",
    "/treino/corridas/",
    "/historico/",
    "/conta/perfil/",
    "/lista-de-compras/",
    "/conquistas/",
    "/privacidade/",
    "/termos/",
    "/conta/excluir/",
)

LINK = re.compile(r'<a\b[^>]*\bhref="(/[^"#?]*)', re.I)


class TodoLinkInternoRespondeTests(CatalogFixture):
    """`CatalogFixture` + `seed_workouts`: sem cardapio e sem ficha, metade das
    telas nem abre, e o teste mediria a fixture em vez dos links."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_complete_user(email="links@exemplo.com")
        self.client.force_login(self.pessoa)

    def _links_de(self, caminho):
        resposta = self.client.get(caminho)
        self.assertEqual(
            resposta.status_code, 200, "a propria tela %s nao abre" % caminho
        )
        return set(LINK.findall(resposta.content.decode()))

    def test_nenhum_link_leva_a_erro(self):
        origem = {}
        for tela in TELAS:
            for destino in self._links_de(tela):
                origem.setdefault(destino, tela)

        # Controle positivo: se a extracao parar de achar links, o laco abaixo
        # roda vazio e o teste fica verde sem ter visitado nada.
        self.assertGreater(len(origem), 8, "a varredura nao achou links")

        quebrados = []
        for destino, tela in sorted(origem.items()):
            status = self.client.get(destino).status_code
            if status >= 400:
                quebrados.append("%s (em %s) -> %s" % (destino, tela, status))

        self.assertEqual(quebrados, [], "links internos que nao respondem")

    def test_exportar_continua_recusando_get(self):
        """O contrato que o link errado violava.

        Se alguem "consertar" o 405 abrindo a rota para GET, o link volta a
        funcionar e a protecao morre junto — por isso o teste acima vem
        acompanhado deste.
        """
        self.assertEqual(self.client.get("/conta/exportar/").status_code, 405)
        self.assertEqual(self.client.post("/conta/exportar/").status_code, 200)
