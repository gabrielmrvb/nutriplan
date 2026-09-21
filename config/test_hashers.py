# -*- coding: utf-8 -*-
"""O hash da senha deixa de custar 3 s (auditoria de 20/09/2026).

Medido em produção: login certo 3,0–3,2 s de TTFB, senha errada 4,4–5,6 s,
cadastro 3,7 s — o PBKDF2-SHA256 de 1 000 000 iterações na CPU do Render
free. Argon2id (`argon2-cffi` em requirements) custa ≈ 0,05–0,15 s; o
PBKDF2 a 600 000 fica de reserva para o ambiente onde o Argon2 não importa
e para conferir as senhas antigas — que o Django regrava no login.
"""
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

    def test_a_senha_antiga_e_regravada_em_argon2_no_login(self):
        """Ninguém troca de senha: `check_password` com `setter` (o que
        `User.check_password` faz) regrava no hasher preferido quando o
        gravado não é ele. Só vale onde o Argon2 importa — é o caso do
        Render e, desde 20/09/2026, desta máquina."""
        if not argon2_disponivel():
            self.skipTest("argon2-cffi não importa neste ambiente")
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User(email="antiga@exemplo.com")
        hasher = PBKDF2SHA256Rapido()
        user.password = hasher.encode("segredo-forte-123", hasher.salt(), iterations=1_000_000)
        regravou = {}
        user.save = lambda *a, **k: regravou.setdefault("ok", True)  # sem banco
        self.assertTrue(user.check_password("segredo-forte-123"))
        self.assertTrue(user.password.startswith("argon2$"))
        self.assertTrue(regravou.get("ok"))

    def test_seiscentas_mil_iteracoes_e_o_piso_da_owasp(self):
        self.assertGreaterEqual(PBKDF2SHA256Rapido.iterations, 600_000)
        self.assertLess(PBKDF2SHA256Rapido.iterations, 1_000_000)
