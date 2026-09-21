"""Bloco 1 — modelo e ingestão.

O que cada teste protege está na docstring dele. A regra que atravessa todos:
o cliente não é confiável, e o que ele manda passa por `ingest` antes de virar
linha.
"""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import DailyAggregate, Event

User = get_user_model()


def corpo(eventos, **contexto):
    base = {"session_id": "sess-1", "device": "mobile", "width": 390,
            "theme": "ferro", "pwa": False, "app_version": "abc1234"}
    base.update(contexto)
    base["events"] = eventos
    return json.dumps(base)


class IngestaoTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("analytics:ingest")

    def _post(self, dados, **extra):
        return self.client.post(self.url, data=dados,
                                content_type="text/plain", **extra)

    def test_o_lote_vira_linhas_com_o_contexto_aplicado(self):
        """O corpo em lote grava uma linha por evento, e o contexto do lote
        (aparelho, tema, versão) desce para cada uma."""
        r = self._post(corpo([
            {"name": "tela.vista", "route": "/hoje/"},
            {"name": "agua.registrada", "route": "/hidratacao/"},
        ]))
        self.assertEqual(r.status_code, 204)
        self.assertEqual(Event.objects.count(), 2)
        e = Event.objects.get(name="agua.registrada")
        self.assertEqual(e.route, "/hidratacao/")
        self.assertEqual(e.device, "mobile")
        self.assertEqual(e.theme, "ferro")
        self.assertEqual(e.app_version, "abc1234")

    def test_um_nome_fora_do_catalogo_nao_derruba_o_lote(self):
        """Nome inventado some; o resto do lote grava. Analytics aceita lixo do
        cliente e a taxonomia fechada é a defesa — mas um item ruim não pode
        custar os bons."""
        r = self._post(corpo([
            {"name": "treino.inciado"},          # erro de digitação
            {"name": "agua.registrada"},
        ]))
        self.assertEqual(r.status_code, 204)
        self.assertEqual([e.name for e in Event.objects.all()], ["agua.registrada"])

    def test_anonimo_por_padrao_e_o_cookie_e_de_primeira_parte(self):
        """Sem login, o evento não tem dono; o `anon_id` vem de um cookie
        HttpOnly sorteado no servidor."""
        r = self._post(corpo([{"name": "tela.vista"}]))
        e = Event.objects.get()
        self.assertIsNone(e.user)
        self.assertTrue(e.anon_id)
        cookie = r.cookies["np_aid"]
        self.assertEqual(cookie.value, e.anon_id)
        self.assertTrue(cookie["httponly"])

    def test_logado_atribui_a_pessoa(self):
        u = User.objects.create_user(email="a@b.com", password="senha-bem-forte-123")
        self.client.force_login(u)
        self._post(corpo([{"name": "agua.registrada"}]))
        self.assertEqual(Event.objects.get().user, u)

    def test_dnt_mantem_o_evento_anonimo_mesmo_logado(self):
        """`DNT: 1` não apaga o evento — ele continua contando no agregado —,
        mas não vira linha do tempo da pessoa."""
        u = User.objects.create_user(email="a@b.com", password="senha-bem-forte-123")
        self.client.force_login(u)
        self._post(corpo([{"name": "agua.registrada"}]), HTTP_DNT="1")
        e = Event.objects.get()
        self.assertIsNone(e.user)
        self.assertTrue(e.anon_id)  # ainda conta, anônimo

    def test_post_de_outra_origem_e_recusado(self):
        r = self._post(corpo([{"name": "tela.vista"}]),
                       HTTP_ORIGIN="https://roubo.example")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Event.objects.count(), 0)

    def test_timestamp_do_futuro_cai_para_agora(self):
        """Relógio adiantado escreveria no futuro, invisível para 'e hoje?'."""
        futuro = int((timezone.now() + timezone.timedelta(days=30)).timestamp() * 1000)  # 30 dias à frente
        self._post(corpo([{"name": "tela.vista", "ts": futuro}]))
        e = Event.objects.get()
        self.assertLess(e.ts, timezone.now() + timezone.timedelta(minutes=1))

    def test_corpo_quebrado_responde_204_sem_gravar(self):
        """Beacon não deve virar retentativa eterna: lixo é respondido com 204
        e some."""
        r = self._post("isto não é json {{{")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(Event.objects.count(), 0)

    def test_propriedade_aninhada_e_cortada(self):
        self._post(corpo([{"name": "dieta.refeicao_registrada",
                           "props": {"opcao": "almoço", "lixo": {"a": 1}}}]))
        e = Event.objects.get()
        self.assertEqual(e.props, {"opcao": "almoço"})

    def test_um_lote_grande_e_aparado_no_teto_do_lote(self):
        """Um lote não grava mais que MAX_EVENTOS_POR_LOTE — a defesa contra
        um cliente que despeja o buffer inteiro de uma vez."""
        from . import ingest
        muitos = [{"name": "tela.vista"} for _ in range(ingest.MAX_EVENTOS_POR_LOTE + 10)]
        self._post(corpo(muitos))
        self.assertEqual(Event.objects.count(), ingest.MAX_EVENTOS_POR_LOTE)

    def test_o_teto_da_janela_descarta_lotes_seguidos(self):
        """Vários lotes na mesma janela param no teto — o rate limit por
        sessão, best-effort no cache."""
        from . import ingest, views
        por_lote = ingest.MAX_EVENTOS_POR_LOTE
        lotes = (views.LIMITE_POR_JANELA // por_lote) + 3  # ultrapassa o teto
        for _ in range(lotes):
            self._post(corpo([{"name": "tela.vista"} for _ in range(por_lote)]))
        self.assertEqual(Event.objects.count(), views.LIMITE_POR_JANELA)


class AliasTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("analytics:ingest")

    def test_ao_entrar_o_historico_anonimo_vira_da_pessoa(self):
        """O funil 'abriu a landing (anônimo) → criou conta → treinou' precisa
        ser de UMA pessoa. O sinal `user_logged_in` (que todo login de verdade
        dispara) lê o cookie e costura o histórico anônimo à pessoa."""
        from django.contrib.auth.signals import user_logged_in
        from django.test import RequestFactory

        # Um toque anônimo, guardando o cookie que o servidor sorteou.
        self.client.post(self.url, data=corpo([{"name": "tela.vista"}]),
                         content_type="text/plain")
        anon = Event.objects.get().anon_id
        self.assertTrue(anon)

        u = User.objects.create_user(email="a@b.com", password="senha-bem-forte-123")
        req = RequestFactory().get("/")
        req.COOKIES["np_aid"] = anon
        user_logged_in.send(sender=User, request=req, user=u)

        self.assertEqual(Event.objects.get().user, u)

    def test_o_alias_nao_rouba_evento_de_outra_pessoa(self):
        outro = User.objects.create_user(email="o@b.com", password="senha-bem-forte-123")
        Event.objects.create(name="tela.vista", anon_id="aid-x", user=outro)
        from .identidade import alias
        novo = User.objects.create_user(email="n@b.com", password="senha-bem-forte-123")
        costurados = alias("aid-x", novo)
        self.assertEqual(costurados, 0)
        self.assertEqual(Event.objects.get().user, outro)


class WiringTests(TestCase):
    """A instrumentação automática só funciona se o `base.html` entregar o
    cliente e o endereço da ingestão. Um teste de VIEW (postar direto) não
    pega o dia em que o `{% url %}` ou o `<script>` somem do template."""

    def test_a_pagina_carrega_o_cliente_e_o_endereco_da_ingestao(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("NUTRIPLAN_ANALYTICS", html)
        self.assertIn(reverse("analytics:ingest"), html)
        self.assertIn("js/analytics", html)  # o <script src> do cliente


class EsquecerTests(TestCase):
    def test_excluir_a_conta_apaga_o_rastro_bruto_da_pessoa(self):
        """LGPD: o rastro identificado some. O agregado, que não guarda
        ninguém, fica."""
        u = User.objects.create_user(email="a@b.com", password="senha-bem-forte-123")
        Event.objects.create(name="treino.concluido", user=u, anon_id="aid-1")
        Event.objects.create(name="tela.vista", user=None, anon_id="aid-2")
        DailyAggregate.objects.create(day=timezone.now().date(), name="treino.concluido", count=9)

        u.delete()

        self.assertFalse(Event.objects.filter(name="treino.concluido").exists())
        self.assertTrue(Event.objects.filter(anon_id="aid-2").exists())  # anônimo fica
        self.assertEqual(DailyAggregate.objects.get().count, 9)  # agregado fica
