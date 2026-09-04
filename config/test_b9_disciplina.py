# -*- coding: utf-8 -*-
"""B9 — os guardrails continuam de pé, e a regra do runner virou mecanismo.

O contrato do B9 pede duas coisas. A primeira é preservar quatro guardrails
sistêmicos; a segunda é a regra "NUNCA rodar suíte dirigida enquanto a completa
estiver usando o mesmo test_nutriplan — antes de qualquer execução, verificar
se existe runner ativo".

Preservar, aqui, precisa de teste: um guardrail apagado não faz teste nenhum
ficar vermelho, porque ele PRÓPRIO era o teste. Some, e a suíte fica verde com
menos proteção — o modo de falha mais silencioso que existe num repositório.

E a regra do runner era só escrita. Ela falhou duas vezes na mesma sessão, e a
segunda derrubou o hook de push com uma mensagem sobre banco quando o problema
era de processo. `config/runner.py` é a verificação; este arquivo é a prova de
que ela está ligada e de que ela pergunta a coisa certa.
"""
import os
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from config import runner


class OsQuatroGuardrailsContinuamDePeTests(SimpleTestCase):
    """Apagar um guardrail deixa a suíte VERDE com menos proteção.

    Por isso os quatro são nomeados aqui: o teste falha na importação se
    alguém remover a classe, e falha na asserção se alguém a esvaziar até
    virar casca.
    """

    #: (módulo, classe, o que ela protege)
    GUARDRAILS = (
        ("accounts.tests", "RotasExtrasDoAdminTests",
         "rota do Admin fora das padrão precisa de decisão escrita"),
        ("config.tests", "TodaTelaTemPortaTests",
         "destino que alguém precisa alcançar tem link em algum template"),
        ("config.tests", "ComentarioDeTemplateNaoVazaTests",
         "`{# #}` em três linhas vira texto na tela"),
        ("accounts.tests", "MatrizDeCapabilityTests",
         "o que cada papel alcança, medido por HTTP"),
    )

    def test_os_quatro_existem_e_tem_teste_dentro(self):
        import importlib

        for caminho, nome, protege in self.GUARDRAILS:
            with self.subTest(guardrail=nome):
                modulo = importlib.import_module(caminho)
                classe = getattr(modulo, nome, None)
                self.assertIsNotNone(
                    classe, "%s sumiu — %s ficou sem proteção" % (nome, protege)
                )
                metodos = [m for m in dir(classe) if m.startswith("test_")]
                self.assertTrue(
                    metodos, "%s virou casca vazia" % nome
                )


class ORunnerUnicoEstaLigadoTests(SimpleTestCase):
    """O teste estrutural: sem ele, tirar a linha do settings mata a
    verificação e a suíte inteira continua verde."""

    def sem_escotilha(self):
        """O teste controla o próprio ambiente.

        A escotilha é uma variável de ambiente, e o roteiro de sabotagem liga
        ela para rodar os cenários em série. Sem isto, um teste que mede a
        checagem leria o ambiente de quem chamou e passaria — ou falharia — por
        um motivo que não é o dele.
        """
        ambiente = dict(os.environ)
        ambiente.pop(runner.IGNORAR, None)
        return mock.patch.dict(os.environ, ambiente, clear=True)

    def test_o_settings_aponta_para_o_runner_do_projeto(self):
        self.assertEqual(settings.TEST_RUNNER, "config.runner.RunnerUnico")

    def test_o_runner_pergunta_antes_de_criar_o_banco(self):
        """A ORDEM é o teste, e não o fato de os dois acontecerem.

        Perguntar depois de criar já é tarde: `create_test_db` é justamente o
        que explode quando alguém está conectado, e aí a mensagem que a pessoa
        lê volta a ser a do Postgres. Asserir só `called` nos dois deixaria
        passar exatamente essa regressão.
        """
        ordem = []
        with self.sem_escotilha(), mock.patch.object(
            runner, "conexoes_ativas",
            side_effect=lambda *_: ordem.append("perguntou") or [],
        ), mock.patch(
            "django.test.runner.DiscoverRunner.setup_databases",
            side_effect=lambda *a, **k: ordem.append("criou"),
        ):
            runner.RunnerUnico().setup_databases()

        self.assertEqual(ordem, ["perguntou", "criou"])

    def test_a_escotilha_realmente_pula_a_checagem(self):
        """Ela está documentada; precisa também funcionar. Uma saída de
        emergência que não abre é pior que não ter saída — a pessoa descobre
        no momento em que já não tem alternativa."""
        with mock.patch.dict(
            os.environ, {runner.IGNORAR: "1"}
        ), mock.patch.object(runner, "conexoes_ativas") as perguntou, \
                mock.patch("django.test.runner.DiscoverRunner.setup_databases"):
            runner.RunnerUnico().setup_databases()

        self.assertFalse(perguntou.called)

    def test_com_alguem_conectado_o_runner_nao_roda(self):
        linhas = [(11640, "test_nutriplan", "idle in transaction", 3)]
        with self.sem_escotilha(), \
                mock.patch.object(
                    runner, "conexoes_ativas", return_value=linhas
                ), \
                mock.patch(
                    "django.test.runner.DiscoverRunner.setup_databases"
                ) as criou:
            with self.assertRaises(SystemExit) as parou:
                runner.RunnerUnico().setup_databases()

        self.assertIn("11640", str(parou.exception))
        self.assertFalse(
            criou.called, "criou o banco mesmo com outro runner na frente"
        )


