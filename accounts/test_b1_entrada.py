"""B1 — LOGIN / CADASTRO: o foco cai na primeira pergunta da tela.

`UserCreationForm.__init__` marca `autofocus` no `USERNAME_FIELD`. Neste projeto
o `USERNAME_FIELD` e o e-mail, e o cadastro pergunta o NOME primeiro — entao o
atributo nascia no segundo campo. Medido no navegador, contra producao: a ordem
de tabulacao comecava em `first_name` e o cursor estava em `email`. Quem chega e
comeca a digitar o nome escreve dentro do campo de e-mail.

O teste NAO fixa o nome do campo. Ele le a ordem dos campos como o navegador a
le e exige que o autofocus esteja no primeiro deles: se alguem reordenar o
formulario amanha, a regra continua valendo sem precisar ser reescrita — e um
teste que dissesse "first_name tem autofocus" passaria a proteger o campo errado
no dia da reordenacao.
"""
import re

from django.test import TestCase
from django.urls import reverse

#: Campos que a pessoa ve e tabula. `hidden` fica de fora: o CSRF e o `process`
#: do allauth aparecem no HTML antes de tudo e nao sao pergunta nenhuma.
CAMPO = re.compile(r'<input\b(?![^>]*type="hidden")[^>]*>', re.I)
NOME = re.compile(r'\bname="([^"]+)"')


def campos_na_ordem(html):
    return [(NOME.search(t).group(1), "autofocus" in t.lower())
            for t in CAMPO.findall(html) if NOME.search(t)]


class OFocoSegueAPrimeiraPerguntaTests(TestCase):
    def _campos(self, rota):
        html = self.client.get(reverse(rota), secure=True).content.decode()
        campos = campos_na_ordem(html)
        self.assertTrue(campos, "nenhum campo visivel em %s" % rota)
        return campos

    def test_no_cadastro_o_foco_cai_no_primeiro_campo(self):
        campos = self._campos("accounts:signup")

        com_foco = [n for n, foco in campos if foco]
        self.assertEqual(
            com_foco, [campos[0][0]],
            "ordem dos campos: %s" % [n for n, _ in campos],
        )

    def test_no_login_o_foco_cai_no_primeiro_campo(self):
        """Controle: o login sempre esteve certo, e precisa continuar.

        Sem ele, "consertar" o cadastro tirando o autofocus de todo lugar
        passaria no teste acima e pioraria a tela de entrar.
        """
        campos = self._campos("accounts:login")

        com_foco = [n for n, foco in campos if foco]
        self.assertEqual(com_foco, [campos[0][0]])

    def test_existe_exatamente_um_campo_com_foco(self):
        """Dois `autofocus` no mesmo documento deixam a escolha para o
        navegador, e navegadores diferentes escolhem diferente."""
        for rota in ("accounts:signup", "accounts:login"):
            with self.subTest(rota=rota):
                campos = self._campos(rota)
                self.assertEqual(len([1 for _, foco in campos if foco]), 1)

    def test_o_cadastro_ainda_pergunta_o_nome_antes_do_email(self):
        """O que torna o teste acima significativo.

        Se o formulario passasse a pedir o e-mail primeiro, autofocus no e-mail
        estaria CERTO — e os testes acima continuariam verdes sem que ninguem
        percebesse que a premissa mudou. Esta afirmacao trava a premissa.
        """
        campos = [n for n, _ in self._campos("accounts:signup")]

        self.assertLess(campos.index("first_name"), campos.index("email"))


class OErroDeLoginDizAVerdadeTests(TestCase):
    """A mensagem de credencial invalida precisa descrever ESTE app.

    O texto padrao do Django afirma que "ambos os campos diferenciam maiusculas
    e minusculas". Medido no navegador contra a stack real: o e-mail entra em
    caixa alta sem problema, porque `AUTHENTICATION_BACKENDS` tem o backend do
    allauth depois do `ModelBackend` e ele acha a conta sem diferenciar caixa.

    Mandar a pessoa conferir a caixa do e-mail quando o defeito esta na senha
    gasta a tentativa seguinte no lugar errado.
    """

    SENHA = "SenhaDeTeste-2026!"

    def _pessoa(self, email="caixa@exemplo.com"):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.create_user(email=email, password=self.SENHA)

    def test_o_email_realmente_nao_diferencia_caixa(self):
        """A PREMISSA da mensagem, medida e nao suposta.

        Se um dia o login passar a diferenciar caixa no e-mail, este teste cai
        primeiro — e a frase volta a ser revista antes de virar mentira.
        """
        self._pessoa("caixa@exemplo.com")

        entrou = self.client.login(
            username="CAIXA@EXEMPLO.COM", password=self.SENHA
        )

        self.assertTrue(entrou, "o e-mail deixou de ser insensivel a caixa")

    def test_a_senha_continua_diferenciando_caixa(self):
        """A outra metade da frase. Sem isto, a mensagem poderia estar errada
        no sentido oposto e o teste acima nao perceberia."""
        self._pessoa("senha@exemplo.com")

        self.assertFalse(
            self.client.login(username="senha@exemplo.com", password=self.SENHA.upper())
        )

    def test_a_tela_nao_manda_conferir_a_caixa_do_email(self):
        resposta = self.client.post(
            reverse("accounts:login"),
            {"username": "ninguem@exemplo.com", "password": "errada"},
            secure=True,
        )

        self.assertNotContains(resposta, "ambos os campos diferenciam")
        self.assertContains(resposta, "E-mail ou senha incorretos")

    def test_a_tela_diz_o_que_de_fato_diferencia(self):
        """Nao basta remover a frase errada: sem dizer nada, quem errou a
        maiuscula da senha fica sem pista nenhuma."""
        resposta = self.client.post(
            reverse("accounts:login"),
            {"username": "ninguem@exemplo.com", "password": "errada"},
            secure=True,
        )

        self.assertContains(resposta, "A senha diferencia maiúsculas")
