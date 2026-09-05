"""Testes da robustez offline: cache de páginas, fila e privacidade.

A parte que exige mais cuidado aqui não é a fila — é o que o cache guarda. HTML
autenticado carrega o nome, o peso e a dieta da pessoa, e um cache que
sobrevive ao logout num aparelho compartilhado entrega isso ao próximo que
abrir o app.
"""
from pathlib import Path

from push.test_cache_privado import sem_comentarios
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from plans.tests import create_complete_user

RAIZ = Path(settings.BASE_DIR)


class ServiceWorkerOfflineTests(TestCase):
    def setUp(self):
        self.sw = self.client.get(reverse("service_worker")).content.decode()

    def test_pages_are_cached_for_offline_reading(self):
        """Sem isto o app não ABRE sem rede: a navegação ia direto para a tela
        de offline, mesmo em páginas já visitadas."""
        self.assertIn("CACHE_PAGINAS", self.sw)
        self.assertIn('request.mode === "navigate"', self.sw)
        self.assertIn("cacheName: CACHE_PAGINAS", self.sw)

    def test_the_offline_page_is_still_the_last_resort(self):
        """Cache de página só ajuda em página já visitada. A tela de offline
        continua servindo para a rota que a pessoa nunca abriu."""
        self.assertIn("OFFLINE_URL", self.sw)

    def test_authenticated_pages_live_in_a_separate_cache(self):
        """A separação é de privacidade, não de organização: sair da conta
        precisa levar o HTML pessoal e NÃO levar o CSS, que não tem nada
        pessoal e custaria um download novo."""
        self.assertNotEqual(
            self.sw.count("CACHE_PAGINAS"), 0, "não há cache separado de páginas"
        )
        # O cache do shell continua sendo outro.
        self.assertIn("const CACHE =", self.sw)

    def test_the_queue_drains_in_the_background_where_it_can(self):
        self.assertIn('event.tag === "nutriplan-fila"', self.sw)
        self.assertIn("drenarFila", self.sw)

    def test_a_refused_item_leaves_the_queue(self):
        """4xx é o servidor recusando o conteúdo. Reenviar não conserta, e
        manter faria a pessoa carregar para sempre algo que nunca vai passar."""
        self.assertIn("resposta.status >= 400 && resposta.status < 500", self.sw)


class LogoutPrivacyTests(TestCase):
    def setUp(self):
        self.pwa = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")

    def test_leaving_the_account_clears_the_page_cache(self):
        self.assertIn('dataset.autenticado === "0"', self.pwa)
        self.assertIn("caches.delete", self.pwa)

    def test_only_the_page_cache_is_cleared(self):
        """Derrubar o cache de CSS e ícones junto faria a próxima abertura
        baixar tudo de novo, e eles não têm nada pessoal.

        A asserção não depende mais da ORDEM do arquivo. A versão anterior
        dividia o texto no marcador de sessão e procurava `-paginas` depois
        dele — o que amarrava o teste ao layout do código e quebrou quando a
        limpeza virou uma função só, chamada de dois lugares.

        Esta versão é mais forte: exige que TODA remoção de cache no arquivo
        esteja dentro do caminho filtrado por `-paginas`. Uma segunda
        `caches.delete` em qualquer lugar reprova, inclusive uma que a versão
        antiga deixaria passar se estivesse antes do marcador.
        """
        remocoes = [
            i for i in range(len(self.pwa))
            if self.pwa.startswith("caches.delete(", i)
        ]

        self.assertEqual(len(remocoes), 1, "só a limpeza de páginas remove cache")
        contexto = self.pwa[max(0, remocoes[0] - 300) : remocoes[0]]
        self.assertIn('indexOf("-paginas")', contexto)

    def test_the_page_says_whether_someone_is_logged_in(self):
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn('data-autenticado="0"', html)

        self.client.force_login(create_complete_user())
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn('data-autenticado="1"', html)


