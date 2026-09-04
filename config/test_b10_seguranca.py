# -*- coding: utf-8 -*-
"""B10 — as nove capacidades continuam fechadas, e a trava é independente.

O contrato do B10 lista nove coisas que não podem reabrir: `change_profile`,
`add_user`, senha de terceiros, `SocialToken`, `SocialApp`, `SocialAccount`,
`EmailAddress`, `WeightEntry` avulso e permissões amplas. E fecha com a regra
que dá nome ao bloco: "mudança visual não pode ressuscitar capability".

Auditado item a item, os nove já têm guardião — `MatrizDeCapabilityTests`,
`SenhaNaoAtravessaOAdminTests`, `EscaladaDePrivilegioNoUserAdminTests` e
`PedirNovaEscolhaDeDivisaoTests`. Este arquivo NÃO os repete por repetir; ele
fecha o buraco que sobra, e que é específico da forma como a proteção principal
foi escrita.

Cinco das nove são protegidas por UMA tabela, a `ALCANCE`. A tabela é o
contrato — está escrito lá, e é uma boa decisão. Mas a proteção e o valor
esperado moram no mesmo lugar, e isso foi MEDIDO, não suposto:

  * reabrindo só o Admin, a própria matriz pega — a tela passa a responder 403
    onde a tabela diz 404, e ela é mais forte do que eu tinha suposto;
  * reabrindo o Admin E ajustando a linha da tabela para 403, que é o movimento
    de quem "faz o teste passar", a matriz fica VERDE.

Aqui os nove nomes vêm do CONTRATO, e não da tabela. No segundo cenário este
arquivo fica vermelho — reabrir passou a exigir dois arquivos que discordam
entre si, que é a diferença entre uma trava e um lembrete.
"""
import io

from django.contrib.auth.models import Group
from django.test import TestCase

from accounts import papeis
from accounts.models import User
from config.settings import BASE_DIR

CONTRATO = BASE_DIR / "docs" / "premium-polish-b1-b11.md"


class AsNoveQueNaoPodemReabrirTests(TestCase):
    """Os nomes vêm do contrato; os números, do que o servidor responde.

    404 e 403 não são a mesma resposta, e a distinção é do projeto: 404 é "a
    tela não existe" e não depende de ninguém conceder permissão um dia; 403 é
    "existe e você não pode". Onde há segredo ou tomada de conta, o contrato
    exige 404 — e é o 404 que está asserido aqui.
    """

    #: (nome no contrato, rota, resposta exigida, o que se ganha ao reabrir)
    FECHADAS = (
        ("add_user", "/admin/accounts/user/add/", 403,
         "criar conta por dentro, fora do auto-serviço"),
        ("WeightEntry avulso", "/admin/accounts/weightentry/", 404,
         "peso de qualquer pessoa fora do contexto da conta"),
        ("EmailAddress", "/admin/account/emailaddress/", 404,
         "tomada de conta em dois passos: troca o e-mail, pede a senha"),
        ("SocialToken", "/admin/socialaccount/socialtoken/", 404,
         "token de acesso ao Google da pessoa"),
        ("SocialApp", "/admin/socialaccount/socialapp/", 404,
         "o segredo do app"),
        ("SocialAccount", "/admin/socialaccount/socialaccount/", 404,
         "extra_data é PII vinda do Google"),
        ("permissões amplas", "/admin/auth/group/add/", 403,
         "criar um papel com o que quiser dentro"),
    )

    @classmethod
    def setUpTestData(cls):
        papeis.sincronizar_papeis()

    def quem(self, email, papel):
        pessoa = User.objects.create_user(email=email, password="senha-bem-forte-123")
        pessoa.is_staff = True
        pessoa.save(update_fields=["is_staff"])
        pessoa.groups.add(Group.objects.get(name=papel))
        return pessoa

    def test_nenhum_papel_alcanca_as_nove(self):
        for papel in (papeis.ADMINISTRADORES, papeis.SUPORTE):
            pessoa = self.quem("b10-%s@exemplo.com" % papel.lower(), papel)
            self.client.force_login(pessoa)
            for nome, rota, esperado, ganho in self.FECHADAS:
                with self.subTest(papel=papel, capacidade=nome, ganho=ganho):
                    resposta = self.client.get(rota, secure=True)
                    self.assertEqual(resposta.status_code, esperado)

    def test_change_profile_continua_sem_dono(self):
        """A permissão genérica cobriria vinte campos para autorizar um. O
        projeto usa uma permissão dedicada, e esta asserção é o que impede
        alguém de "simplificar" voltando à genérica."""
        for papel in (papeis.ADMINISTRADORES, papeis.SUPORTE):
            pessoa = self.quem("b10-cp-%s@exemplo.com" % papel.lower(), papel)
            with self.subTest(papel=papel):
                self.assertFalse(pessoa.has_perm("accounts.change_profile"))

    def test_nenhum_papel_recebe_permissao_de_apagar(self):
        """Apagar conta é exclusão a pedido da pessoa, com fluxo próprio."""
        for papel in (papeis.ADMINISTRADORES, papeis.SUPORTE):
            with self.subTest(papel=papel):
                for permissao in papeis.permissoes_de(papel):
                    self.assertFalse(permissao.codename.startswith("delete_"))


