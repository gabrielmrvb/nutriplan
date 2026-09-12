# -*- coding: utf-8 -*-
"""O freemium tem um lugar só, e ele funciona antes de existir cobrança.

Os testes de `PermissionDenied` usam uma view de TESTE, roteada num URLconf
próprio: nenhum recurso do produto é Pro hoje (`RECURSOS_PRO` está vazio de
propósito), e gatear uma função real só para provar o mecanismo seria tirar
de quem usa. A prova vale do mesmo jeito — é o mesmo mixin, o mesmo
`dispatch` e a mesma resposta que uma view real teria.
"""
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import path, reverse
from django.views import View

from accounts import gates
from accounts.models import Profile, User
from accounts.gates import ExigeRecurso, Plano, Recurso, plano_de, recursos_de, tem_acesso


class _ViewPro(ExigeRecurso, View):
    recurso = Recurso.EXPORTACAO

    def get(self, request):
        return HttpResponse("dado pro")

    def post(self, request):
        return HttpResponse("executou")


class _ViewSemRecurso(ExigeRecurso, View):
    def get(self, request):
        return HttpResponse("nunca")


from config.urls import urlpatterns as _projeto  # noqa: E402

# As rotas do projeto entram junto: a página de 403 herda de `base.html`, que
# reverte `manifest`, `sw.js` e a barra — sem elas o 403 estouraria em
# `NoReverseMatch` e o teste mediria a fixture, não o gate.
urlpatterns = [
    path("teste/pro/", _ViewPro.as_view(), name="teste_pro"),
    path("teste/sem/", _ViewSemRecurso.as_view(), name="teste_sem"),
] + list(_projeto)


def _pessoa(email, plano=Plano.GRATIS):
    from datetime import date, time

    from accounts.models import ActivityLevel, Goal, Sex

    user = User.objects.create_user(email=email, password="senha-bem-forte-123")
    Profile.objects.create(
        user=user, sex=Sex.MALE, birth_date=date(1995, 4, 12), height_cm=178,
        activity_level=ActivityLevel.LIGHT, goal=Goal.CUT,
        wake_time=time(7, 0), sleep_time=time(23, 0), plano=plano,
    )
    return user


