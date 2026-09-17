"""Dependência de QA que só existe no venv é dependência que some no próximo
computador. `pillow` e `websocket-client` entraram assim (15/09/2026), e o
teste passa a cobrar que o arquivo de requisitos de desenvolvimento os
declare — e que o ambiente que roda a suíte os tenha, lidos DO ARQUIVO."""
import re
from importlib import metadata
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ARQUIVO = Path(settings.BASE_DIR) / "requirements-dev.txt"


def _declarados(texto):
    nomes = []
    for linha in texto.splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha or linha.startswith("-r"):
            continue
        nomes.append(re.split(r"[<>=!~\[ ]", linha, 1)[0].lower())
    return nomes


class RequisitosDeDesenvolvimentoTests(SimpleTestCase):
    def test_o_arquivo_existe_e_puxa_o_de_producao(self):
        texto = ARQUIVO.read_text(encoding="utf-8")
        self.assertIn("-r requirements.txt", texto)

    def test_as_dependencias_de_qa_estao_declaradas(self):
        nomes = _declarados(ARQUIVO.read_text(encoding="utf-8"))
        for nome in ("pillow", "websocket-client"):
            with self.subTest(pacote=nome):
                self.assertIn(nome, nomes)

    def test_tudo_que_o_arquivo_declara_esta_instalado(self):
        """Lido do arquivo, não do ambiente: se alguém apagar uma linha, o
        teste continua cobrando o que o arquivo diz — e se alguém acrescentar
        um pacote sem instalar, o teste avisa antes de o script quebrar."""
        for nome in _declarados(ARQUIVO.read_text(encoding="utf-8")):
            with self.subTest(pacote=nome):
                metadata.version(nome)  # levanta PackageNotFoundError se faltar

    def test_pyflakes_nao_e_dependencia(self):
        """Estava no venv sem ninguém usar; o dono decidiu que sai dos dois
        lugares (arquivo e ambiente) em 16/09/2026."""
        self.assertNotIn("pyflakes", _declarados(ARQUIVO.read_text(encoding="utf-8")))
        with self.assertRaises(metadata.PackageNotFoundError):
            metadata.version("pyflakes")
