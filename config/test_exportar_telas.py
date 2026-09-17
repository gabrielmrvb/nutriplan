"""O exportador de telas serve à semente do Claude Design (spec de 15/09/2026).

Três mecânicas novas, e cada uma tem um motivo: a ENTRADA só existe para
quem não está logado (logado, `/conta/entrar/` redireciona para a Home — e a
semente ficaria sem a tela de entrada); a FICHA tem id na URL, que depende
da pessoa; e as seis telas da spec precisam estar na lista, com os nomes
que `scripts/montar_semente.py` procura.
"""
import importlib

from django.test import TestCase

from plans.tests import create_complete_user


def _modulo():
    # O módulo chama `django.setup()` no import; dentro da suíte isso é
    # inofensivo, e importar tarde evita custo em quem não roda este arquivo.
    return importlib.import_module("scripts.exportar_telas")


class ExportadorDeTelasTests(TestCase):
    SEIS = ("10-hoje", "11-treino-painel", "12-treino-ficha",
            "13-treino-execucao", "14-progresso", "15-entrada")

    def test_as_seis_telas_da_spec_estao_na_lista(self):
        nomes = [t["nome"] for t in _modulo().TELAS]
        for nome in self.SEIS:
            with self.subTest(nome=nome):
                self.assertIn(nome, nomes)

    def test_a_entrada_e_pedida_sem_sessao(self):
        """Logado, `/conta/entrar/` redireciona; a tela anônima não pode."""
        modulo = _modulo()
        usuario = create_complete_user("exporta@exemplo.com")
        entrada = next(t for t in modulo.TELAS if t["nome"] == "15-entrada")
        resposta, url_final = modulo.resposta_da_tela(entrada, usuario)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("/conta/entrar/", url_final)
        self.assertIn("Bom te ver de volta", resposta.content.decode())

    def test_uma_tela_logada_entra_com_a_pessoa(self):
        modulo = _modulo()
        usuario = create_complete_user("logada@exemplo.com")
        hoje = next(t for t in modulo.TELAS if t["nome"] == "10-hoje")
        resposta, url_final = modulo.resposta_da_tela(hoje, usuario)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("/conta/entrar/", url_final)

    def test_a_ficha_de_hoje_devolve_none_sem_plano_de_treino(self):
        """Sem sessão não há id; a tela é pulada com aviso, não estoura."""
        modulo = _modulo()
        usuario = create_complete_user("semficha@exemplo.com")
        self.assertIsNone(modulo.ficha_de_hoje(usuario))
