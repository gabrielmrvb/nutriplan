# -*- coding: utf-8 -*-
"""A sessão acaba, e as páginas guardadas vão junto.

`CACHE_PAGINAS` guarda uma cópia de cada tela visitada, e é ela que faz a dieta
abrir no metrô. O `sw.js` já nomeava o problema, para as telas de gestão:
"guardadas no cache, elas sobrevivem ao logout e ficam legíveis para qualquer
coisa com acesso ao perfil do navegador". A conclusão de lá foi não cachear
`/admin/` e `/gestao/`.

O mesmo vale para as telas da PRÓPRIA pessoa, e nada as apagava. Medido no
navegador antes da correção: a cópia de `/hoje/` tinha 55.831 bytes, com
`data-usuario`, `data-autenticado="1"` e as cinco refeições do dia — e
continuava lá depois de a sessão terminar.

`limpar()` não resolvia: ela roda no `activate` e só descarta gerações
antigas. Uma sessão que termina não muda a versão do cache.

O gatilho é a TELA DE ENTRAR, e não o botão de sair, porque sessão que EXPIRA
não passa por logout nenhum — e cai exatamente aqui.
"""
import re

from django.test import SimpleTestCase, TestCase

from config.settings import BASE_DIR

SW = (BASE_DIR / "templates" / "pwa" / "sw.js").read_text(encoding="utf-8")


def sem_comentarios(texto):
    """O código sem os comentários.

    Este projeto comenta muito, e uma asserção que procura `CACHE_PAGINAS` acha
    a menção dele na frase que explica por que ele existe. A sabotagem que
    REMOVE a linha passaria verde — foi exatamente o que aconteceu num teste da
    Corrida, e a lição está sendo aplicada antes de custar de novo.
    """
    sem_bloco = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"^\s*//.*$", "", sem_bloco, flags=re.M)


def corpo_do_handler(evento):
    """O corpo de um `addEventListener` do worker, contando chaves."""
    marca = 'self.addEventListener("%s"' % evento
    inicio = SW.index(marca)
    abre = SW.index("{", SW.index("=>", inicio))
    nivel = 0
    for i in range(abre, len(SW)):
        if SW[i] == "{":
            nivel += 1
        elif SW[i] == "}":
            nivel -= 1
            if nivel == 0:
                return SW[abre : i + 1]
    raise AssertionError("o handler de %s não fecha" % evento)


class OWorkerEsqueceAsPaginasQuandoAvisadoTests(SimpleTestCase):
    """A limpeza existe, apaga a coisa certa, e só ela."""

    def test_existe_um_handler_de_mensagem(self):
        self.assertIn('self.addEventListener("message"', SW)

    def test_ele_apaga_o_cache_de_paginas(self):
        corpo = sem_comentarios(corpo_do_handler("message"))

        self.assertIn("caches.delete(CACHE_PAGINAS)", corpo)

    def test_ele_nao_apaga_o_cache_de_estaticos(self):
        """CSS e ícone não têm nada pessoal, e apagá-los faria a próxima
        abertura ser lenta sem proteger ninguém. Pior: o `/offline/` mora ali,
        e sem ele a pessoa sem rede vê a página de erro do navegador."""
        corpo = sem_comentarios(corpo_do_handler("message"))

        self.assertNotRegex(corpo, r"caches\.delete\(CACHE\)")

    def test_ele_so_reage_ao_recado_combinado(self):
        """Um handler que apaga em qualquer mensagem seria apagado por
        qualquer script da origem que resolvesse conversar com o worker."""
        corpo = sem_comentarios(corpo_do_handler("message"))

        self.assertIn('event.data.tipo !== "esquecer-paginas"', corpo)


class QuemPedeAlimpezaEATelaDeEntrarTests(TestCase):
    """O gatilho precisa acertar os dois jeitos de a sessão acabar, e errar
    o terceiro caso de propósito."""

    def test_a_tela_de_entrar_pede_a_limpeza(self):
        corpo = self.client.get("/conta/entrar/").content.decode()

        self.assertIn("esquecer-paginas", corpo)

    def test_a_tela_de_offline_NAO_pede(self):
        """Ela também renderiza sem autenticação. Apagar as páginas justamente
        quando a rede caiu seria destruir o que o offline existe para servir —
        e é o modo mais fácil de esta correção virar um defeito pior."""
        corpo = self.client.get("/offline/").content.decode()

        self.assertNotIn("esquecer-paginas", corpo)

    def test_a_tela_de_cadastro_NAO_pede(self):
        """Contra-controle de escopo: se qualquer página anônima pedisse, o
        teste de cima passaria por acidente e a regra seria outra."""
        corpo = self.client.get("/conta/cadastro/").content.decode()

        self.assertNotIn("esquecer-paginas", corpo)


class OQueContinuaSendoGuardadoTests(SimpleTestCase):
    """Contra-controle da correção inteira.

    Se a resposta fosse "pare de cachear página autenticada", o app perderia o
    offline — que é o motivo de o cache existir. A correção precisa deixar o
    cacheamento em pé.
    """

    def test_a_navegacao_continua_guardando_pagina(self):
        self.assertIn("caches.open(CACHE_PAGINAS).then((c) => c.put(request, copia))", SW)

    def test_as_telas_operacionais_continuam_fora(self):
        """A proteção que já existia não pode ter sido substituída por esta."""
        self.assertIn("ehTelaOperacional", SW)
        self.assertIn('url.pathname.startsWith("/gestao/")', SW)