class OPlanoNasceGratisTests(TestCase):
    def test_perfil_novo_e_gratis(self):
        self.assertEqual(plano_de(_pessoa("g@exemplo.com")), Plano.GRATIS)

    def test_sem_perfil_e_sem_login_e_gratis(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(plano_de(AnonymousUser()), Plano.GRATIS)
        self.assertEqual(plano_de(None), Plano.GRATIS)

    def test_o_pro_e_escrito_no_perfil_e_lido_de_la(self):
        self.assertEqual(plano_de(_pessoa("p@exemplo.com", Plano.PRO)), Plano.PRO)


class NadaEProHojeTests(TestCase):
    """A arquitetura entra antes da primeira cobrança: cobrar o que hoje é de
    todo mundo seria tirar, não vender (§37)."""

    def test_o_conjunto_pro_esta_vazio_e_isso_e_decisao(self):
        self.assertEqual(gates.RECURSOS_PRO, frozenset())

    def test_gratis_alcanca_todo_recurso(self):
        u = _pessoa("livre@exemplo.com")
        for r in Recurso:
            with self.subTest(recurso=r):
                self.assertTrue(tem_acesso(u, r))
        self.assertTrue(all(recursos_de(u).values()))


@mock.patch.object(gates, "RECURSOS_PRO", frozenset({Recurso.EXPORTACAO}))
@override_settings(ROOT_URLCONF="accounts.test_gates")
class QuandoUmRecursoVirarProTests(TestCase):
    """O que acontece no dia em que alguém mover um recurso para `RECURSOS_PRO`
    — provado hoje, com o conjunto trocado só dentro destes testes."""

    def test_gratis_perde_so_aquele_recurso(self):
        u = _pessoa("g2@exemplo.com")
        self.assertFalse(tem_acesso(u, Recurso.EXPORTACAO))
        self.assertTrue(tem_acesso(u, Recurso.ANALISES))
        self.assertFalse(recursos_de(u)["exportacao"])

    def test_pro_alcanca(self):
        self.assertTrue(tem_acesso(_pessoa("p2@exemplo.com", Plano.PRO), Recurso.EXPORTACAO))

    def test_a_rota_pro_recusa_gratis_por_GET_e_por_POST(self):
        """§76: "como usuário Free pode acessar Pro diretamente por POST/URL?"
        Não pode — e a recusa é 403 SEM executar, não um redirecionamento
        depois de executar."""
        self.client.force_login(_pessoa("g3@exemplo.com"))
        self.assertEqual(self.client.get(reverse("teste_pro")).status_code, 403)
        resposta = self.client.post(reverse("teste_pro"))
        self.assertEqual(resposta.status_code, 403)
        self.assertNotIn(b"executou", resposta.content)

    def test_a_rota_pro_atende_pro(self):
        self.client.force_login(_pessoa("p3@exemplo.com", Plano.PRO))
        self.assertEqual(self.client.get(reverse("teste_pro")).content, b"dado pro")

    def test_view_que_esquece_o_recurso_estoura_e_nao_libera(self):
        """Mixin sem `recurso` é bug de configuração; o pior resultado seria
        liberar em silêncio."""
        self.client.force_login(_pessoa("p4@exemplo.com", Plano.PRO))
        with self.assertRaises(ValueError):
            self.client.get(reverse("teste_sem"))


class ADecisaoMoraNumLugarSoTests(TestCase):
    def test_nome_de_recurso_desconhecido_levanta_em_vez_de_negar(self):
        with self.assertRaises(ValueError):
            tem_acesso(_pessoa("x@exemplo.com"), "exportar-tudo")

    def test_nenhum_template_ou_view_decide_por_conta_propria(self):
        """`if perfil.plano == "pro"` fora de `gates.py` é a segunda cópia da
        regra, e a segunda cópia é a que envelhece."""
        raiz = Path(settings.BASE_DIR)
        suspeitos = []
        for pasta in ("templates", "accounts", "plans", "workouts", "push", "achievements", "demo", "config"):
            for arquivo in (raiz / pasta).rglob("*"):
                if arquivo.suffix not in (".html", ".py") or arquivo.name in ("gates.py", "test_gates.py"):
                    continue
                if "migrations" in arquivo.parts:
                    continue
                texto = arquivo.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"""plano\s*==\s*["']pro["']|\.plano\s*==\s*Plano\.PRO|is_pro\b""", texto):
                    suspeitos.append(arquivo.relative_to(raiz).as_posix())
        self.assertEqual(suspeitos, [])

    def test_o_context_processor_entrega_os_recursos_ao_template(self):
        from accounts.context_processors import freemium

        class Pedido:
            user = _pessoa("cp@exemplo.com")

        contexto = freemium(Pedido())
        self.assertEqual(set(dict(contexto["recursos"])), {r.value for r in Recurso})
        self.assertEqual(str(contexto["plano"]), Plano.GRATIS)

    def test_o_context_processor_nao_custa_consulta_se_ninguem_perguntar(self):
        """Ele roda em TODA resposta; um `user.profile` aqui seria +1 em todas
        as telas. `OCustoDaTelaDeAreasEstaMedidoTests` pegou isso na primeira
        versão, e a preguiça é a correção."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from accounts.context_processors import freemium

        class Pedido:
            user = _pessoa("lazy@exemplo.com")

        Pedido.user = User.objects.get(pk=Pedido.user.pk)  # sem perfil em cache
        with CaptureQueriesContext(connection) as consultas:
            freemium(Pedido())
        self.assertEqual(len(consultas), 0)
