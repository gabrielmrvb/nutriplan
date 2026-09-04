# -*- coding: utf-8 -*-
"""INFRA SAFETY P0 — as travas do backup, executadas e não lidas.

A auditoria desta fase encontrou máquina de backup pronta e bem escrita, e três
buracos em volta dela:

  * `backup.sh` grava na pasta atual quando ninguém diz outra coisa, o
    `.gitignore` não cobria `*.dump`, e este repositório é PÚBLICO. Uma
    execução a partir da raiz deixava dado de saúde a um `git add -A` de
    distância da internet — e o `.gitignore` deste projeto registra DUAS vezes
    em que um `git add -A` trouxe uma pasta inteira que não era para vir;
  * o fluxo do GitHub cifrava o dump e nunca abria o resultado. O projeto já
    exige que o dump seja LIDO de volta antes de dizer "OK"; a camada de
    criptografia não tinha a mesma exigência;
  * quatro dos cinco backups existentes nesta máquina estão em PGDMP 1.16 e o
    `pg_restore` do PATH é 16.9. O restore morria com "unsupported version",
    frase que não diz o que fazer e que aparece no pior dia possível.

Os testes aqui RODAM os scripts. Asserção sobre o texto de um script prova que
a linha existe, não que ela funciona — e a diferença entre as duas é o defeito
do arquivo de zero byte que já aconteceu neste projeto.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from config.settings import BASE_DIR

RAIZ = Path(BASE_DIR)
SCRIPTS = RAIZ / "scripts"
FLUXO = RAIZ / ".github" / "workflows" / "backup.yml"

BASH = shutil.which("bash")
GPG = shutil.which("gpg")
GIT = shutil.which("git")

sem_bash = unittest.skipUnless(BASH, "bash não está disponível")
sem_gpg = unittest.skipUnless(GPG and BASH, "gpg ou bash não disponíveis")
sem_git = unittest.skipUnless(GIT, "git não está disponível")


#: Onde mora o cliente PostgreSQL nesta máquina. Os scripts o procuram no PATH,
#: e o processo de teste do Django não o tem — sem isto os testes mediriam a
#: ausência do binário em vez da trava que vieram medir.
CLIENTE_PG = Path.home() / "pgsql" / "bin"


def posix(caminho):
    """Bash no Windows não entende caminho de Windows com contrabarra.

    O `tempfile` do Python devolve exatamente isso, e o script recebia um
    caminho que não existia para ele. A falha era confusa: o script parecia
    quebrado, e o quebrado era o teste.
    """
    return str(caminho).replace("\\", "/")


def rodar(script, *args, **ambiente):
    """Executa um script do projeto e devolve (codigo, saida+erro)."""
    env = dict(os.environ)
    if CLIENTE_PG.is_dir():
        env["PATH"] = posix(CLIENTE_PG) + os.pathsep + env.get("PATH", "")
    env.update({k: v for k, v in ambiente.items() if v is not None})
    for k, v in ambiente.items():
        if v is None:
            env.pop(k, None)
    p = subprocess.run(
        [BASH, posix(SCRIPTS / script), *[posix(a) for a in args]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(RAIZ),
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


@sem_bash
class ODumpNaoPodeNascerDentroDoRepositorioTests(SimpleTestCase):
    """O repositório é público, e um dump é dado de saúde de gente real.

    A trava é o script perguntar ao git se o destino está sob controle de
    versão — e não o `.gitignore`, que protege quem não digitou `git add -f` e
    não protege quem grava numa pasta que a regra não previu.
    """

    def test_gravar_na_raiz_do_repositorio_e_recusado(self):
        codigo, saida = rodar(
            "backup.sh", ".", DATABASE_URL="postgres://nao-vai-conectar/x"
        )

        self.assertEqual(codigo, 1, saida)
        self.assertIn("dentro de um repositório git", saida)

    def test_a_recusa_acontece_ANTES_de_qualquer_conexao(self):
        """Se ela viesse depois do `pg_dump`, o arquivo já existiria no
        repositório quando alguém lesse a mensagem."""
        codigo, saida = rodar(
            "backup.sh", ".", DATABASE_URL="postgres://nao-vai-conectar/x"
        )

        self.assertEqual(codigo, 1)
        self.assertNotIn("despejando", saida)
        self.assertFalse(list(RAIZ.glob("*.dump")), "sobrou dump na raiz")

    def test_uma_pasta_fora_do_repositorio_e_aceita(self):
        """Contra-controle: sem ele, um script que recusa TUDO passaria nos
        dois testes de cima e o backup estaria quebrado."""
        with tempfile.TemporaryDirectory() as fora:
            codigo, saida = rodar(
                "backup.sh", fora, DATABASE_URL="postgres://nao-vai-conectar/x"
            )

        self.assertIn("despejando", saida)
        self.assertNotIn("dentro de um repositório git", saida)

    def test_a_escotilha_do_ci_existe_e_e_explicita(self):
        """Um checkout descartável de CI é o caso legítimo. Sem saída, o fluxo
        do GitHub precisaria contornar a trava de outro jeito — e contornar é
        como a trava some."""
        with tempfile.TemporaryDirectory():
            codigo, saida = rodar(
                "backup.sh", ".",
                DATABASE_URL="postgres://nao-vai-conectar/x",
                PERMITIR_NO_REPO="1",
            )

        self.assertIn("despejando", saida)

    @sem_git
    def test_o_gitignore_e_a_segunda_tranca(self):
        p = subprocess.run(
            [GIT, "check-ignore", "-q", "backup-de-teste.dump"],
            cwd=str(RAIZ), capture_output=True,
        )

        self.assertEqual(p.returncode, 0, "*.dump não está no .gitignore")


@sem_gpg
class OCifradoPrecisaDecifrarAntesDeApagarOOriginalTests(SimpleTestCase):
    """A regra que o projeto já aplica ao dump, aplicada à criptografia.

    O modo de falhar de um cifrado quebrado é silencioso e tardio: ele sobe,
    aparece verde, e só se revela inútil no dia em que alguém precisa dele —
    que é o dia em que não há segunda tentativa.
    """

    def arquivo_de_teste(self, pasta):
        alvo = Path(pasta) / "coisa.dump"
        alvo.write_bytes(b"PGDMP-de-mentira-" + os.urandom(2048))
        return alvo

    def test_sem_senha_ele_se_recusa(self):
        with tempfile.TemporaryDirectory() as pasta:
            alvo = self.arquivo_de_teste(pasta)
            codigo, saida = rodar("guardar.sh", str(alvo), BACKUP_PASSPHRASE=None)

        self.assertEqual(codigo, 1)
        self.assertIn("BACKUP_PASSPHRASE", saida)

    def test_o_cifrado_decifra_e_o_original_e_apagado(self):
        with tempfile.TemporaryDirectory() as pasta:
            alvo = self.arquivo_de_teste(pasta)
            original = alvo.read_bytes()
            codigo, saida = rodar(
                "guardar.sh", str(alvo), BACKUP_PASSPHRASE="senha-de-ensaio-longa"
            )

            self.assertEqual(codigo, 0, saida)
            cifrado = Path(str(alvo) + ".gpg")
            self.assertTrue(cifrado.exists())
            self.assertFalse(alvo.exists(), "o arquivo em claro sobreviveu")
            self.assertNotIn(original[:32], cifrado.read_bytes())

            # E ele decifra DE VERDADE, com a senha certa.
            volta = Path(pasta) / "volta.bin"
            p = subprocess.run(
                [GPG, "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback",
                 "--passphrase", "senha-de-ensaio-longa",
                 "--decrypt", "-o", str(volta), str(cifrado)],
                capture_output=True,
            )
            self.assertEqual(p.returncode, 0, p.stderr[:400])
            self.assertEqual(volta.read_bytes(), original)

    def test_a_impressao_digital_do_cifrado_fica_registrada(self):
        """Sem ela, quem baixar o artefato meses depois não tem como saber se
        o arquivo chegou inteiro."""
        with tempfile.TemporaryDirectory() as pasta:
            alvo = self.arquivo_de_teste(pasta)
            rodar("guardar.sh", str(alvo), BACKUP_PASSPHRASE="senha-de-ensaio-longa")
            somas = Path(pasta) / "SHA256SUMS"

            self.assertTrue(somas.exists())
            self.assertIn("coisa.dump.gpg", somas.read_text(encoding="utf-8"))


@sem_bash
class ORestoreNaoEncostaEmProducaoTests(SimpleTestCase):
    """Restaurar por cima do banco de verdade apaga o banco de verdade."""

    def test_alvo_remoto_e_recusado_sem_forca(self):
        with tempfile.TemporaryDirectory() as pasta:
            falso = Path(pasta) / "x.dump"
            falso.write_bytes(b"nada")
            codigo, saida = rodar(
                "restaurar.sh", str(falso),
                "postgres://usuario@servidor-de-producao.example/banco",
                FORCA=None,
            )

        self.assertEqual(codigo, 1)
        self.assertIn("não é local", saida)

    def test_um_gpg_sem_senha_e_recusado_antes_de_tocar_no_banco(self):
        with tempfile.TemporaryDirectory() as pasta:
            falso = Path(pasta) / "x.dump.gpg"
            falso.write_bytes(b"nada")
            codigo, saida = rodar(
                "restaurar.sh", str(falso), BACKUP_PASSPHRASE=None
            )

        self.assertEqual(codigo, 1)
        self.assertIn("BACKUP_PASSPHRASE", saida)
        self.assertNotIn("restaurando em", saida)

    def test_cliente_velho_demais_diz_o_que_fazer(self):
        """Quatro dos cinco backups desta máquina exigem o cliente 18. Sem
        esta mensagem, o restore morre com "unsupported version" — frase que
        não diz nada para quem está tentando recuperar o banco."""
        with tempfile.TemporaryDirectory() as pasta:
            # Cabeçalho PGDMP com versão inventada e alta o bastante para
            # nenhum cliente aceitar.
            falso = Path(pasta) / "futuro.dump"
            falso.write_bytes(b"PGDMP" + bytes([9, 9, 0]) + os.urandom(64))
            codigo, saida = rodar("restaurar.sh", str(falso))

        self.assertEqual(codigo, 1)
        self.assertIn("não consegue ler este dump", saida)
        self.assertNotIn("restaurando em", saida)


class OFluxoDoGitHubNaoVazaODumpTests(SimpleTestCase):
    """O que sobe como artefato, e o que nunca deve subir."""

    def fluxo(self):
        return FLUXO.read_text(encoding="utf-8")

    def test_o_artefato_e_so_o_cifrado(self):
        texto = self.fluxo()
        bloco = texto.split("upload-artifact", 1)[1]

        self.assertIn("*.gpg", bloco)
        self.assertNotIn("*.dump\n", bloco)

    def test_o_dump_em_claro_nunca_nasce_dentro_do_checkout(self):
        """Se nascer, um passo seguinte mal escrito pode commitá-lo — e o
        repositório é público."""
        texto = self.fluxo()

        self.assertIn('backup.sh "$RUNNER_TEMP', texto)

    def test_a_criptografia_passa_pelo_script_que_prova_o_round_trip(self):
        """Gpg inline no fluxo era uma segunda cópia da lógica, e a cópia não
        decifrava de volta."""
        texto = self.fluxo()

        self.assertIn("guardar.sh", texto)

    def test_o_token_do_fluxo_nao_escreve_nada(self):
        self.assertRegex(self.fluxo(), r"permissions:\s*\n\s*contents:\s*read")

    def test_nenhum_gatilho_de_pull_request(self):
        """`pull_request_target` num fluxo com segredo é a forma mais comum de
        vazamento em Actions.

        A leitura é do BLOCO `on:`, e não do cabeçalho inteiro: o comentário
        que explica a decisão cita `pull_request_target` pelo nome, e um teste
        que varre o arquivo todo reprovaria a própria documentação.
        """
        linhas = self.fluxo().splitlines()
        inicio = linhas.index("on:")
        fim = linhas.index("permissions:")
        gatilhos = [
            linha for linha in linhas[inicio:fim]
            if linha.strip() and not linha.strip().startswith("#")
        ]

        self.assertNotIn("pull_request", " ".join(gatilhos))
        self.assertIn("workflow_dispatch", " ".join(gatilhos))

    def test_a_retencao_do_artefato_e_curta_e_declarada(self):
        """Cópia de dado de saúde não fica parada pelos 90 dias do padrão."""
        import re

        achado = re.search(r"retention-days:\s*(\d+)", self.fluxo())

        self.assertIsNotNone(achado)
        self.assertLessEqual(int(achado.group(1)), 30)


@sem_bash
class OArquivoPelaMetadeNaoSobreviveTests(SimpleTestCase):
    """Um `.dump` incompleto do lado dos bons é pior que arquivo nenhum.

    Encontrado por um teste desta mesma rodada, e não por leitura: o cenário
    da escotilha de CI deixou um arquivo de zero byte na raiz do repositório.
    O `pg_dump` cria o arquivo antes de terminar de escrevê-lo, e o `errexit`
    encerrava o script antes da conferência de tamanho que o apagaria.

    É a mesma família do defeito que originou o script — um arquivo que existe
    e não presta —, agora no caminho da falha em vez do caminho do sucesso.
    """

    def test_uma_conexao_recusada_nao_deixa_dump_no_disco(self):
        with tempfile.TemporaryDirectory() as pasta:
            codigo, saida = rodar(
                "backup.sh", pasta,
                DATABASE_URL="postgres://ninguem@127.0.0.1:1/nao-existe",
            )

            self.assertNotEqual(codigo, 0, saida)
            self.assertEqual(
                list(Path(pasta).glob("*.dump")), [],
                "sobrou um dump incompleto do lado dos bons",
            )


@sem_gpg
class AVerificacaoDoRoundTripPrecisaFuncionarTests(SimpleTestCase):
    """Provar que o cifrado decifra exige um cifrado que NÃO decifra.

    Os outros testes desta rodada mostram o caminho feliz: o gpg funciona, o
    arquivo volta, a soma bate. Nenhum deles cairia se a comparação fosse
    removida do script — e a comparação é a razão de o script existir.

    Aqui o `gpg` é trocado por um impostor que escreve lixo. Se a verificação
    estiver no lugar, o script recusa e PRESERVA o arquivo em claro; se não
    estiver, ele apaga o original e declara sucesso sobre um `.gpg` inútil —
    que é exatamente o desastre silencioso que se quer impedir.
    """

    IMPOSTOR = (
        "#!/usr/bin/env bash\n"
        "# Finge criptografar: escreve lixo no -o e ignora a entrada.\n"
        "alvo=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = '-o' ]; then alvo=\"$2\"; shift; fi\n"
        "  shift\n"
        "done\n"
        "printf 'lixo-que-nao-e-o-original' > \"$alvo\"\n"
        "exit 0\n"
    )

    def test_um_cifrado_que_nao_volta_e_recusado_e_o_original_fica(self):
        with tempfile.TemporaryDirectory() as pasta:
            falso_bin = Path(pasta) / "bin"
            falso_bin.mkdir()
            impostor = falso_bin / "gpg"
            impostor.write_text(self.IMPOSTOR, encoding="utf-8", newline="\n")
            impostor.chmod(0o755)

            alvo = Path(pasta) / "coisa.dump"
            conteudo = b"PGDMP-de-mentira-" + os.urandom(2048)
            alvo.write_bytes(conteudo)

            env = dict(os.environ)
            env["PATH"] = posix(falso_bin) + os.pathsep + env["PATH"]
            env["BACKUP_PASSPHRASE"] = "senha-de-ensaio-longa"
            p = subprocess.run(
                [BASH, posix(SCRIPTS / "guardar.sh"), posix(alvo)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env, cwd=str(RAIZ),
            )

            self.assertNotEqual(p.returncode, 0, "aceitou um cifrado quebrado")
            self.assertIn("não bate com o original", (p.stdout or "") + (p.stderr or ""))
            self.assertTrue(alvo.exists(), "apagou o original sem ter prova")
            self.assertEqual(alvo.read_bytes(), conteudo)
            self.assertFalse(
                Path(str(alvo) + ".gpg").exists(),
                "deixou no disco um cifrado que não presta",
            )


@sem_bash
class ASenhaNaoVaiParaALinhaDeComandoTests(SimpleTestCase):
    """Achado por revisão independente, e confirmado por medição.

    O cabeçalho do `backup.sh` prometia que a URL entra por ambiente e nunca
    por argumento — e a promessa era sobre como o SCRIPT é chamado. O `pg_dump`
    era chamado com `-d "$DATABASE_URL"`, então a URI inteira, com a senha
    dentro, virava o argv de um processo externo, visível em `ps`.

    O pior não era o risco na máquina de uma pessoa só: era o comentário
    garantindo uma proteção que não existia. Este teste é o que impede a
    promessa de voltar a ser falsa — ele troca o `pg_dump` por um impostor que
    grava o próprio argv e olha o que chegou lá.
    """

    IMPOSTOR = (
        "#!/usr/bin/env bash\n"
        'printf "%s\n" "$@" > "$REGISTRO_ARGV"\n'
        'printf "%s" "${PGPASSWORD:-<vazia>}" > "$REGISTRO_ENV"\n'
        "exit 9\n"
    )
    SENHA = "SENHA-QUE-NAO-PODE-VAZAR"
    URL = "postgres://usuario:%s@host.exemplo/banco?sslmode=require" % SENHA

    def test_o_pg_dump_nao_recebe_a_senha_em_argv(self):
        with tempfile.TemporaryDirectory() as pasta:
            binario = Path(pasta) / "bin"
            binario.mkdir()
            impostor = binario / "pg_dump"
            impostor.write_text(self.IMPOSTOR, encoding="utf-8", newline="\n")
            impostor.chmod(0o755)
            argv = Path(pasta) / "argv.txt"
            ambiente = Path(pasta) / "env.txt"

            env = dict(os.environ)
            env["PATH"] = posix(binario) + os.pathsep + env["PATH"]
            env["REGISTRO_ARGV"] = posix(argv)
            env["REGISTRO_ENV"] = posix(ambiente)
            env["DATABASE_URL"] = self.URL
            subprocess.run(
                [BASH, posix(SCRIPTS / "backup.sh"), posix(Path(pasta) / "saida")],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env, cwd=str(RAIZ),
            )

            self.assertTrue(argv.exists(), "o pg_dump nem chegou a ser chamado")
            linha_de_comando = argv.read_text(encoding="utf-8")
            self.assertNotIn(self.SENHA, linha_de_comando)
            # E o resto da URL continua chegando: `sslmode` e, no Neon, o
            # `channel_binding` não são enfeite — sem eles não há conexão.
            self.assertIn("sslmode=require", linha_de_comando)
            self.assertIn("usuario@host.exemplo", linha_de_comando)
            # A senha chegou pelo ambiente, que não aparece em `ps`.
            self.assertEqual(ambiente.read_text(encoding="utf-8"), self.SENHA)

    def test_uma_senha_percent_encoded_chega_decodificada(self):
        """`%40` na URI é `@` na senha. Sem decodificar, o servidor recusa a
        autenticação — no dia do desastre, e com uma mensagem que não explica
        nada."""
        with tempfile.TemporaryDirectory() as pasta:
            binario = Path(pasta) / "bin"
            binario.mkdir()
            impostor = binario / "pg_dump"
            impostor.write_text(self.IMPOSTOR, encoding="utf-8", newline="\n")
            impostor.chmod(0o755)
            ambiente = Path(pasta) / "env.txt"

            env = dict(os.environ)
            env["PATH"] = posix(binario) + os.pathsep + env["PATH"]
            env["REGISTRO_ARGV"] = posix(Path(pasta) / "argv.txt")
            env["REGISTRO_ENV"] = posix(ambiente)
            env["DATABASE_URL"] = "postgres://u:a%40b@host/banco"
            subprocess.run(
                [BASH, posix(SCRIPTS / "backup.sh"), posix(Path(pasta) / "saida")],
                capture_output=True, env=env, cwd=str(RAIZ),
            )

            self.assertEqual(ambiente.read_text(encoding="utf-8"), "a@b")

    def test_url_sem_senha_passa_intacta(self):
        """Contra-controle: um script que estraga toda URL passaria nos dois
        testes de cima e o backup estaria quebrado."""
        with tempfile.TemporaryDirectory() as pasta:
            binario = Path(pasta) / "bin"
            binario.mkdir()
            impostor = binario / "pg_dump"
            impostor.write_text(self.IMPOSTOR, encoding="utf-8", newline="\n")
            impostor.chmod(0o755)
            argv = Path(pasta) / "argv.txt"

            env = dict(os.environ)
            env["PATH"] = posix(binario) + os.pathsep + env["PATH"]
            env["REGISTRO_ARGV"] = posix(argv)
            env["REGISTRO_ENV"] = posix(Path(pasta) / "env.txt")
            env["DATABASE_URL"] = "postgres://usuario@localhost:5432/banco"
            subprocess.run(
                [BASH, posix(SCRIPTS / "backup.sh"), posix(Path(pasta) / "saida")],
                capture_output=True, env=env, cwd=str(RAIZ),
            )

            self.assertIn(
                "postgres://usuario@localhost:5432/banco",
                argv.read_text(encoding="utf-8"),
            )



@sem_bash
class ATravaOlhaAPastaENaoOAmbienteTests(SimpleTestCase):
    """A pergunta é sobre a PASTA. `GIT_DIR` a transformava noutra pergunta.

    Dentro de um hook, o git exporta `GIT_DIR` no ambiente. Com ela definida,
    `git -C <pasta> rev-parse --is-inside-work-tree` para de responder sobre a
    pasta e responde sobre o repositório da variável — devolvendo "true" para
    qualquer destino.

    O efeito prático era o pior possível para um backup: o script recusaria
    `~/backups-nutriplan`, que é o caminho que a própria documentação manda
    usar, com uma mensagem dizendo que ele está dentro de um repositório.

    Quem pegou foi a suíte completa, que roda DENTRO do hook de push. Rodando o
    arquivo sozinho, os quatro testes que caíram passavam.
    """

    def test_com_GIT_DIR_no_ambiente_uma_pasta_de_fora_continua_aceita(self):
        with tempfile.TemporaryDirectory() as fora:
            codigo, saida = rodar(
                "backup.sh", fora,
                DATABASE_URL="postgres://nao-vai-conectar/x",
                GIT_DIR=posix(RAIZ / ".git"),
            )

        self.assertNotIn("dentro de um repositório git", saida)
        self.assertIn("despejando", saida)

    def test_com_GIT_DIR_no_ambiente_a_raiz_do_repo_continua_recusada(self):
        """O outro lado: consertar o falso positivo não pode apagar a trava."""
        codigo, saida = rodar(
            "backup.sh", ".",
            DATABASE_URL="postgres://nao-vai-conectar/x",
            GIT_DIR=posix(RAIZ / ".git"),
        )

        self.assertEqual(codigo, 1)
        self.assertIn("dentro de um repositório git", saida)