class QueueScopeTests(TestCase):
    """O que a fila cobre — e o que ela recusa a cobrir."""

    def setUp(self):
        cru = (RAIZ / "static" / "js" / "fila.js").read_text(encoding="utf-8")
        # SEM COMENTÁRIOS, e a lição custou caro aqui. A versão anterior lia o
        # arquivo cru e procurava `"carga"` nele. Quando a carga SAIU da fila,
        # o commit que a removeu escreveu sete menções à palavra explicando por
        # quê — e o teste continuou VERDE afirmando que a fila cobre a carga.
        # Medido: `carga` aparecia 3 vezes no arquivo e 0 fora de comentário.
        #
        # É a armadilha que o `CLAUDE.md` nomeia, na direção mais perigosa: o
        # teste não só deixou de proteger como passou a documentar o sistema ao
        # contrário, e nunca mais reprovaria.
        self.fila = sem_comentarios(cru)
        # A lista literal, que é onde a pergunta "o que a fila cobre?" mora.
        self.rotas = self.fila[self.fila.index("ROTAS = [") :]
        self.rotas = self.rotas[: self.rotas.index("];") + 2]

    def test_a_fila_cobre_agua_e_marcacao_de_refeicao(self):
        for rota in ("agua", "marcar"):
            with self.subTest(rota=rota):
                self.assertIn(rota, self.rotas)

    def test_e_nao_cobre_mais_nada(self):
        """Controle positivo do teste acima: ele sozinho ficaria verde se a
        lista GANHASSE rotas. Duas entradas, e são estas duas."""
        self.assertEqual(self.rotas.count("/^"), 2, self.rotas)

    def test_a_carga_de_treino_saiu_da_fila(self):
        """Saiu com a funcionalidade INTACTA — o registro online segue igual.

        O corpo daquele formulário carrega um contador defasado, e o replay
        dele apaga série e reescreve peso. Ver
        `workouts/test_carga_fora_da_fila.py` e `CAMPANHA — CARGA OFFLINE V2`.
        """
        self.assertNotIn("carga", self.rotas)
        self.assertNotIn("treino", self.rotas)

    def test_suplemento_saiu_da_fila_junto_com_a_tela(self):
        """A rota não existe mais; enfileirar para ela seria guardar um POST
        que vai bater em 404 quando a rede voltar — e a fila reenviaria em
        silêncio, sem ninguém descobrir.

        Diferente da carga: o suplemento saiu porque a FUNCIONALIDADE saiu
        (`3536b61`), e ele esteve mesmo na fila antes disso (`326aaa2`).
        """
        self.assertNotIn("suplementos", self.fila)

    def test_it_refuses_anything_that_reads_server_state_to_decide(self):
        """Enfileirar o assistente produziria decisões tomadas sobre dados
        velhos: uma troca de exercício calculada sobre a ficha de ontem,
        aplicada amanhã."""
        for perigosa in ("ajustar", "recalibrar", "recalcular", "substituir"):
            with self.subTest(rota=perigosa):
                self.assertNotIn(perigosa, self.fila)

    def test_every_queued_item_carries_an_identifier(self):
        """A rede não garante entrega única. Sem identificador, reenviar
        "+500 ml" duas vezes registra um litro que ninguém bebeu."""
        self.assertIn("dados.op_id = identificador()", self.fila)

    def test_it_does_not_hijack_the_normal_post_when_there_is_network(self):
        """A fila é para a falta de rede, não um substituto do POST — e um
        interceptador que sempre pega quebraria o formulário para todo mundo
        no dia em que o IndexedDB falhar."""
        self.assertIn("if (navigator.onLine) return;", self.fila)

    def test_the_page_shows_what_is_waiting(self):
        """Marcar sem rede e não ver retorno é indistinguível de não ter
        funcionado — e aí a pessoa toca de novo, enfileirando duas vezes."""
        self.assertIn("esperando conexão", self.fila)

    def test_the_queue_script_only_loads_for_someone_logged_in(self):
        """As quatro rotas exigem sessão. Enfileirar algo que vai voltar 302
        para o login é encher a fila de lixo."""
        base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
        trecho = base.split("fila_js_url", 1)[0]
        self.assertIn("{% if user.is_authenticated %}", trecho[-400:])

    def test_the_queue_ships_in_the_offline_shell(self):
        """Um script de offline que só existe online não serve para nada."""
        sw = self.client.get(reverse("service_worker")).content.decode()
        self.assertIn("js/fila", sw)
