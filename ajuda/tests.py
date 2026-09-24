# -*- coding: utf-8 -*-
"""`/ajuda/`: a FAQ, "Reportar um problema" e "O que mudou".

O que importa provar aqui, e por quê:

- as três telas abrem SEM login — quem não consegue entrar é quem mais
  precisa delas;
- o formulário de problema chega PREENCHIDO (rota, versão, aparelho) e o
  e-mail sai para o dono com `Reply-To` da pessoa: é isso que faz um relato
  virar reprodução em vez de "deu erro";
- o formulário é público, então tem pote de mel e limite por IP e global —
  sem eles é um relé de e-mail aberto para o endereço do dono;
- "O que mudou" lê o `CHANGELOG.md` de verdade, e o arquivo tem a forma
  que o leitor espera (datas em ordem, um item por mudança).
"""
import re
from datetime import date
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import PedidoDeRecuperacao
from plans.tests import create_complete_user

from . import mudancas as leitor
from .views import LIMITE_GLOBAL, LIMITE_POR_IP, versao

SUPORTE = "dono@exemplo.com"


def _campo(html, nome):
    """O `value` do `<input name="nome">` renderizado, ou None."""
    m = re.search(r'<input[^>]*name="%s"[^>]*>' % re.escape(nome), html)
    if not m:
        return None
    v = re.search(r'value="([^"]*)"', m.group(0))
    return v.group(1) if v else ""


def _csrf(html):
    return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)


class TelasAbremSemLoginTests(TestCase):
    def test_as_tres_telas_e_a_confirmacao_respondem_200_para_quem_nao_esta_logado(self):
        for nome in ("ajuda:index", "ajuda:reportar", "ajuda:reportado", "ajuda:mudancas"):
            with self.subTest(nome=nome):
                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    def test_a_faq_e_uma_sanfona_com_as_quatro_areas_e_aponta_para_as_outras_duas_telas(self):
        html = self.client.get(reverse("ajuda:index")).content.decode()
        self.assertGreaterEqual(html.count('<details class="fora">'), 12)
        for titulo in ("A estimativa e o cardápio", "O treino", "Água, peso e progresso", "Conta, avisos e privacidade"):
            self.assertIn("<h2>%s</h2>" % titulo, html)
        self.assertIn('href="%s"' % reverse("ajuda:reportar"), html)
        self.assertIn('href="%s"' % reverse("ajuda:mudancas"), html)
        self.assertIn("<code>local</code>", html, "a versão em uso aparece na página")

    def test_a_faq_so_afirma_o_que_o_app_nao_faz_com_a_palavra_nao(self):
        """Três respostas dizem NÃO de propósito: caloria gasta, Apple Saúde e
        prescrição. Se alguém 'melhorar' a FAQ prometendo isso, o teste cai."""
        html = self.client.get(reverse("ajuda:index")).content.decode()
        self.assertIn("Nada de caloria gasta", html)
        self.assertIn("Não existe API web para isso", html)
        self.assertIn("não uma prescrição", html)

    def test_a_ajuda_e_encontravel_do_perfil_das_areas_e_da_tela_de_entrar(self):
        """Ancorado no TEXTO de cada porta, não no `href`: o rodapé legal do
        Perfil também aponta para a ajuda, e um `href` casaria com ele mesmo
        com o botão da conta apagado (a sabotagem mostrou)."""
        pessoa = create_complete_user(email="ajuda@exemplo.com")
        self.client.force_login(pessoa)
        html = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn('href="%s">Ajuda e reportar um problema</a>' % reverse("ajuda:index"), html)
        html = self.client.get(reverse("areas")).content.decode()
        # Em Mais a Ajuda é uma LINHA da lista de ferramentas (23/09/2026).
        self.assertIn('<span class="mapa__nome">Ajuda</span>', html)
        self.client.logout()
        with override_settings(LEGAL_PUBLICADO=False):
            html = self.client.get(reverse("accounts:login"), secure=True).content.decode()
            self.assertIn('href="%s"' % reverse("ajuda:index"), html, "a ajuda não depende do legal")
            self.assertNotIn(reverse("privacidade"), html)


