"""O token de CSRF que o formulário envia é o de AGORA, não o da renderização.

RAIZ do "a sessão cai e perde o que eu digitei" (item 1 da missão de UX,
22/09/2026). Não havia logout nenhum em POST: o que havia era 403 de CSRF, e
ele tem dois caminhos MEDIDOS neste app, os dois com a página certa e a
pessoa certa:

1. a página veio do cache do service worker (ele serve a cópia guardada
   quando a rede passa de 3 s) e traz o token de uma sessão anterior;
2. a pessoa entrou de novo — em outra aba, ou porque a sessão tinha vencido —
   e `login()` chamou `rotate_token()`, que troca o segredo do cookie. A aba
   antiga continua com o token velho no HTML.

Nos dois casos o COOKIE está certo e só o campo escondido do formulário está
velho. `static/js/pwa.js` ("TOKEN DE CSRF") reescreve o campo com o valor do
cookie no carregamento e de novo no `submit`, e o 403 deixa de acontecer.

Isto NÃO enfraquece a proteção, e é o que os dois primeiros testes deste
arquivo existem para provar: o cookie só é legível por JavaScript da PRÓPRIA
origem (é disso que a defesa vive), e um token de outro segredo continua
sendo recusado. É também o que a documentação do Django manda fazer em
requisição AJAX — ler `csrftoken` e mandá-lo de volta.

A terceira prova é do arquivo do cliente: a régua textual com sabotagem, que
é como este repositório prende JavaScript que a suíte não executa.
"""
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse


class OFormularioAceitaOTokenDoCookieTests(TestCase):
    """A propriedade de que o cliente depende: mandar o VALOR DO COOKIE no
    campo escondido é aceito. Se um dia `CSRF_COOKIE_MASKED` for ligado, ou o
    Django mudar o formato, este teste fica vermelho — e não a produção."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("accounts:login")

    def _cookie(self):
        self.client.get(self.url)
        return self.client.cookies["csrftoken"].value

    def test_o_valor_cru_do_cookie_e_aceito_como_token_do_formulario(self):
        cookie = self._cookie()
        resposta = self.client.post(
            self.url,
            {"login": "ninguem@exemplo.com", "password": "x", "csrfmiddlewaretoken": cookie},
        )
        # 200 = o formulário rodou e recusou as credenciais; 403 seria o CSRF.
        self.assertEqual(resposta.status_code, 200)

    def test_token_de_outro_segredo_continua_recusado(self):
        """O controle positivo: a recusa ainda existe, e é ela que protege."""
        self._cookie()
        resposta = self.client.post(
            self.url,
            {
                "login": "ninguem@exemplo.com",
                "password": "x",
                "csrfmiddlewaretoken": "a" * 64,
            },
        )
        self.assertEqual(resposta.status_code, 403)


class OClienteRenovaOTokenTests(TestCase):
    """O bloco que faz isso no navegador, prendido pelo texto do arquivo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = Path(settings.BASE_DIR, "static", "js", "pwa.js").read_text(encoding="utf-8")

    def test_o_pwa_js_le_o_cookie_csrftoken(self):
        self.assertIn("csrftoken", self.js)

    def test_ele_reescreve_o_campo_escondido_do_formulario(self):
        self.assertIn("csrfmiddlewaretoken", self.js)

    def test_e_renova_no_submit_tambem(self):
        """Só no carregamento não basta: a aba pode ficar aberta horas, e é
        nela que o token envelhece. O ouvinte é de CAPTURA, para rodar antes
        de qualquer `submit` da própria página."""
        trecho = self.js[self.js.index("TOKEN DE CSRF"):]
        trecho = trecho[: trecho.index("/* ====") if "/* ====" in trecho else 4000]
        self.assertIn('"submit"', trecho)
        self.assertIn("true", trecho)  # capture

    def test_a_fila_e_o_formulario_seguem_a_MESMA_regra(self):
        """`fila.js` já trocava o token pelo do momento do envio, e por isso
        a água marcada sem rede nunca sofreu com isto. O formulário comum é
        que estava de fora. Os dois lendo o cookie é a regra única — se um
        deles voltar a confiar no HTML renderizado, este teste cai."""
        fila = Path(settings.BASE_DIR, "static", "js", "fila.js").read_text(encoding="utf-8")
        for arquivo, texto in (("fila.js", fila), ("pwa.js", self.js)):
            with self.subTest(arquivo=arquivo):
                self.assertIn("csrftoken=([^;]+)", texto)
