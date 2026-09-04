# -*- coding: utf-8 -*-
"""O allauth é motor. A interface é do NutriPlan.

`config/urls.py` monta a biblioteca pela metade de propósito: sem
`allauth.account.urls`, para não existirem duas telas de entrar. Mas três
telas dela continuavam chegando a uma pessoa de verdade:

  `login/cancelled/`   quem desiste do consentimento do Google
  `login/error/`       quando o `state` do OAuth não bate
  `/conta/social/`     ver e desvincular as contas conectadas

Medida com uma conta autenticada e um Google vinculado, antes da correção:
`/conta/social/` respondia 200 com 2.517 bytes, sem `app.css`, sem a navegação
e sem a marca, sob o título "Conexões de conta".

A rota NÃO foi escondida. Ver e desvincular o Google só existe ali — o perfil
não oferece nada disso —, então tirá-la do ar removeria a função junto. Só o
template mudou: a view continua sendo a do allauth, com o `DisconnectForm` e a
trava de `validate_disconnect`.
"""
import re

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import resolve, reverse

from plans.tests import create_complete_user

User = get_user_model()


class UmaTelaDeEntrarSoTests(TestCase):
    """O apelido `account_login` não pode ter criado uma segunda porta.

    Ele existe porque 25 lugares da biblioteca revertem esse nome por dentro, o
    `AccountMiddleware` instalado entre eles, e sem ele desistir do Google
    terminava em 500. Registrar um NOME é diferente de montar uma TELA — e é
    esta diferença que os dois testes abaixo cobram.
    """

    def test_o_nome_leva_ao_mesmo_endereco(self):
        self.assertEqual(reverse("account_login"), reverse("accounts:login"))

    def test_quem_atende_esse_endereco_e_a_view_do_nutriplan(self):
        """A prova que falta se o teste parar no `reverse`.

        Dois padrões apontam para `/conta/entrar/`: o de `accounts.urls` e o
        apelido. Se a resolução passasse a cair no apelido — ou pior, numa view
        da biblioteca —, `reverse` continuaria igual e a pessoa veria outra
        tela. Quem responde tem de ser a view do produto.
        """
        casada = resolve(reverse("accounts:login"))
        modulo = casada.func.view_class.__module__

        self.assertEqual(casada.func.view_class.__name__, "AppLoginView")
        self.assertTrue(
            modulo.startswith("accounts."),
            "quem atende /conta/entrar/ veio de %s" % modulo,
        )

    def test_a_tela_de_entrar_e_a_do_app(self):
        html = self.client.get(reverse("accounts:login")).content.decode()

        self.assertIn("app.css", html)
        self.assertIn("Entrar · NutriPlan", html)