class OContratoNaoEncolheEmSilencioTests(TestCase):
    """A lista de nove é a fonte, e uma fonte que some não faz barulho.

    Sem isto, apagar uma linha do contrato tornaria o teste de cima verde por
    ter menos o que provar — o mesmo modo de falha do guardrail apagado do B9.
    """

    NOMES = (
        "change_profile",
        "add_user",
        "senha de terceiros",
        "SocialToken",
        "SocialApp",
        "SocialAccount",
        "EmailAddress",
        "WeightEntry standalone",
        "permissões amplas",
    )

    def test_as_nove_continuam_escritas_no_contrato(self):
        texto = io.open(CONTRATO, encoding="utf-8").read()

        for nome in self.NOMES:
            with self.subTest(capacidade=nome):
                self.assertIn(nome, texto)


class MudancaVisualNaoRessuscitaCapabilityTests(TestCase):
    """A regra que fecha o bloco, aplicada à superfície visual mais nova.

    O B8 deu ao projeto uma tela de 403. Ela é renderizada pelo tratador do
    Django, então passou a aparecer TAMBÉM dentro do `/admin/` — e uma tela de
    erro que explica demais é vazamento: dizer qual permissão falta transforma
    "você não pode" em "peça exatamente isto a quem administra", e entrega o
    nome interno de graça.
    """

    @classmethod
    def setUpTestData(cls):
        papeis.sincronizar_papeis()

    def setUp(self):
        self.equipe = User.objects.create_user(
            email="b10-visual@exemplo.com", password="senha-bem-forte-123"
        )
        self.equipe.is_staff = True
        self.equipe.save(update_fields=["is_staff"])
        self.client.force_login(self.equipe)

    def test_a_tela_de_403_nao_diz_qual_permissao_falta(self):
        resposta = self.client.get("/gestao/", secure=True)
        corpo = resposta.content.decode()

        self.assertEqual(resposta.status_code, 403)
        for segredo in ("ver_painel_de_gestao", "accounts.ver_painel", "has_perm"):
            with self.subTest(vazamento=segredo):
                self.assertNotIn(segredo, corpo)

    def test_a_tela_de_403_nao_virou_uma_porta_para_dentro(self):
        """A saída leva para o dia de hoje, e não de volta para a área
        restrita: um botão que reenvia para /gestao/ seria um laço, e um botão
        para /admin/ seria a tela de erro sugerindo o caminho."""
        corpo = self.client.get("/gestao/", secure=True).content.decode()

        self.assertNotIn('<a class="btn btn--primary btn--block" href="/gestao/"', corpo)
        self.assertNotIn('<a class="btn btn--primary btn--block" href="/admin/', corpo)
