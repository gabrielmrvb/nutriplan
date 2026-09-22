"""Nada que a pessoa digitou se perde em silêncio (item 2 da missão de UX).

O relato do dono: enviar a etapa 2 ou o registro manual de corrida "derruba
a sessão sem aviso, descartando os dados". Nenhum POST do app faz logout
(`accounts/views.py:1539` é o único `logout()`, na tela de sair). Os dois
caminhos que PRODUZEM essa experiência, lidos no código e na doutrina do
service worker:

1. o 403 de CSRF: o token da página fica velho quando `login()` roda em
   outra aba (`rotate_token`) ou quando o worker serve a página do cache
   depois de um re-login (paciência de 3 s no cold start do Render) — e a
   resposta era a página inglesa do Django, "Forbidden (403)", sem caminho
   de volta;
2. a sessão expirada com o formulário aberto: o POST vira 302 para o
   login e o formulário nunca volta.

Duas defesas, e as duas têm teste: a página de 403 é nossa, em português,
e diz que o que foi digitado está guardado; e `pwa.js` ("RASCUNHO DO
FORMULÁRIO") guarda os campos dos formulários longos no aparelho enquanto
a pessoa digita e os devolve quando o mesmo formulário reabre vazio —
depois do 403, depois do login, depois de fechar o app no meio.
"""
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.test_tres_etapas import ETAPA1, etapa


class PaginaDe403Tests(TestCase):
    def test_o_403_de_csrf_fala_portugues_e_aponta_a_volta(self):
        cliente = Client(enforce_csrf_checks=True)
        user = User.objects.create_user(email="csrf@exemplo.com", password="senha-bem-forte-123")
        cliente.force_login(user)
        resposta = cliente.post(etapa(1), ETAPA1)
        self.assertEqual(resposta.status_code, 403)
        html = resposta.content.decode()
        self.assertNotIn("Forbidden", html)
        self.assertNotIn("CSRF verification failed", html)
        self.assertIn("não pôde ser confirmado", html)
        self.assertIn("ficou guardado", html)
        self.assertIn("history.back()", html)
        self.assertIn(reverse("plans:today"), html)


class RascunhoTests(SimpleTestCase):
    def test_o_pwa_guarda_e_devolve_o_que_foi_digitado(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        partes = js.split("RASCUNHO DO FORMULÁRIO", 1)
        self.assertEqual(len(partes), 2)
        bloco = partes[1][:6000]
        self.assertIn("[data-rascunho]", bloco)
        self.assertIn("localStorage", bloco)
        # senha nunca; token nunca; arquivo nunca
        self.assertIn('"password"', bloco)
        self.assertIn("csrfmiddlewaretoken", bloco)
        self.assertIn('"file"', bloco)
        # devolve só em campo VAZIO: o que o servidor reabriu preenchido manda
        self.assertIn("vazio", bloco)
        # e some quando o envio deu certo (a página seguinte é outra)
        self.assertIn("enviado", bloco)

    def test_os_formularios_longos_levam_a_marca(self):
        base = Path(settings.BASE_DIR) / "templates"
        for nome in ("accounts/onboarding/step.html", "workouts/corrida_form.html", "ajuda/reportar.html"):
            fonte = (base / nome).read_text(encoding="utf-8")
            self.assertIn("data-rascunho", fonte, nome)