class AsContasConectadasUsamAcaraDoProdutoTests(TestCase):
    """A tela existe, funciona, e agora se parece com o NutriPlan."""

    URL = "/conta/social/"

    def setUp(self):
        self.pessoa = create_complete_user("qa.conexoes@exemplo.com")
        self.conta = SocialAccount.objects.create(
            user=self.pessoa, provider="google", uid="uid-de-teste"
        )
        # CSRF ligado de propósito: o cliente padrão do Django não confere o
        # token, e sem isso um template que perdesse `{% csrf_token %}`
        # passaria verde. Foi o que a sabotagem S198 mostrou.
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.pessoa)

    def enviar_o_formulario_da_tela(self):
        """Manda o POST que a TELA monta, e não um dicionário inventado.

        `self.client.post(url, {"account": pk})` prova que a VIEW funciona — e
        ela é do allauth, já funcionava antes desta mudança. Com o nome do
        campo trocado no template, ou com o `csrf_token` removido, aquele
        teste continuava verde e a tela ficava quebrada: foi exatamente o que
        as sabotagens S197 e S198 mostraram.

        Aqui os campos saem do HTML renderizado, então o teste cai junto com o
        formulário.
        """
        html = self.client.get(self.URL).content.decode()
        formulario = re.search(
            r"<form method=\"post\" novalidate>(.*?)</form>", html, re.S
        )
        self.assertIsNotNone(formulario, "sumiu o formulário de desvincular")

        campos = {}
        for tag in re.findall(r"<input[^>]*>", formulario.group(1), re.S):
            atributos = dict(re.findall(r'(\w+)="([^"]*)"', tag))
            nome = atributos.get("name")
            if not nome:
                continue
            if atributos.get("type") == "radio" and "checked" not in tag:
                continue
            campos[nome] = atributos.get("value", "")

        return self.client.post(self.URL, campos)

    def com_senha(self):
        self._trocar(lambda p: p.set_password("uma-senha-bem-forte-123"))

    def sem_senha(self):
        self._trocar(lambda p: p.set_unusable_password())

    def _trocar(self, mudanca):
        """Mexer na senha invalida o `session_auth_hash`, e o cliente sai
        deslogado — o POST seguinte virava 302 para o login e o teste media o
        redirecionamento em vez da regra. Reautentica depois de mudar."""
        mudanca(self.pessoa)
        self.pessoa.save()
        self.client.force_login(self.pessoa)

    def test_a_tela_veste_o_app(self):
        html = self.client.get(self.URL).content.decode()

        self.assertIn("app.css", html)
        self.assertIn("Contas conectadas · NutriPlan", html)

    def test_e_nao_a_da_biblioteca(self):
        """O título e a frase do allauth, que a pessoa via antes."""
        html = self.client.get(self.URL).content.decode()

        self.assertNotIn("Conexões de conta", html)
        self.assertNotIn("contas de terceiros", html)

    def test_a_navegacao_do_app_continua_na_tela(self):
        """Sem ela a pessoa entrava num lugar de onde não dava para sair."""
        html = self.client.get(self.URL).content.decode()

        for aba in ("Dieta", "Treino", "Progresso", "Perfil"):
            with self.subTest(aba=aba):
                self.assertIn(aba, html)

    def test_desvincular_continua_funcionando(self):
        """A capability é o motivo de a rota continuar de pé.

        Se o override tivesse quebrado o formulário — nome de campo errado,
        CSRF fora, action trocada —, a tela ficaria bonita e inútil, e nenhum
        teste de aparência perceberia.
        """
        self.com_senha()

        resposta = self.enviar_o_formulario_da_tela()

        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(SocialAccount.objects.filter(pk=self.conta.pk).exists())

    def test_quem_nao_tem_senha_nao_consegue_se_trancar_para_fora(self):
        """A trava é do allauth (`validate_disconnect`), e o override não pode
        tê-la contornado: sem senha utilizável, desvincular o único Google
        deixaria a conta sem nenhum jeito de entrar."""
        self.sem_senha()

        resposta = self.enviar_o_formulario_da_tela()

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(SocialAccount.objects.filter(pk=self.conta.pk).exists())

    def test_o_erro_dessa_trava_aparece_na_tela(self):
        """Recusar em silêncio é pior que recusar: a pessoa clica, nada muda, e
        ela não sabe se salvou."""
        self.sem_senha()

        html = self.enviar_o_formulario_da_tela().content.decode()

        self.assertIn("field__errors", html)

    def test_conectar_outra_conta_continua_oferecido(self):
        """A terceira capability da tela da biblioteca.

        `process=connect` e não `login`: a pessoa já está autenticada, e o que
        ela pede é vincular. Com `login` o allauth trocaria a sessão em vez de
        acrescentar uma conta. A asserção é sobre o FORMULÁRIO inteiro, e não
        sobre a palavra "connect" solta na página — que aparece em comentário e
        passaria verde com o botão apagado.
        """
        html = self.client.get(self.URL).content.decode()

        formulario = re.search(
            r'<form[^>]*action="%s".*?</form>' % reverse("google_login"),
            html,
            re.S,
        )

        self.assertIsNotNone(formulario, "sumiu o formulário de conectar")
        self.assertIn('name="process" value="connect"', formulario.group(0))
        self.assertIn("csrfmiddlewaretoken", formulario.group(0))

    def test_anonimo_nao_ve_a_tela(self):
        self.client.logout()

        resposta = self.client.get(self.URL)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])
