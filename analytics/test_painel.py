"""O painel de analytics: acesso, orçamento de consultas (< 15 por tela) e CSV.

O orçamento é a régua que o dono pediu: cada tela abaixo de 15 consultas, e o
custo NÃO cresce com o volume (por isso o teste semeia e mede)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import papeis

from .models import Event

User = get_user_model()

TELAS = ["geral", "explorar", "funil", "retencao", "usuario"]


class BasePainel(TestCase):
    @classmethod
    def setUpTestData(cls):
        papeis.sincronizar_papeis()

    def operador(self):
        quem = User.objects.create_user(email="g@b.com", password="senha-bem-forte-123")
        quem.is_staff = True
        quem.save(update_fields=["is_staff"])
        quem.groups.add(Group.objects.get(name=papeis.ADMINISTRADORES))
        return quem

    _semente = 0

    def _semear(self, n=60):
        agora = timezone.now()
        BasePainel._semente += 1
        u = User.objects.create_user(
            email="semeado%d@b.com" % BasePainel._semente, password="senha-bem-forte-123"
        )
        for i in range(n):
            Event.objects.create(
                name="tela.vista" if i % 2 else "dieta.refeicao_registrada",
                ts=agora - timezone.timedelta(hours=i),
                anon_id="anon-%d" % (i % 7),
                user=u if i % 3 else None,
                route="/hoje/",
                props={"opcao": "almoço"} if i % 2 == 0 else {},
            )


class AcessoTests(BasePainel):
    def test_anonimo_vai_para_o_login(self):
        r = self.client.get(reverse("analytics_painel:geral"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/entrar", r["Location"])

    def test_logado_sem_permissao_leva_403(self):
        u = User.objects.create_user(email="qualquer@b.com", password="senha-bem-forte-123")
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse("analytics_painel:geral")).status_code, 403)

    def test_operador_abre_as_cinco_telas(self):
        self.client.force_login(self.operador())
        self._semear()
        for tela in TELAS:
            r = self.client.get(reverse("analytics_painel:" + tela))
            self.assertEqual(r.status_code, 200, tela)


class OrcamentoTests(BasePainel):
    def setUp(self):
        self.client.force_login(self.operador())
        self._semear()

    def test_cada_tela_fica_abaixo_de_quinze_consultas(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        alvos = {
            "geral": reverse("analytics_painel:geral"),
            "explorar": reverse("analytics_painel:explorar") + "?evento=dieta.refeicao_registrada&agrupar=opcao",
            "funil": reverse("analytics_painel:funil") + "?funil=onboarding",
            "retencao": reverse("analytics_painel:retencao"),
            "usuario": reverse("analytics_painel:usuario") + "?id=anon-1",
        }
        for nome, url in alvos.items():
            with self.subTest(tela=nome):
                with CaptureQueriesContext(connection) as ctx:
                    self.client.get(url)
                self.assertLessEqual(len(ctx), 15, "%s: %d consultas" % (nome, len(ctx)))

    def test_o_custo_nao_cresce_com_o_volume(self):
        """Semeia MUITO mais e mede de novo: o número tem de ser o mesmo."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        url = reverse("analytics_painel:geral")
        with CaptureQueriesContext(connection) as antes:
            self.client.get(url)
        self._semear(400)
        with CaptureQueriesContext(connection) as depois:
            self.client.get(url)
        self.assertEqual(len(antes.captured_queries), len(depois.captured_queries))


class CsvTests(BasePainel):
    def test_explorar_baixa_csv(self):
        self.client.force_login(self.operador())
        self._semear()
        r = self.client.get(
            reverse("analytics_painel:explorar") + "?evento=dieta.refeicao_registrada&agrupar=opcao&formato=csv"
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn(b"almo", r.content)  # o valor da propriedade no CSV
