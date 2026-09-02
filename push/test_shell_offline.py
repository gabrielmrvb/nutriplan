"""A tela de offline e um SHELL: ela nao pode carregar sessao nenhuma.

O service worker pre-cacheia `/offline/` no install, dentro do cache de
ESTATICOS — e esse cache nao e limpo no logout, de proposito: CSS e icone nao
tem nada pessoal. A tela de offline, porem, e renderizada pelo Django.

Com `cache.addAll(SHELL)` recebendo URL crua, a requisicao leva cookie (o
padrao e `same-origin`). Resultado medido no navegador, com o servidor
derrubado de proposito para forcar o fallback:

    data-usuario="717"      <- a chave primaria de OUTRA pessoa
    data-autenticado="1"
    18x "Faltou completar seu cadastro..."   <- mensagens da sessao dela

A sessao ativa no momento era a 725. Dois danos:

1. privacidade — o identificador e as mensagens da pessoa anterior ficam no
   aparelho sem prazo, sobrevivendo ao logout;
2. correcao — `fila.js` le exatamente `data-usuario` para decidir de quem e
   cada operacao pendente. Uma marcacao feita a partir dessa tela nasceria com
   o dono errado.

A correcao tem duas camadas: o worker pede o shell com `credentials: "omit"`,
e a propria view marca `shell_offline`, para que o template nao emita
identidade nem mensagem ainda que alguem troque aquele `Request` por uma URL.
"""
from pathlib import Path

from django.test import TestCase

from plans.tests import create_complete_user

RAIZ = Path(__file__).resolve().parent.parent


class ShellOfflineNaoCarregaSessaoTests(TestCase):
    def setUp(self):
        self.pessoa = create_complete_user(email="shell@exemplo.com")
        self.client.force_login(self.pessoa)

    def test_o_shell_nao_traz_a_chave_primaria_de_ninguem(self):
        resposta = self.client.get("/offline/")

        self.assertContains(resposta, 'data-usuario=""')
        self.assertNotContains(resposta, 'data-usuario="%d"' % self.pessoa.pk)

    def test_o_shell_sai_como_anonimo(self):
        resposta = self.client.get("/offline/")

        self.assertContains(resposta, 'data-autenticado="0"')

    def test_controle_uma_tela_normal_ainda_declara_o_dono(self):
        """Sem isto, remover `data-usuario` do site inteiro passaria nos testes
        acima como se fosse conserto — e a fila offline pararia de saber de
        quem e cada operacao."""
        resposta = self.client.get("/")

        self.assertContains(resposta, 'data-usuario="%d"' % self.pessoa.pk)
        self.assertContains(resposta, 'data-autenticado="1"')

    def test_o_shell_nem_mostra_nem_CONSOME_a_mensagem_pendente(self):
        """As duas metades do dano, num teste so.

        Mostrar a mensagem de outra sessao e o vazamento. Consumi-la e o outro
        lado: a mensagem seria congelada dentro da copia cacheada e a pessoa
        certa nunca a veria na tela dela.
        """
        self.client.post("/agua/", {"ml": "37"})  # valor invalido -> messages.error

        offline = self.client.get("/offline/")
        self.assertNotContains(offline, "Quantidade de água inválida")

        seguinte = self.client.get("/")
        self.assertContains(seguinte, "Quantidade de água inválida")


class OWorkerPedeOShellSemCookieTests(TestCase):
    """A primeira camada, no proprio service worker."""

    def setUp(self):
        self.sw = self.client.get("/sw.js").content.decode()

    def test_o_precache_omite_credenciais(self):
        trecho = self.sw[self.sw.index('addEventListener("install"'):][:1600]

        self.assertIn('credentials: "omit"', trecho)
        self.assertNotIn("cache.addAll(SHELL)", trecho)

    def test_a_tela_de_offline_esta_no_shell(self):
        """Controle positivo: se ela sair do SHELL, os testes acima ficam
        verdes sem provar nada, porque nao ha mais o que pre-cachear."""
        self.assertIn("const SHELL = [OFFLINE_URL", self.sw)

    def test_o_shell_vai_para_o_cache_de_estaticos_e_nao_o_de_paginas(self):
        """E por isso que ele precisa ser neutro: o cache de estaticos
        sobrevive ao logout."""
        trecho = self.sw[self.sw.index('addEventListener("install"'):][:1600]

        self.assertIn("caches\n      .open(CACHE)", trecho)
        self.assertNotIn("CACHE_PAGINAS", trecho)
