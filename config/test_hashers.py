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

from config.hashers import Argon2Moderado, PBKDF2SHA256Rapido, argon2_disponivel


class OHashDaSenhaTests(SimpleTestCase):
    def test_o_primeiro_hasher_e_argon2_quando_da_e_o_pbkdf2_rapido_quando_nao(self):
        primeiro = settings.PASSWORD_HASHERS[0]
        if argon2_disponivel():
            self.assertEqual(primeiro, "config.hashers.Argon2Moderado")
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


class OArgon2ModeradoTests(SimpleTestCase):
    """m=32 MiB, t=2, p=1 (decisão do dono, 21/09/2026). Medido em produção com
    os parâmetros padrão do Django (m=100 MiB, p=8): o login custava 2,0–2,6 s
    no CPU do Render free — o Argon2 sozinho ~1,7 s, contra 0,30 s de um GET
    da mesma tela. A OWASP aceita a partir de m=19 MiB, t=2, p=1; 32 MiB é
    folga sobre o mínimo, não o mínimo."""

    def test_os_parametros_sao_os_da_decisao_e_nao_descem_do_piso_da_owasp(self):
        self.assertEqual((Argon2Moderado.memory_cost, Argon2Moderado.time_cost, Argon2Moderado.parallelism), (32 * 1024, 2, 1))
        self.assertGreaterEqual(Argon2Moderado.memory_cost, 19 * 1024)
        self.assertGreaterEqual(Argon2Moderado.time_cost, 2)

    def test_a_senha_gravada_com_os_parametros_padrao_confere_e_e_regravada(self):
        """Quem entrou entre 20 e 21/09 tem o hash com m=100 MiB/p=8: continua
        entrando (os parâmetros viajam no próprio hash) e o Django regrava
        com os novos no login seguinte — `must_update` compara parâmetros."""
        if not argon2_disponivel():
            self.skipTest("argon2-cffi não importa neste ambiente")
        from django.contrib.auth.hashers import Argon2PasswordHasher

        padrao = Argon2PasswordHasher()
        moderado = Argon2Moderado()
        antigo = padrao.encode("segredo-forte-123", padrao.salt())
        self.assertIn("m=102400,t=2,p=8", antigo)
        self.assertTrue(check_password("segredo-forte-123", antigo))
        self.assertTrue(moderado.must_update(antigo))
        novo = moderado.encode("segredo-forte-123", moderado.salt())
        self.assertIn("m=32768,t=2,p=1", novo)
        self.assertFalse(moderado.must_update(novo))
        self.assertTrue(check_password("segredo-forte-123", novo))
        self.assertIn("m=32768,t=2,p=1", make_password("segredo-forte-123"))
