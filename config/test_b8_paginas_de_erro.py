# -*- coding: utf-8 -*-
"""B8 — as telas de erro passaram a ter porta.

A varredura visual do B8 mediu as telas alteradas de B1 a B7 e encontrou o
buraco fora delas: o projeto não tinha NENHUMA página de erro. Medido em
produção, `GET /rota-que-nao-existe/` devolvia 179 bytes da página embutida do
Django — em inglês, sem marca e sem um único link. Um app cuja regra é
`TodaTelaTemPortaTests` deixava sem saída justamente quem chegou no lugar
errado.

As três telas são alcançáveis de verdade:

  * 404 — link velho, endereço digitado errado, atalho salvo de rota que mudou;
  * 403 — quem é da equipe mas não tem `ver_painel_de_gestao`, cenário que o
    B5 já testa e exige que continue existindo;
  * 500 — a tela que aparece quando tudo o mais falhou.

A do 500 é a de regra diferente, e é onde este arquivo concentra o esforço.
"""
import re

from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views.defaults import server_error

from config.settings import BASE_DIR
from plans.tests import create_complete_user

TEMPLATES = BASE_DIR / "templates"

# Texto da página embutida do Django. Se ele reaparecer, o template do projeto
# deixou de ser encontrado — e o defeito volta calado.
TEXTO_DO_DJANGO = "The requested resource was not found on this server."

#: O cartão de cada tela. O do 500 tem nome próprio porque a tela é
#: autocontida e não usa as classes do `app.css`.
CARTAO = re.compile(r'<div class="(?:card center|caixa)">(.*?)</div>', re.S)


def portas_do_cartao(corpo):
    """Os links de saída DE DENTRO do cartão de erro.

    Ancorar no cartão não é preciosismo — foi a sabotagem que exigiu. A versão
    anterior destes testes procurava `href="/conta/entrar/"` no documento
    inteiro, e passava por causa do "Entrar" que o CABEÇALHO do `base.html`
    desenha para quem não tem sessão. Trocar o `{% url %}` da porta por um
    caminho escrito à mão e errado não derrubava teste nenhum.

    É a armadilha que o `CLAUDE.md` descreve: a asserção casava com uma string
    que também existe em outro lugar da página.
    """
    cartao = CARTAO.search(corpo)
    if cartao is None:
        return None
    return re.findall(r'<a class="btn[^"]*" href="([^"]+)"', cartao.group(1))


class OQueOQuatrocentosEQuatroMostraTests(TestCase):
    """A tela do 404, nos dois estados em que ela é alcançada."""

    def test_o_endereco_inexistente_usa_o_template_do_projeto(self):
        resposta = self.client.get("/rota-que-nao-existe/")

        self.assertEqual(resposta.status_code, 404)
        self.assertTemplateUsed(resposta, "404.html")
        self.assertNotContains(resposta, TEXTO_DO_DJANGO, status_code=404)

    def test_deslogado_a_porta_precisa_estar_no_corpo_da_pagina(self):
        """O caso que decidiu o desenho.

        Deslogado, o `base.html` não desenha barra de abas nenhuma — a asserção
        de baixo prova isso e é o que dá sentido à de cima. Se a porta fosse
        herdada da navegação, esta tela ficaria sem saída exatamente para quem
        chega por um link velho sem ter sessão.
        """
        corpo = self.client.get("/rota-que-nao-existe/").content.decode()

        self.assertNotIn('class="tabbar__item', corpo)
        self.assertEqual(portas_do_cartao(corpo), [reverse("accounts:login")])
        self.assertIn("Entrar no NutriPlan", corpo)

    def test_logado_a_porta_leva_para_o_dia_de_hoje(self):
        self.client.force_login(create_complete_user("perdido@exemplo.com"))

        corpo = self.client.get("/rota-que-nao-existe/").content.decode()

        self.assertEqual(portas_do_cartao(corpo), [reverse("plans:today")])
        self.assertIn("Ir para o dia de hoje", corpo)

    def test_a_tela_fala_portugues(self):
        """Não é preciosismo: a página do Django diz "Not Found" para um app
        inteiro em pt-BR, e quem lê conclui que quebrou, não que errou o
        endereço."""
        resposta = self.client.get("/rota-que-nao-existe/")

        self.assertContains(resposta, "Esta página não existe", status_code=404)


