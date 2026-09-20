# -*- coding: utf-8 -*-
"""PROTÓTIPO (auditoria 20/09/2026): o hash da senha deixa de custar 3 s."""
from django.conf import settings
from django.contrib.auth.hashers import check_password, get_hasher, identify_hasher, make_password
from django.test import SimpleTestCase

from config.hashers import PBKDF2SHA256Rapido, argon2_disponivel


class OHashDaSenhaTests(SimpleTestCase):
    def test_o_primeiro_hasher_e_argon2_quando_da_e_o_pbkdf2_rapido_quando_nao(self):
        primeiro = settings.PASSWORD_HASHERS[0]
        if argon2_disponivel():
            self.assertTrue(primeiro.endswith("Argon2PasswordHasher"))
        else:
            self.assertEqual(primeiro, "config.hashers.PBKDF2SHA256Rapido")

    def test_a_senha_gravada_com_um_milhao_continua_conferindo_e_pede_atualizacao(self):
        """Ninguém precisa trocar de senha: o algoritmo é o mesmo, o Django
        confere com as iterações gravadas e regrava no próximo login."""
        antiga = make_password("segredo-forte-123", hasher="pbkdf2_sha256")
        hasher = PBKDF2SHA256Rapido()
        velha = hasher.encode("segredo-forte-123", hasher.salt(), iterations=1_000_000)
        self.assertTrue(check_password("segredo-forte-123", velha))
        self.assertTrue(check_password("segredo-forte-123", antiga))
        self.assertTrue(hasher.must_update(velha))
        self.assertFalse(hasher.must_update(hasher.encode("x", hasher.salt())))

    def test_seiscentas_mil_iteracoes_e_o_piso_da_owasp(self):
        self.assertGreaterEqual(PBKDF2SHA256Rapido.iterations, 600_000)
        self.assertLess(PBKDF2SHA256Rapido.iterations, 1_000_000)
