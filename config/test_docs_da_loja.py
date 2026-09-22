"""Os documentos de loja (`docs/loja/`) dizem a verdade sobre o app — e é
isso que os dois formulários de privacidade cobram (Fase 3 da missão
Capacitor, 22/09/2026).

Formulário que não bate com o app é motivo frequente de rejeição e de
remoção depois de publicado, então o que dá para conferir por código é
conferido aqui: as permissões de saúde declaradas, as URLs públicas que a
loja vai abrir, e a régua de linguagem do app (estimativa e cardápio de
exemplo, nunca "plano alimentar") valendo também na descrição da loja.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

RAIZ = Path(__file__).resolve().parent.parent
LOJA = RAIZ / "docs" / "loja"


class ADescricaoDaLojaObedeceARegráDeLinguagemTests(SimpleTestCase):
    def setUp(self):
        self.listagem = (LOJA / "listagem.md").read_text(encoding="utf-8")
        self.descricao = self.listagem[self.listagem.index("Pare de adivinhar"):self.listagem.index("## Novidades")]

    def test_a_loja_promete_estimativa_e_cardapio_de_exemplo(self):
        self.assertIn("estimativa", self.descricao.lower())
        self.assertIn("cardápio de exemplo", self.descricao.lower())

    def test_a_loja_nao_promete_plano_alimentar_nem_dieta_personalizada(self):
        """A mesma régua de `config/test_linguagem.py`, agora na vitrine:
        prescrição dietética é privativa do nutricionista (Lei 8.234/1991)."""
        for proibido in ("plano alimentar", "dieta personalizada", "sua dieta", "prescrição"):
            with self.subTest(proibido=proibido):
                self.assertNotIn(proibido, self.descricao.lower().replace("não é prescrição", ""))

    def test_a_loja_diz_o_que_o_app_nao_e(self):
        self.assertIn("não substitui nutricionista nem", self.descricao.lower())


class OsFormulariosBatemComOAppTests(SimpleTestCase):
    def setUp(self):
        self.formularios = (LOJA / "privacidade-das-lojas.md").read_text(encoding="utf-8")
        self.manifesto = (RAIZ / "nativo" / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")

    def test_as_permissoes_de_saude_justificadas_sao_as_declaradas(self):
        declaradas = set(re.findall(r'android\.permission\.health\.(\w+)" />', self.manifesto))
        removidas = set(re.findall(r'android\.permission\.health\.(\w+)" tools:node="remove"', self.manifesto))
        justificadas = set(re.findall(r"`(READ_\w+)`", self.formularios))
        self.assertEqual(declaradas - removidas, justificadas)

    def test_os_dois_formularios_negam_rastreamento_e_compartilhamento(self):
        self.assertIn("não rastreia", self.formularios.lower())
        self.assertIn("compartilhado com terceiros", self.formularios.lower())
        self.assertIn("não há publicidade", self.formularios.lower())

    def test_o_que_o_app_nao_le_esta_marcado_como_nao_coletado(self):
        """O app não lê GPS nem tem SDK de crash — e o formulário diz isso.
        Se um dia passar a ler, este teste é o lembrete de atualizar."""
        for linha in ("| Location |", "| Diagnostics › Crash/Performance |"):
            trecho = self.formularios[self.formularios.index(linha):][:120]
            self.assertIn("**Não**", trecho)
        js = (RAIZ / "static" / "js" / "nativo.js").read_text(encoding="utf-8")
        self.assertNotIn("Geolocation", js)


class AsUrlsQueAsLojasAbremExistemTests(TestCase):
    def test_privacidade_termos_e_ajuda_respondem_200_e_estao_na_listagem(self):
        listagem = (LOJA / "listagem.md").read_text(encoding="utf-8")
        for nome in ("privacidade", "termos", "ajuda:index"):
            rota = reverse(nome)
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)
                self.assertIn(rota, listagem)
