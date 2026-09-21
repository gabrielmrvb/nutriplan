# -*- coding: utf-8 -*-
"""Logs estruturados e o alerta de 5xx (21/09/2026).

Três coisas, e o que cada teste prende:

* **a linha é JSON** fora de DEBUG, com `t`, `nivel`, `logger`, `pedido`,
  `msg`, os campos do pedido e `exc` redigido — uma URL de banco dentro de um
  traceback sai `[REDIGIDO]`, igual à linha de texto de sempre;
* **o log de acesso** diz a ROTA (o padrão da URL, nunca o caminho com token),
  o status, a duração e o USUÁRIO ANÔNIMO: hash estável com chave, 12 hex, que
  não é o id e muda de pessoa para pessoa — e que não custa consulta: em
  `/saude/vivo/` continua sendo zero;
* **o alerta de 5xx** conta numa janela deslizante, manda UM e-mail quando
  passa do limite, cala por 30 minutos, ignora 4xx, e o e-mail nomeia rota e
  identificador do pedido sem token nenhum. E está LIGADO no `LOGGING` de
  verdade: um 500 de verdade chega ao handler configurado.
"""
import json
import logging
from unittest import mock

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import path

from config import observabilidade as obs


def _registro(nome="nutriplan", nivel=logging.INFO, msg="oi", **extra):
    registro = logging.LogRecord(nome, nivel, __file__, 1, msg, (), None)
    for chave, valor in extra.items():
        setattr(registro, chave, valor)
    return registro


