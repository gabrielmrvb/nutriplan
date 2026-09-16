"""A vitrine é ferramenta de quem mantém: mesma permissão do painel, fora
da navegação, e a MESMA página nos dois regimes — a classe do regime vem do
servidor, nunca de `:has()` nem de JavaScript."""
from django.contrib.auth.models import Permission

from .tests import BaseDoPainel


class AcessoAVitrineTests(BaseDoPainel):
    def test_anonimo_vai_para_o_login(self):
        resposta = self.client.get("/gestao/vitrine/")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/entrar/", resposta["Location"])

    def test_usuario_comum_leva_403(self):
        self.client.force_login(self.pessoa("comum@exemplo.com"))
        self.assertEqual(self.client.get("/gestao/vitrine/").status_code, 403)

    def test_quem_tem_a_permissao_entra_mesmo_sem_ser_staff(self):
        pessoa = self.pessoa("curadora@exemplo.com")
        pessoa.user_permissions.add(Permission.objects.get(codename="ver_painel_de_gestao", content_type__app_label="accounts"))
        self.client.force_login(pessoa)
        self.assertEqual(self.client.get("/gestao/vitrine/").status_code, 200)


class RegimeDaVitrineTests(BaseDoPainel):
    def setUp(self):
        self.client.force_login(self.operador())

    def test_sem_parametro_e_mesa(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertNotIn('class="modo-foco', html)
        self.assertNotIn(' modo-foco"', html)
        self.assertIn("Vitrine · Mesa", html)

    def test_regime_ferro_escreve_a_classe_no_body(self):
        html = self.client.get("/gestao/vitrine/?regime=ferro").content.decode()
        self.assertIn("<body class=\"modo-foco", html)
        self.assertIn("Vitrine · Ferro", html)

    def test_regime_desconhecido_cai_em_mesa(self):
        html = self.client.get("/gestao/vitrine/?regime=roxo").content.decode()
        self.assertNotIn("modo-foco", html.split("<main", 1)[0])
        self.assertIn("Vitrine · Mesa", html)

    def test_a_vitrine_esta_fora_da_navegacao_e_do_cache(self):
        resposta = self.client.get("/gestao/vitrine/")
        html = resposta.content.decode()
        self.assertNotIn('class="tabbar"', html)
        self.assertIn("no-store", resposta["Cache-Control"])

    def test_o_formulario_com_erro_mostra_o_erro_junto_do_campo(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertIn("Informe um endereço de email válido", html)