class BuscadorTests(TestCase):
    """A FAQ e "o que mudou" são o texto que diz o que o produto faz — é por
    onde alguém ACHA o app —, então entram no sitemap e no índice; o
    formulário e a confirmação não são conteúdo e ficam `noindex`."""

    def test_a_faq_e_o_que_mudou_sao_rotas_publicas_e_estao_no_sitemap(self):
        from config.seo import ROTAS_PUBLICAS
        for nome in ("ajuda:index", "ajuda:mudancas"):
            with self.subTest(nome=nome):
                self.assertIn(reverse(nome), ROTAS_PUBLICAS)
                self.assertIn("<loc>http://testserver%s</loc>" % reverse(nome), self.client.get("/sitemap.xml").content.decode())

    def test_reportar_e_a_confirmacao_ficam_fora_do_indice(self):
        from config.seo import ROTAS_PUBLICAS
        for nome in ("ajuda:reportar", "ajuda:reportado"):
            with self.subTest(nome=nome):
                self.assertNotIn(reverse(nome), ROTAS_PUBLICAS)
                cabeca = self.client.get(reverse(nome)).content.decode().split("</head>", 1)[0]
                self.assertIn('<meta name="robots" content="noindex">', cabeca)


class VersaoTests(TestCase):
    def test_a_versao_e_o_commit_do_render_em_sete_caracteres_ou_local(self):
        with mock.patch.dict("os.environ", {"RENDER_GIT_COMMIT": "abcdef0123456789"}):
            self.assertEqual(versao(), "abcdef0")
        with mock.patch.dict("os.environ", {"RENDER_GIT_COMMIT": ""}):
            self.assertEqual(versao(), "local")


