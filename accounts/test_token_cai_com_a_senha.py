# -*- coding: utf-8 -*-
"""Trocar a senha tem de derrubar o token de app.

`TokenDeApp` promete no docstring que "quem perde o telefone precisa que 'sair
de todos os aparelhos' funcione AGORA". Não funcionava: não existe endpoint
para isso, e a troca de senha — o que qualquer pessoa faz ao desconfiar de
invasão — não tocava nos tokens. Medido contra o servidor de desenvolvimento:
token emitido, senha trocada, `GET /api/v1/eu/` com o token antigo devolvendo
200, e mais 90 dias de validade pela frente.
"""
import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TokenDeApp, User


class ATrocaDeSenhaRevogaOsTokensTests(TestCase):
    def setUp(self):
        self.pessoa = User.objects.create_user(
            email="dono-do-telefone@exemplo.com", password="senha-bem-forte-123"
        )

    def _vivos(self):
        return TokenDeApp.objects.filter(
            user=self.pessoa, revogado_em__isnull=True
        ).count()

    def test_o_token_emitido_antes_para_de_valer_depois(self):
        registro, cru = TokenDeApp.emitir(self.pessoa)
        self.assertEqual(self._vivos(), 1)

        self.pessoa.set_password("outra-senha-bem-forte-456")
        self.pessoa.save()

        self.assertEqual(self._vivos(), 0)

    def test_o_token_antigo_deixa_de_autenticar_na_api(self):
        """O que importa não é a coluna: é a requisição parar de passar."""
        registro, cru = TokenDeApp.emitir(self.pessoa)
        cabecalho = {"HTTP_AUTHORIZATION": "Bearer " + cru}

        antes = self.client.get("/api/v1/eu/", **cabecalho)
        self.assertEqual(antes.status_code, 200)

        self.pessoa.set_password("outra-senha-bem-forte-456")
        self.pessoa.save()

        depois = self.client.get("/api/v1/eu/", **cabecalho)
        self.assertEqual(depois.status_code, 401)

    def test_o_token_de_OUTRA_pessoa_nao_e_afetado(self):
        """CONTROLE NEGATIVO: revogar demais seria derrubar todo mundo a cada
        troca de senha de qualquer um."""
        outra = User.objects.create_user(
            email="nao-e-comigo@exemplo.com", password="senha-bem-forte-123"
        )
        TokenDeApp.emitir(self.pessoa)
        TokenDeApp.emitir(outra)

        self.pessoa.set_password("outra-senha-bem-forte-456")
        self.pessoa.save()

        self.assertEqual(
            TokenDeApp.objects.filter(user=outra, revogado_em__isnull=True).count(), 1
        )

    def test_login_normal_nao_revoga_nada(self):
        """CONTROLE POSITIVO, e é o que impede a correção de virar um bug pior.

        Todo login grava `last_login` com `update_fields`, e um `save()` que
        revogasse ali derrubaria o token da pessoa toda vez que ela entrasse
        pelo site.
        """
        TokenDeApp.emitir(self.pessoa)

        self.client.login(username="dono-do-telefone@exemplo.com",
                          password="senha-bem-forte-123")

        self.assertEqual(self._vivos(), 1)

    def test_salvar_o_usuario_sem_mexer_na_senha_nao_revoga(self):
        """CONTROLE POSITIVO: mudar o nome não é motivo para deslogar o app."""
        TokenDeApp.emitir(self.pessoa)

        self.pessoa.first_name = "Nome Novo"
        self.pessoa.save()

        self.assertEqual(self._vivos(), 1)

    def test_a_tela_de_trocar_senha_derruba_o_token(self):
        """O caminho REAL da pessoa, e não só o modelo: o formulário do app."""
        registro, cru = TokenDeApp.emitir(self.pessoa)
        self.client.force_login(self.pessoa)

        resposta = self.client.post(
            reverse("accounts:password_change"),
            {"old_password": "senha-bem-forte-123",
             "new_password1": "outra-senha-bem-forte-456",
             "new_password2": "outra-senha-bem-forte-456"},
        )

        self.assertIn(resposta.status_code, (302, 200))
        self.assertEqual(self._vivos(), 0)
