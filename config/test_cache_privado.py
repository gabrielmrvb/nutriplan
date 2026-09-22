"""A tela de quem está logado não fica legível depois que a pessoa sai.

ACHADO DE SEGURANÇA, medido em 22/09/2026 numa sessão logada do staging
(`fetch` same-origin enxerga todo cabeçalho de resposta): `/historico/`,
`/treino/` e `/conta/perfil/` respondiam **sem `Cache-Control` nenhum**.
Sem diretiva, o cache do navegador guarda a página por heurística — e
"guardar" aqui é peso, altura, e-mail, objetivo e histórico de treino: dado
de saúde, o mesmo que a etapa 1 do cadastro pede autorização para tratar
(LGPD art. 11). Num aparelho de casa, sair da conta e apertar VOLTAR
redesenhava a tela da pessoa anterior a partir do disco, sem passar pelo
servidor.

A diretiva é `private, no-cache, must-revalidate` e **não** `no-store`, e as
duas escolhas são a mesma decisão:

- `private` tira a página de qualquer cache compartilhado;
- `no-cache` obriga a revalidar ANTES de reusar — depois do logout a
  revalidação devolve o 302 do login, e é isso que apaga a tela de trás;
- `no-store` quebraria duas coisas medidas: o service worker recusa guardar
  o que vem com `no-store` (`podeGuardar`, em `templates/pwa/sw.js`), e é
  o cache dele que faz a dieta abrir no metrô; e o Chrome desliga o
  bfcache numa página `no-store`, que é justamente o "Voltar ao formulário"
  do 403 devolvendo o que a pessoa digitou.

Quem já declara a própria diretiva (login e gestão com `never_cache`, a
exportação com `no-store`) não é tocado: a regra só preenche o silêncio.
"""
from django.test import TestCase
from django.urls import reverse

from plans.tests import create_complete_user

PRIVADO = "private"


class TelaLogadaNaoFicaNoCacheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="cache@exemplo.com")

    def setUp(self):
        self.client.force_login(self.user)

    def _cache_control(self, rota):
        resposta = self.client.get(rota)
        self.assertEqual(resposta.status_code, 200, rota)
        return resposta.headers.get("Cache-Control", "")

    def test_as_telas_com_dado_de_saude_sao_privadas_e_revalidadas(self):
        """Peso, altura, e-mail e histórico não podem ser reusados do disco."""
        for nome in ("plans:today", "plans:history", "accounts:profile"):
            with self.subTest(rota=nome):
                diretiva = self._cache_control(reverse(nome))
                self.assertIn(PRIVADO, diretiva)
                self.assertIn("no-cache", diretiva)

    def test_nao_manda_no_store_porque_o_worker_e_o_bfcache_dependem_disso(self):
        """`no-store` desligaria o cache offline do PWA e o botão Voltar."""
        for nome in ("plans:today", "plans:history"):
            with self.subTest(rota=nome):
                self.assertNotIn("no-store", self._cache_control(reverse(nome)))

    def test_quem_ja_diz_no_store_continua_dizendo(self):
        """O `never_cache` do login é mais estrito, e a regra não o afrouxa."""
        self.client.logout()
        diretiva = self.client.get(reverse("accounts:login")).headers.get("Cache-Control", "")
        self.assertIn("no-store", diretiva)

    def test_a_tela_anonima_continua_cacheavel(self):
        """A landing é pública e é ela que o service worker pré-cacheia; pôr
        `private` nela tiraria a capa do app do cache de borda sem proteger
        ninguém."""
        self.client.logout()
        self.assertEqual(self.client.get("/").headers.get("Cache-Control", ""), "")

    def test_a_sonda_de_vida_nao_paga_a_consulta_de_sessao(self):
        """`request.user` é um `SimpleLazyObject`, e LÊ-LO na fase de resposta
        forçaria a consulta de sessão em TODA resposta do app.
        `/saude/vivo/` promete zero consultas e é a sonda que bate de 5 em 5
        minutos — a primeira versão desta regra quebrou a promessa, e a suíte
        pegou. A guarda é `_wrapped is empty`: usuário que a view não resolveu
        não teve dado nenhum na tela."""
        self.client.logout()
        with self.assertNumQueries(0):
            resposta = self.client.get("/saude/vivo/")
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("private", resposta.headers.get("Cache-Control", ""))

    def test_o_worker_continua_podendo_guardar_essa_diretiva(self):
        """A régua do worker é literal: ele recusa `no-store` e só isso. Este
        teste lê o arquivo do worker para a regra do servidor e a do cliente
        não divergirem em silêncio."""
        from pathlib import Path

        from django.conf import settings

        worker = Path(settings.BASE_DIR, "templates", "pwa", "sw.js").read_text(encoding="utf-8")
        self.assertIn('indexOf("no-store") === -1', worker)
        self.client.force_login(self.user)
        self.assertNotIn("no-store", self._cache_control(reverse("plans:today")))