@override_settings(NUTRIPLAN_SUPORTE_EMAIL=SUPORTE)
class ReportarTests(TestCase):
    def test_o_formulario_chega_preenchido_com_rota_versao_e_aparelho(self):
        with mock.patch.dict("os.environ", {"RENDER_GIT_COMMIT": "1234567890"}):
            html = self.client.get(
                reverse("ajuda:reportar") + "?de=/treino/ficha/3/",
                HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            ).content.decode()
        self.assertEqual(_campo(html, "rota"), "/treino/ficha/3/")
        self.assertEqual(_campo(html, "versao"), "1234567")
        self.assertIn("iPhone", _campo(html, "dispositivo"))
        self.assertIn('name="versao"', html)
        self.assertIn("readonly", re.search(r'<input[^>]*name="versao"[^>]*>', html).group(0))

    def test_sem_de_a_rota_vem_do_referer_do_mesmo_host_e_nunca_de_outro(self):
        html = self.client.get(reverse("ajuda:reportar"), HTTP_REFERER="http://testserver/agua/?x=1").content.decode()
        self.assertEqual(_campo(html, "rota"), "/agua/?x=1")
        html = self.client.get(reverse("ajuda:reportar"), HTTP_REFERER="https://outro.exemplo.com/agua/").content.decode()
        self.assertEqual(_campo(html, "rota"), "")

    def test_quem_esta_logado_ja_tem_o_email_preenchido(self):
        pessoa = create_complete_user(email="logada@exemplo.com")
        self.client.force_login(pessoa)
        html = self.client.get(reverse("ajuda:reportar")).content.decode()
        self.assertEqual(_campo(html, "email"), "logada@exemplo.com")

    def test_o_relato_vira_email_para_o_dono_com_reply_to_da_pessoa_e_os_dados_preenchidos(self):
        """Enviado pelo formulário RENDERIZADO, com CSRF de verdade: um nome de
        campo trocado no template derrubaria isto, e não um `post` de dicionário."""
        cliente = self.client_class(enforce_csrf_checks=True)
        html = cliente.get(reverse("ajuda:reportar") + "?de=/treino/").content.decode()
        resposta = cliente.post(reverse("ajuda:reportar"), {
            "csrfmiddlewaretoken": _csrf(html),
            "rota": _campo(html, "rota"),
            "versao": _campo(html, "versao"),
            "dispositivo": "Pixel 8, Chrome 130",
            "descricao": "Toquei em Concluir série e a página ficou em branco.",
            "email": "quem@exemplo.com",
            "site": "",
        })
        self.assertRedirects(resposta, reverse("ajuda:reportado"))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [SUPORTE])
        self.assertEqual(email.reply_to, ["quem@exemplo.com"])
        self.assertEqual(email.subject, "[NutriPlan] Problema em /treino/ · local")
        for trecho in ("Rota: /treino/", "Versão: local", "Aparelho: Pixel 8, Chrome 130",
                       "Quem: quem@exemplo.com", "Toquei em Concluir série"):
            self.assertIn(trecho, email.body)
        self.assertEqual(PedidoDeRecuperacao.objects.filter(tipo="ajd-ip").count(), 1)
        self.assertEqual(PedidoDeRecuperacao.objects.filter(tipo="ajd-glob").count(), 1)

    def test_logado_o_quem_e_a_conta_e_nao_o_campo(self):
        pessoa = create_complete_user(email="conta@exemplo.com")
        self.client.force_login(pessoa)
        self.client.post(reverse("ajuda:reportar"), {
            "descricao": "A água não somou quando toquei duas vezes.", "email": "",
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Quem: conta@exemplo.com", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].reply_to, [])

    def test_descricao_curta_reabre_o_formulario_com_erro_e_nao_manda_nada(self):
        resposta = self.client.post(reverse("ajuda:reportar"), {"descricao": "quebrou"})
        self.assertEqual(resposta.status_code, 400)
        self.assertIn('class="field__errors"', resposta.content.decode())
        self.assertEqual(mail.outbox, [])

    def test_o_pote_de_mel_preenchido_recebe_a_mesma_resposta_e_nao_manda_nada(self):
        resposta = self.client.post(reverse("ajuda:reportar"), {
            "descricao": "Compre agora o melhor produto do mercado!!!", "site": "http://spam",
        })
        self.assertRedirects(resposta, reverse("ajuda:reportado"))
        self.assertEqual(mail.outbox, [])
        self.assertFalse(PedidoDeRecuperacao.objects.filter(tipo__startswith="ajd").exists())

    def test_o_limite_por_ip_para_o_envio_sem_mudar_a_resposta(self):
        dados = {"descricao": "Um relato honesto com mais de dez letras."}
        for _ in range(LIMITE_POR_IP):
            self.client.post(reverse("ajuda:reportar"), dados)
        self.assertEqual(len(mail.outbox), LIMITE_POR_IP)
        resposta = self.client.post(reverse("ajuda:reportar"), dados)
        self.assertRedirects(resposta, reverse("ajuda:reportado"))
        self.assertEqual(len(mail.outbox), LIMITE_POR_IP, "o sexto não sai")

    def test_o_limite_global_vale_para_ips_diferentes(self):
        PedidoDeRecuperacao.objects.bulk_create([
            PedidoDeRecuperacao(tipo="ajd-glob", chave="__global__") for _ in range(LIMITE_GLOBAL)
        ])
        self.client.post(reverse("ajuda:reportar"), {"descricao": "Um relato honesto com mais de dez letras."},
                         REMOTE_ADDR="203.0.113.7")
        self.assertEqual(mail.outbox, [])

    def test_smtp_fora_do_ar_devolve_503_com_a_mensagem_e_nao_conta_no_limite(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=OSError("timeout")):
            resposta = self.client.post(reverse("ajuda:reportar"), {
                "descricao": "Um relato honesto com mais de dez letras.",
            })
        self.assertEqual(resposta.status_code, 503)
        self.assertIn("Não conseguimos enviar agora", resposta.content.decode())
        self.assertFalse(PedidoDeRecuperacao.objects.filter(tipo="ajd-ip").exists())


class OQueMudouTests(TestCase):
    TEXTO = (
        "# Título\n\nprosa solta\n\n"
        "## 2026-09-21\n\n- **Um.** Com `código` e <b>html</b>.\n- Dois.\n\n"
        "## 2026-09-20\n\n- Três.\n"
    )

    def test_o_leitor_separa_secoes_por_data_e_itens_por_linha(self):
        secoes = leitor.ler(self.TEXTO)
        self.assertEqual([s["data"] for s in secoes], [date(2026, 9, 21), date(2026, 9, 20)])
        self.assertEqual(len(secoes[0]["itens"]), 2)
        self.assertEqual(secoes[1]["itens"], ["Três."])

    def test_o_leitor_escapa_html_e_so_conhece_negrito_e_codigo(self):
        item = leitor.ler(self.TEXTO)[0]["itens"][0]
        self.assertEqual(item, "<strong>Um.</strong> Com <code>código</code> e &lt;b&gt;html&lt;/b&gt;.")

    def test_o_changelog_do_repositorio_tem_a_forma_esperada_e_o_mais_recente_primeiro(self):
        secoes = leitor.mudancas()
        self.assertGreaterEqual(len(secoes), 3)
        datas = [s["data"] for s in secoes]
        self.assertEqual(datas, sorted(datas, reverse=True), "o mais recente primeiro")
        self.assertEqual(len(datas), len(set(datas)), "uma seção por dia")
        for secao in secoes:
            self.assertTrue(secao["itens"], "seção %s sem item" % secao["data"])

    def test_a_tela_lista_as_datas_e_os_itens_do_arquivo(self):
        html = self.client.get(reverse("ajuda:mudancas")).content.decode()
        secoes = leitor.mudancas()
        self.assertIn('<time datetime="%s">' % secoes[0]["data"].isoformat(), html)
        self.assertIn("<li>%s</li>" % secoes[0]["itens"][0], html)
        self.assertEqual(html.count('class="card mudancas"'), len(secoes))
