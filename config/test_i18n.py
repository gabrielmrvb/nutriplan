# -*- coding: utf-8 -*-
"""i18n preparada, sem traduzir (21/09/2026).

O app é pt-BR e continua sendo. O que este arquivo prende é o TERRENO: o
catálogo existe e o Django o encontra; toda frase marcada nos templates
novos está listada nele com `msgstr` vazio (o Django mostra o msgid, que já
é o texto certo); e nenhuma tela mudou de língua — não há LocaleMiddleware
nem negociação por cabeçalho. Marcar é barato agora e caro depois: a régua
`TEMPLATES_NOVOS` cresce com cada template criado a partir de hoje.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.utils import translation

RAIZ = Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / "locale" / "pt_BR" / "LC_MESSAGES" / "django.po"
#: Templates criados (ou frases novas em templates velhos) a partir de
#: 21/09/2026: cada um carrega `{% load i18n %}` e marca o texto visível.
#: `templates/base.html` entra pela FRASE nova (a faixa do staging), não pelo
#: arquivo inteiro — marcar mil frases antigas de uma vez não é o objetivo.
#:
#: A EXCEÇÃO, que existe desde 21/09/2026 e nunca esteve escrita:
#: `templates/analytics/` — o painel de GESTÃO — fica de fora. Os seis
#: templates nascidos com o painel, no MESMO dia em que esta régua foi
#: escrita, não carregam `{% load i18n %}` e nunca entraram na lista; os de
#: 24/09 (entrada, uso) seguem o precedente. A razão: aquelas telas são a
#: ferramenta de quem OPERA o produto, não o produto — a segunda língua, no
#: dia em que existir, é para quem USA o app. Quando isso mudar, entram
#: todos de uma vez, e não meia dúzia de frases soltas.
TEMPLATES_NOVOS = {
    "templates/base.html": ["STAGING — não é produção"],
    # A receita (23/09/2026): duas telas NOVAS, e por isso o texto visível
    # delas nasce marcado. A tela que as inclui (`alimentacao.html`) é
    # antiga e continua fora — marcar mil frases velhas de uma vez não é o
    # objetivo desta régua, e a lista diz exatamente o que está coberto.
    "templates/plans/receita.html": ['Voltar ao cardápio'],
    # O PROGRESSO (23/09/2026): a parcial de área é nova — uma para as quatro
    # seções —, e por isso nasce com o texto visível marcado. `history.html`
    # e `_peso.html` são antigos e continuam fora: marcar mil frases velhas
    # de uma vez não é o objetivo desta régua.
    "templates/plans/_progresso_area.html": ['O que este gráfico mede', 'treinou', 'descanso combinado', 'combinado, sem série', 'sem registro', 'dia cheio', 'Seus recordes', 'Os recordes aparecem a partir do segundo treino com carga.', 'O que mais você registrou', 'Ritmo da última semana:', 'por km'],
    "templates/plans/_receita.html": ['Porção', 'Proteína', 'Carboidrato', 'Gordura', 'O que vai', 'Como faz', 'Você registrou esta refeição.', 'Comi esta', 'Trocar por outra receita'],
    # A missão "dado errado" (24/09/2026): duas parciais novas e uma tela
    # nova, e as três nascem marcadas.
    "templates/workouts/_series_do_dia.html": ['kg no total'],
    "templates/workouts/exercicios_feitos.html": ['Exercícios que já fiz', 'Treino', 'Tudo em que você registrou série, esteja na ficha de hoje ou não.', 'Ver a semana', 'Última vez:'],
}


def msgids_do_catalogo():
    texto = CATALOGO.read_text(encoding="utf-8")
    return re.findall(r'^msgid "((?:[^"\\]|\\.)+)"\s*$', texto, re.M)


class OTerrenoDaI18nTests(SimpleTestCase):
    def test_o_app_e_pt_br_e_so_pt_br(self):
        self.assertEqual(settings.LANGUAGE_CODE, "pt-br")
        self.assertTrue(settings.USE_I18N)
        self.assertEqual([codigo for codigo, _ in settings.LANGUAGES], ["pt-br"])
        self.assertNotIn("django.middleware.locale.LocaleMiddleware", settings.MIDDLEWARE, "sem negociação: nenhuma tela muda de língua")

    def test_o_catalogo_existe_onde_o_django_procura(self):
        self.assertEqual([Path(p) for p in settings.LOCALE_PATHS], [RAIZ / "locale"])
        self.assertTrue(CATALOGO.exists(), CATALOGO)
        texto = CATALOGO.read_text(encoding="utf-8")
        self.assertIn('"Language: pt_BR\\n"', texto)
        self.assertIn('"Content-Type: text/plain; charset=UTF-8\\n"', texto)

    def test_toda_frase_marcada_nos_templates_novos_esta_no_catalogo_sem_traducao(self):
        texto = CATALOGO.read_text(encoding="utf-8")
        listadas = msgids_do_catalogo()
        for caminho, frases in TEMPLATES_NOVOS.items():
            template = (RAIZ / caminho).read_text(encoding="utf-8")
            self.assertRegex(template, r"\{% load [^%]*\bi18n\b", caminho)
            for frase in frases:
                with self.subTest(template=caminho, frase=frase):
                    self.assertIn('{%% translate "%s" %%}' % frase, template, "a frase nova entra marcada")
                    self.assertIn(frase, listadas, "e listada no catálogo")
                    trecho = texto[texto.index('msgid "%s"' % frase):]
                    # SEM `$`: o `trecho` começa no `msgid` procurado e vai
                    # até o FIM DO ARQUIVO, então ancorar o fim exigia que
                    # a frase fosse a última do catálogo — e era, enquanto
                    # havia uma só. Com dez, nove reprovavam por posição. O
                    # que a régua mede é o que vem LOGO DEPOIS do msgid.
                    self.assertRegex(trecho, r'^msgid "[^\n]*"\nmsgstr ""(\n|$)', "sem tradução: msgstr vazio")

    def test_o_catalogo_nao_tem_traducao_nenhuma(self):
        texto = CATALOGO.read_text(encoding="utf-8")
        corpo = texto[texto.index('msgid ""') + 8:]
        for m in re.finditer(r'^msgstr "((?:[^"\\]|\\.)*)"', corpo, re.M):
            self.assertEqual(m.group(1), "", "traduzir é decisão de produto — ainda não")

    def test_a_frase_marcada_renderiza_o_proprio_texto(self):
        with translation.override("pt-br"):
            self.assertEqual(translation.gettext("STAGING — não é produção"), "STAGING — não é produção")