class OQueOQuatrocentosETresMostraTests(TestCase):
    """Pelo caminho REAL, e não por um `PermissionDenied` fabricado: quem é da
    equipe sem `ver_painel_de_gestao` leva 403 em /gestao/, e o B5 tem teste
    exigindo que seja assim."""

    def setUp(self):
        self.equipe = create_complete_user("equipe@exemplo.com")
        self.equipe.is_staff = True
        self.equipe.save(update_fields=["is_staff"])
        self.client.force_login(self.equipe)

    def test_staff_sem_a_permissao_ve_a_tela_do_projeto(self):
        resposta = self.client.get("/gestao/")

        self.assertEqual(resposta.status_code, 403)
        self.assertTemplateUsed(resposta, "403.html")
        self.assertContains(
            resposta, "Você não tem acesso a esta página", status_code=403
        )

    def test_o_403_tem_porta(self):
        corpo = self.client.get("/gestao/").content.decode()

        self.assertEqual(portas_do_cartao(corpo), [reverse("plans:today")])

    def test_quem_tem_a_permissao_continua_entrando(self):
        """Contra-controle. Sem ele, um 403 devolvido para TODO mundo passaria
        nos dois testes de cima e o painel estaria quebrado."""
        self.equipe.user_permissions.add(
            Permission.objects.get(
                codename="ver_painel_de_gestao", content_type__app_label="accounts"
            )
        )
        self.client.force_login(self.equipe)

        self.assertEqual(self.client.get("/gestao/").status_code, 200)


class OQuinhentosNaoPodeDependerDeNadaTests(TestCase):
    """A regra diferente, e o motivo de esta tela ser escrita à mão.

    `django.views.defaults.server_error` faz `template.render()` — sem request e
    sem context processors. A docstring dele diz "Context: None". Estender o
    `base.html` renderizaria `app_css_url` VAZIO, e o Django não reclamaria:
    variável desconhecida vira string vazia. Sairia uma tela sem estilo, e o
    defeito só apareceria no dia em que o servidor já estivesse quebrado.
    """

    def resposta(self):
        return server_error(RequestFactory().get("/"))

    def test_ela_renderiza_sem_request_e_sem_context_processors(self):
        resposta = self.resposta()

        self.assertEqual(resposta.status_code, 500)
        self.assertIn("O NutriPlan teve um problema", resposta.content.decode())

    def test_ela_nao_depende_da_folha_de_estilo(self):
        """A folha vem de um context processor que não roda aqui. Se um dia
        alguém trocar o `<style>` embutido por um `<link>`, a tela de erro passa
        a depender exatamente do que pode estar fora do ar."""
        corpo = self.resposta().content.decode()

        self.assertNotIn('<link rel="stylesheet"', corpo)
        self.assertIn("<style>", corpo)
        self.assertIn("#0d0f12", corpo)

    def test_nenhuma_variavel_ficou_por_resolver(self):
        """O modo de falhar deste projeto é silencioso: variável desconhecida
        some, e o `href` fica vazio sem erro nenhum. Aqui isso é asserção."""
        corpo = self.resposta().content.decode()

        self.assertNotIn("{{", corpo)
        self.assertNotIn("{%", corpo)
        self.assertIsNone(
            re.search(r'href=""', corpo), "a porta do 500 ficou sem destino"
        )

    def test_o_500_nao_estende_o_base(self):
        """Estrutural, e não estético: é a asserção que impede alguém de
        "padronizar" esta tela com as outras e reintroduzir a dependência de
        contexto que ela existe para não ter."""
        fonte = (TEMPLATES / "500.html").read_text(encoding="utf-8")

        self.assertNotIn("{% extends", fonte)

    def test_a_porta_do_500_e_um_alvo_de_44px(self):
        """A régua do projeto vale também na tela de erro."""
        fonte = (TEMPLATES / "500.html").read_text(encoding="utf-8")

        self.assertIn("min-height: 44px", fonte)


class AsTresTelasTemPortaTests(TestCase):
    """Uma asserção por tela, com o mesmo critério de `TodaTelaTemPortaTests`:
    existe um link de saída, e ele aponta para uma rota que resolve.

    A busca é ANCORADA NO CARTÃO de erro, e não na página inteira, porque
    contar `a.btn` no documento todo mede a coisa errada: medido no navegador,
    o cabeçalho do `base.html` desenha um "Criar conta" para quem está
    deslogado, e ele entraria na conta sem ser a saída que esta tela precisa
    ter.
    """

    def portas_do_cartao(self, corpo):
        portas = portas_do_cartao(corpo)
        self.assertIsNotNone(portas, "não achei o cartão de erro na página")
        return portas

    def test_toda_tela_de_erro_oferece_exatamente_uma_saida(self):
        self.client.force_login(create_complete_user("saida@exemplo.com"))

        for descricao, corpo in (
            ("404", self.client.get("/rota-que-nao-existe/").content.decode()),
            ("403", self.client.get("/gestao/").content.decode()),
            ("500", server_error(RequestFactory().get("/")).content.decode()),
        ):
            with self.subTest(tela=descricao):
                portas = self.portas_do_cartao(corpo)
                self.assertEqual(
                    len(portas), 1, "%s: portas encontradas=%r" % (descricao, portas)
                )
                self.assertTrue(portas[0].startswith("/"), portas[0])

    def test_o_404_deslogado_tambem_tem_saida_dentro_do_cartao(self):
        """O estado que motivou o desenho, e que o teste de cima não cobre:
        sem sessão não há barra de abas, então a saída do cartão é a única
        coisa entre a pessoa e uma tela sem porta."""
        corpo = self.client.get("/rota-que-nao-existe/").content.decode()

        self.assertEqual(self.portas_do_cartao(corpo), [reverse("accounts:login")])