class ALinhaEJSONTests(SimpleTestCase):
    def test_uma_linha_um_objeto_com_os_campos_do_pedido(self):
        registro = _registro("nutriplan.acesso", msg="GET saude/vivo/ -> 200", pedido="abc123", rota="saude/vivo/",
                             metodo="GET", status=200, ms=12, usuario="anon")
        linha = json.loads(obs.FormatoJSON().format(registro))
        self.assertEqual(linha["logger"], "nutriplan.acesso")
        self.assertEqual(linha["pedido"], "abc123")
        self.assertEqual(linha["rota"], "saude/vivo/")
        self.assertEqual(linha["status"], 200)
        self.assertEqual(linha["ms"], 12)
        self.assertEqual(linha["usuario"], "anon")
        self.assertEqual(linha["nivel"], "INFO")
        self.assertRegex(linha["t"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00$")
        self.assertNotIn("exc", linha)

    def test_o_traceback_entra_redigido(self):
        try:
            raise RuntimeError("falhou em postgresql://usuario:senha@host/banco")
        except RuntimeError:
            import sys
            registro = _registro("django.request", logging.ERROR, "Internal Server Error: /conta/senha/nova/MQ/abc-def/")
            registro.exc_info = sys.exc_info()
        linha = json.loads(obs.FormatoJSON().format(registro))
        self.assertIn("RuntimeError", linha["exc"])
        self.assertNotIn("senha@host", linha["exc"])
        self.assertIn("[REDIGIDO]", linha["exc"])
        self.assertNotIn("abc-def", linha["msg"])

    def test_fora_de_debug_o_console_e_json_e_em_debug_e_texto(self):
        self.assertEqual(obs.configuracao(False)["handlers"]["console"]["formatter"], "json")
        self.assertEqual(obs.configuracao(True)["handlers"]["console"]["formatter"], "nutriplan")
        self.assertEqual(obs.configuracao(True, json_=True)["handlers"]["console"]["formatter"], "json")


def _explode(request):
    raise RuntimeError("boom de teste")


def _ok(request, **kwargs):
    return HttpResponse("ok")


urlpatterns = [
    path("explode/", _explode, name="explode"),
    path("plana/<int:n>/", _ok, name="plana"),
    path("saude/vivo/", _ok, name="vivo"),
]


@override_settings(ROOT_URLCONF=__name__)
class OLogDeAcessoTests(TestCase):
    def test_registra_rota_status_duracao_e_anonimo(self):
        with self.assertLogs("nutriplan.acesso", "INFO") as capturado:
            resposta = self.client.get("/plana/7/")
        self.assertEqual(resposta.status_code, 200)
        registro = capturado.records[-1]
        self.assertEqual(registro.rota, "plana/<int:n>/", "a ROTA, e não /plana/7/")
        self.assertEqual(registro.status, 200)
        self.assertEqual(registro.metodo, "GET")
        self.assertIsInstance(registro.ms, int)
        self.assertIn(registro.usuario, ("anon", "-"))

    def test_o_usuario_e_um_hash_estavel_com_chave_e_nao_o_id(self):
        Usuario = get_user_model()
        a = Usuario.objects.create_user(email="a@exemplo.com", password="x")
        b = Usuario.objects.create_user(email="b@exemplo.com", password="x")
        fabrica = RequestFactory()
        pedido = fabrica.get("/plana/1/")
        pedido.user = a
        um = obs.usuario_anonimo(pedido)
        self.assertRegex(um, r"^[0-9a-f]{12}$")
        self.assertNotEqual(um, str(a.pk))
        self.assertEqual(um, obs.usuario_anonimo(pedido), "estável")
        pedido.user = b
        outro = obs.usuario_anonimo(pedido)
        self.assertNotEqual(um, outro, "muda de pessoa para pessoa")
        with override_settings(SECRET_KEY="outra-chave-" * 5):
            self.assertNotEqual(outro, obs.usuario_anonimo(pedido), "a MESMA pessoa com outra chave é outro hash: sem a chave não se volta ao id")

    def test_o_usuario_nao_custa_consulta_quando_a_view_nao_o_leu(self):
        with self.assertNumQueries(0):
            with self.assertLogs("nutriplan.acesso", "INFO") as capturado:
                self.client.get("/saude/vivo/")
        self.assertEqual(capturado.records[-1].usuario, "-")



class OLogDeAcessoNoAppDeVerdadeTests(TestCase):
    """Com a URLconf real: o 404 renderiza a página de sempre."""

    def test_estatico_nao_entra(self):
        with self.assertNoLogs("nutriplan.acesso", "INFO"):
            self.client.get("/static/css/app.css")

    def test_a_rota_de_caminho_nao_resolvido_e_redigida(self):
        with self.assertLogs("nutriplan.acesso", "INFO") as capturado:
            resposta = self.client.get("/conta/senha/nova/MQ/token-secreto/nao-existe/")
        self.assertEqual(resposta.status_code, 404)
        self.assertNotIn("token-secreto", capturado.records[-1].rota)
        self.assertEqual(capturado.records[-1].status, 404)


class OAlertaDe5xxTests(SimpleTestCase):
    def _handler(self):
        enviados = []
        relogio = {"agora": 1000.0}
        handler = obs.AlertaDe5xx(limite=3, janela=300, silencio=1800, enviar=lambda a, c: enviados.append((a, c)), relogio=lambda: relogio["agora"])
        return handler, enviados, relogio

    def _erro(self, handler, msg="Internal Server Error: /treino/", pedido="p1", status=500):
        handler.emit(_registro("django.request", logging.ERROR, msg, pedido=pedido, status_code=status))

    def test_ate_o_limite_nada_e_no_seguinte_um_email_so(self):
        handler, enviados, relogio = self._handler()
        for i in range(3):
            self._erro(handler, pedido="p%d" % i)
        self.assertEqual(enviados, [])
        self._erro(handler, pedido="p3")
        self.assertEqual(len(enviados), 1)
        assunto, corpo = enviados[0]
        self.assertIn("4 erros 5xx em 5 min", assunto)
        self.assertIn("/treino/", corpo)
        self.assertIn("[pedido p3]", corpo)
        self.assertIn("scripts/incidente.py diagnostico", corpo)
        for i in range(10):
            self._erro(handler)
        self.assertEqual(len(enviados), 1, "silêncio de 30 min: uma rajada é UM e-mail")

    def test_depois_do_silencio_alerta_de_novo(self):
        handler, enviados, relogio = self._handler()
        for _ in range(4):
            self._erro(handler)
        relogio["agora"] += 1801
        for _ in range(4):
            self._erro(handler)
        self.assertEqual(len(enviados), 2)

    def test_a_janela_desliza(self):
        handler, enviados, relogio = self._handler()
        for _ in range(3):
            self._erro(handler)
        relogio["agora"] += 301
        self._erro(handler)
        self.assertEqual(enviados, [], "os três antigos saíram da janela: é o primeiro de novo")

    def test_4xx_nao_conta(self):
        handler, enviados, _ = self._handler()
        for _ in range(10):
            self._erro(handler, status=404)
        self.assertEqual(enviados, [])
        self.assertEqual(len(handler.erros), 0)

    def test_o_email_nao_carrega_token(self):
        handler, enviados, _ = self._handler()
        for _ in range(4):
            self._erro(handler, msg="Internal Server Error: /conta/senha/nova/MQ/token-valido/")
        self.assertNotIn("token-valido", enviados[0][1])
        self.assertIn("[REDIGIDO]", enviados[0][1])

    def test_sem_destinatario_so_avisa_no_log(self):
        with override_settings(NUTRIPLAN_ALERTA_EMAIL=""):
            with self.assertLogs("nutriplan", "WARNING") as capturado:
                self.assertFalse(obs._enviar_email("assunto", "corpo"))
        self.assertIn("NUTRIPLAN_ALERTA_EMAIL", capturado.output[0])

    def test_com_destinatario_manda_pelo_smtp_configurado(self):
        with override_settings(NUTRIPLAN_ALERTA_EMAIL="dona@exemplo.com", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            from django.core import mail
            self.assertTrue(obs._enviar_email("[NutriPlan] 4 erros 5xx em 5 min", "corpo"))
            self.assertEqual(mail.outbox[-1].to, ["dona@exemplo.com"])
            self.assertIn("5xx", mail.outbox[-1].subject)


@override_settings(ROOT_URLCONF=__name__)
class OAlertaEstaLigadoDeVerdadeTests(TestCase):
    def test_um_500_de_verdade_chega_ao_handler_configurado(self):
        handlers = [h for h in logging.getLogger("django.request").handlers if isinstance(h, obs.AlertaDe5xx)]
        self.assertEqual(len(handlers), 1, "o LOGGING de verdade tem o AlertaDe5xx no django.request")
        handler = handlers[0]
        enviados = []
        with mock.patch.object(handler, "enviar", lambda a, c: enviados.append((a, c))), \
                mock.patch.object(handler, "limite", 0), mock.patch.object(handler, "ultimo_alerta", None), \
                mock.patch.object(handler, "erros", handler.erros.__class__()):
            self.client.raise_request_exception = False
            resposta = self.client.get("/explode/")
        self.assertEqual(resposta.status_code, 500)
        self.assertEqual(len(enviados), 1)
        self.assertIn("/explode/", enviados[0][1])
        self.assertRegex(enviados[0][1], r"\[pedido [0-9a-f]{12}\]", "o identificador do pedido viaja no e-mail")

    def test_o_settings_liga_json_fora_de_debug_e_desliga_o_acesso_na_suite(self):
        from django.conf import settings
        self.assertFalse(settings.NUTRIPLAN_LOG_ACESSO, "manage.py test: o log de acesso fica em WARNING")
        self.assertEqual(settings.LOGGING["loggers"]["nutriplan.acesso"]["level"], "WARNING")
        self.assertIn("alerta_5xx", settings.LOGGING["loggers"]["django.request"]["handlers"])