class OQueORunnerPerguntaTests(SimpleTestCase):
    """A consulta em si, com uma conexão de mentira — o que importa é O QUE
    ela pergunta, e isso dá para medir sem um segundo runner de verdade."""

    class CursorFalso:
        def __init__(self, dono):
            self.dono = dono

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, params):
            self.dono.sql = sql
            self.dono.params = params

        def fetchall(self):
            return self.dono.linhas

    class ConexaoFalsa:
        def __init__(self, vendor="postgresql", linhas=(), explode=False):
            self.vendor = vendor
            self.linhas = list(linhas)
            self.explode = explode
            self.sql = None
            self.params = None
            self.settings_dict = {"NAME": "nutriplan", "TEST": {"NAME": None}}

        def cursor(self):
            if self.explode:
                raise RuntimeError("banco fora do ar")
            return OQueORunnerPerguntaTests.CursorFalso(self)

    def test_a_propria_conexao_do_runner_nao_conta(self):
        """Sem isto o runner se veria na lista e nunca rodaria — o guardrail
        mais inútil possível, o que impede tudo."""
        conexao = self.ConexaoFalsa()

        runner.conexoes_ativas(conexao, "test_nutriplan")

        self.assertIn("pg_backend_pid()", conexao.sql)

    def test_o_clone_do_parallel_tambem_conta(self):
        """`--parallel` cria `test_nutriplan_1`, `_2`... Uma execução paralela
        é uma execução, e brigar com ela embaralha igual."""
        conexao = self.ConexaoFalsa()

        runner.conexoes_ativas(conexao, "test_nutriplan")

        self.assertEqual(conexao.params, ["test_nutriplan", r"test_nutriplan\_%"])

    def test_backend_que_nao_e_postgres_nao_e_interrogado(self):
        conexao = self.ConexaoFalsa(vendor="sqlite")

        self.assertIsNone(runner.conexoes_ativas(conexao, "test_nutriplan"))
        self.assertIsNone(conexao.sql)

    def test_falha_ao_perguntar_nao_vira_falha_ao_rodar(self):
        """Não saber é motivo para não afirmar nada, e não para impedir a
        pessoa de testar. Um guardrail que quebra quando o Postgres pisca vira
        o problema que ele veio resolver."""
        conexao = self.ConexaoFalsa(explode=True)

        self.assertIsNone(runner.conexoes_ativas(conexao, "test_nutriplan"))

    def test_o_nome_configurado_ganha_do_palpite_com_prefixo(self):
        conexao = self.ConexaoFalsa()
        conexao.settings_dict["TEST"]["NAME"] = "outro_banco"

        self.assertEqual(runner.nome_do_banco_de_teste(conexao), "outro_banco")

    def test_sem_nome_configurado_vale_o_prefixo_do_django(self):
        conexao = self.ConexaoFalsa()

        self.assertEqual(
            runner.nome_do_banco_de_teste(conexao), "test_nutriplan"
        )


class AMensagemPrecisaDizerOQueFazerTests(SimpleTestCase):
    """Uma mensagem que só diz "runner ativo detectado" manda a pessoa
    procurar no histórico o comando que ela não anotou. Esta diz o pid, o
    banco, e o comando inteiro."""

    LINHAS = [(11640, "test_nutriplan", "idle in transaction", 42)]

    def texto(self):
        return runner.descrever(self.LINHAS, "test_nutriplan")

    def test_diz_quem_esta_na_frente(self):
        texto = self.texto()

        self.assertIn("11640", texto)
        self.assertIn("idle in transaction", texto)
        self.assertIn("42 s", texto)

    def test_traz_o_comando_pronto_e_so_do_banco_de_teste(self):
        texto = self.texto()

        self.assertIn("pg_terminate_backend", texto)
        self.assertIn("datname LIKE 'test_nutriplan%'", texto)

    def test_a_escotilha_esta_escrita_com_o_preco_dela(self):
        """Uma saída de emergência sem o preço ao lado vira o caminho normal."""
        texto = self.texto()

        self.assertIn(runner.IGNORAR, texto)
        self.assertIn("embaralhado", texto)
