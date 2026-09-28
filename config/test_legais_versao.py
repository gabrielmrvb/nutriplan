"""Política e Termos com versão, data e encarregado (Lote 4 da missão LGPD,
28/09/2026 — Gate 1).

Três lacunas medidas no Gate 1 e fechadas aqui, com texto ainda marcado
`[REVISAR]` porque é rascunho do dono, não redação jurídica revisada:

1. a Política dizia "Quem é o responsável" e nunca nomeava o ENCARREGADO
   (art. 41 da LGPD) — a pessoa a quem se reclama, e não só "quem
   responde pelo app";
2. "Levar seus dados com você" apontava para a exportação sem dizer o que
   ela contém — e a mesma seção repetia, com duas frases, uma regra que
   cabe numa: revogar consentimento de saúde é excluir a conta;
3. os Termos citavam só a Lei 8.234/1991 (nutricionista) e nunca a Lei
   9.696/1998 (Educação Física, CREF) — o app também monta ficha de treino.

E a data no topo das duas páginas era escrita à mão duas vezes (aqui e em
`accounts.consentimento.VERSAO_DOS_LEGAIS`, que já governa quando o app
pede consentimento de novo). Este teste lê a CONSTANTE, nunca uma data
literal — subir a versão numa outra branch não pode derrubar este teste.
"""
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts import consentimento
from config.legal import data_dos_legais_por_extenso


def _sem_quebra_de_linha(html):
    """O template quebra linha dentro de frase por legibilidade do código —
    o navegador colapsa isso, e o teste também precisa colapsar, senão uma
    frase de teste que cai bem no meio de uma quebra do template reprova por
    um motivo que não tem nada a ver com o conteúdo."""
    return " ".join(html.split())


class AVersaoVemDaConstanteTests(TestCase):
    """As duas páginas mostram a mesma versão e a mesma data — a de
    `VERSAO_DOS_LEGAIS`, nunca uma string congelada no template."""

    def test_a_politica_mostra_versao_e_data(self):
        html = self.client.get(reverse("privacidade")).content.decode()
        self.assertIn("Versão %s" % consentimento.VERSAO_DOS_LEGAIS, html)
        self.assertIn(data_dos_legais_por_extenso(), html)

    def test_os_termos_mostram_versao_e_data(self):
        html = self.client.get(reverse("termos")).content.decode()
        self.assertIn("Versão %s" % consentimento.VERSAO_DOS_LEGAIS, html)
        self.assertIn(data_dos_legais_por_extenso(), html)

    def test_nenhuma_pagina_escreve_a_data_a_mao(self):
        """Sabotagem prevista: se alguém devolver "Última atualização: 21 de
        setembro de 2026." escrito no template, este teste cai, porque a
        constante pode não bater mais com o literal (outra branch sobe a
        versão para 2026-09-28)."""
        for rota in (reverse("privacidade"), reverse("termos")):
            with self.subTest(rota=rota):
                html = self.client.get(rota).content.decode()
                self.assertNotIn("Última atualização: 21 de setembro de 2026.", html)


class ADataPorExtensoTests(SimpleTestCase):
    def test_formata_sem_zero_a_esquerda_no_dia(self):
        self.assertEqual(data_dos_legais_por_extenso(), "21 de setembro de 2026")


@override_settings(LEGAL_PUBLICADO=True, LEGAL_RESPONSAVEL="Fulana de Tal", LEGAL_CONTATO="contato@exemplo.com")
class APoliticaNomeiaOEncarregadoTests(TestCase):
    """Art. 41 da LGPD: quem responde pelo tratamento tem de estar nomeado,
    não só "quem mantém o app". O contato é um PLACEHOLDER declarado —
    ainda não existe caixa própria para o encarregado."""

    def setUp(self):
        self.html = _sem_quebra_de_linha(self.client.get(reverse("privacidade")).content.decode())

    def test_diz_o_titulo_do_encarregado(self):
        self.assertIn("Encarregado pelo tratamento de dados (art. 41 da LGPD)", self.html)

    def test_usa_o_responsavel_do_contexto_como_nome(self):
        self.assertIn("Fulana de Tal", self.html)

    def test_o_email_e_o_placeholder_marcado(self):
        self.assertIn("encarregado@[REVISAR]", self.html)


class APoliticaDescreveAExportacaoCompletaTests(TestCase):
    """"Levar seus dados com você" tinha duas linhas vagas; o rascunho do
    dono lista as tabelas reais que a exportação inclui."""

    def setUp(self):
        self.html = _sem_quebra_de_linha(self.client.get(reverse("privacidade")).content.decode())

    def test_lista_as_categorias_de_dado(self):
        for trecho in (
            "pesagens", "refeições", "água (cada registro)", "treinos e séries",
            "planos de corrida", "Health Connect", "lista de compras",
            "conquistas", "avisos e e-mails", "eventos de uso",
        ):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, self.html)


class ARevogacaoDeSaudeEAExclusaoTests(TestCase):
    """§3.4 a: uma frase só, não duas dizendo a mesma coisa de dois jeitos."""

    def setUp(self):
        self.html = _sem_quebra_de_linha(self.client.get(reverse("privacidade")).content.decode())

    def test_a_frase_do_dono_esta_la(self):
        self.assertIn(
            "Retirar o consentimento para dados de saúde é excluir a conta: "
            "sem esses dados o app não calcula nada.",
            self.html,
        )


class OsTermosCitamACrefTests(TestCase):
    """§4: a ficha de treino também é entrega do app, e só a Lei 8.234/1991
    (nutricionista) estava citada — faltava a Lei 9.696/1998 (CREF)."""

    def setUp(self):
        self.html = _sem_quebra_de_linha(self.client.get(reverse("termos")).content.decode())

    def test_cita_a_lei_da_educacao_fisica_ao_lado_da_do_nutricionista(self):
        self.assertIn("Lei 8.234/1991", self.html)
        self.assertIn("Lei 9.696/1998", self.html)

    def test_diz_o_aviso_crn_cref(self):
        self.assertIn("registrado no CRN", self.html)
        self.assertIn("registrado no CREF", self.html)
        self.assertIn("não serve para tratar doença", self.html)
        # a frase original terminava em "...seguir o plano"; "plano" é
        # proibido nas telas da alimentação (config/test_linguagem.py) e foi
        # adaptada — a divergência é declarada no comentário do template.
        self.assertIn("antes de seguir o que o app sugere", self.html)
