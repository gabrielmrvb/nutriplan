"""A vitrine é ferramenta de quem mantém: mesma permissão do painel, fora
da navegação, e a MESMA página nos dois regimes — a classe do regime vem do
servidor, nunca de `:has()` nem de JavaScript."""
import os
from pathlib import Path

from django.conf import settings
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

    def test_sem_parametro_segue_o_sistema(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertNotIn('class="modo-foco', html)
        self.assertNotIn(' modo-foco"', html)
        self.assertIn("Vitrine · Sistema", html)

    def test_regime_ferro_escreve_a_classe_no_body(self):
        html = self.client.get("/gestao/vitrine/?regime=ferro").content.decode()
        self.assertIn('<html lang="pt-br" class="modo-foco">', html)
        self.assertIn("Vitrine · Ferro", html)

    def test_regime_desconhecido_cai_no_sistema(self):
        html = self.client.get("/gestao/vitrine/?regime=roxo").content.decode()
        self.assertNotIn("modo-foco", html.split("<main", 1)[0])
        self.assertIn("Vitrine · Sistema", html)

    def test_a_vitrine_esta_fora_da_navegacao_e_do_cache(self):
        resposta = self.client.get("/gestao/vitrine/")
        html = resposta.content.decode()
        self.assertNotIn('class="tabbar"', html)
        self.assertIn("no-store", resposta["Cache-Control"])

    def test_o_formulario_com_erro_mostra_o_erro_junto_do_campo(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertIn("Informe um endereço de email válido", html)


class CoberturaDaVitrineTests(BaseDoPainel):
    """Toda parcial de `templates/partials/` aparece na vitrine — lido do
    disco, para a nona parcial não nascer fora dela.

    `partials/marca.html` e `partials/_conquista.html` NÃO são incluídos de
    novo aqui: as duas bases (`templates/base.html`, cabeçalho e rodapé; e
    `templates/gestao/base.html`, cabeçalho do painel) já os incluem em TODA
    página. Incluir de novo na vitrine duplicaria o aviso de conquista — dois
    `<div data-conquista>` na mesma tela — e a marca no cabeçalho. Por isso a
    cobertura soma os três arquivos (vitrine + as duas bases), e não só o
    template da vitrine: a parcial pode estar coberta por herança, e a lista
    de parciais continua vindo do disco, não de uma lista escrita à mão.
    """

    def setUp(self):
        self.client.force_login(self.operador())
        self.template = (Path(settings.BASE_DIR) / "templates" / "gestao" / "vitrine.html").read_text(encoding="utf-8")
        self.base = (Path(settings.BASE_DIR) / "templates" / "base.html").read_text(encoding="utf-8")
        self.gestao_base = (Path(settings.BASE_DIR) / "templates" / "gestao" / "base.html").read_text(encoding="utf-8")

    def test_toda_parcial_e_incluida(self):
        pasta = Path(settings.BASE_DIR) / "templates" / "partials"
        faltando = [
            n
            for n in sorted(os.listdir(pasta))
            if n.endswith(".html")
            and f'"partials/{n}"' not in self.template
            and f'"partials/{n}"' not in self.base
            and f'"partials/{n}"' not in self.gestao_base
        ]
        self.assertEqual(faltando, [], f"parciais fora da vitrine: {faltando}")

    def test_os_componentes_de_css_estao_na_pagina(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        for classe in ('class="btn btn--primary"', "btn--ghost", "btn--quiet", "btn--perigo", "btn--sm", "btn--block",
                       'class="chip"', "chip--brand", "pill--brand", "pill--mute", 'class="tiles"', 'class="data-list"',
                       'class="empty-state"', 'class="hint"', "choice-cards", "conquista__titulo", "entrada__marca"):
            with self.subTest(classe=classe):
                self.assertIn(classe, html)

    def test_estados_do_campo(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertIn("Campo desabilitado.", html)
        # O campo de texto é o do sistema, não o `<input>` nu (17/09/2026).
        self.assertRegex(html, r'<input[^>]*name="nome"[^>]*class="field-input"')
        self.assertRegex(html, r'<input[^>]*name="email"[^>]*class="field-input"')
        self.assertIn("Informe um endereço de email válido", html)
        self.assertIn("Este campo é obrigatório", html)

    def test_conteudo_longo_e_quebrado_esta_previsto(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertIn("Supercalifragilisticexpialidocious", html)
        # O tile do maior valor real (dia pesado de treino) guarda o teto
        # prático de 5 dígitos — ver config.test_design_system.NumeroDoTileNaoQuebraNoMeioTests.
        self.assertIn("20000", html)
        self.assertIn("kg de volume", html)

    def test_nenhum_estilo_inline(self):
        self.assertNotIn('style="', self.template)
