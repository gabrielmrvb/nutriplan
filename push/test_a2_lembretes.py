"""O cartão de lembretes não manda ativar o que não existe — achado A2.

O caso real, medido em produção: `/hoje/` mostrava um cartão "Lembretes" com
a frase *"Ative para receber um aviso 10 minutos antes de cada refeição"* e
**nenhum controle na tela**. O botão existia no DOM com `hidden`.

A causa era o `return` antecipado de `pwa.js`: ele escondia o botão e saía
sem chamar `say()`, deixando de pé o texto que o SERVIDOR escreve. Todos os
outros ramos do arquivo atualizam a frase.

E não era estado do demo: `NUTRIPLAN_VAPID_KEY` é um global do servidor,
vazio para todo mundo. Toda pessoa com conta real via o mesmo cartão.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
PWA = RAIZ / "static" / "js" / "pwa.js"
HOJE = RAIZ / "templates" / "plans" / "today.html"


def sem_comentarios(texto):
    """O JavaScript sem comentários.

    O comentário que explica a correção CITA `say()` e o texto do servidor.
    Sem remover comentário, a asserção casaria com a prosa que descreve o
    conserto em vez de com o conserto.
    """
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", texto)


class OCartaoDeLembretesNaoMenteTests(SimpleTestCase):
    def setUp(self):
        self.js = sem_comentarios(PWA.read_text(encoding="utf-8"))

    def test_o_ramo_indisponivel_atualiza_o_texto_antes_de_sair(self):
        """Esconder o controle sem trocar a frase é o defeito inteiro."""
        ramo = re.search(
            r"if\s*\(\s*!supported\s*\|\|\s*!window\.NUTRIPLAN_VAPID_KEY\s*\)\s*\{"
            r"(.*?)\n    \}",
            self.js,
            flags=re.S,
        )

        self.assertIsNotNone(ramo, "sumiu o ramo que trata push indisponível")
        corpo = ramo.group(1)
        self.assertIn("button.hidden = true", corpo)
        self.assertIn(
            "say(",
            corpo,
            "o ramo esconde o botão e sai sem corrigir a frase — é o A2 de "
            "volta: a tela manda ativar uma coisa que não tem como ativar.",
        )

    def test_as_duas_causas_dizem_coisas_diferentes(self):
        """Suporte do navegador e chave ausente não são o mesmo problema.

        Um é do aparelho de quem lê, o outro é nosso. Uma frase só para os
        dois casos ou culpa o navegador de quem não tem culpa, ou esconde
        que a configuração do servidor está incompleta.
        """
        ramo = re.search(
            r"!window\.NUTRIPLAN_VAPID_KEY\s*\)\s*\{(.*?)\n    \}",
            self.js,
            flags=re.S,
        )
        corpo = ramo.group(1)
        self.assertIn("supported", corpo)
        frases = re.findall(r'"([^"]{20,})"', corpo)
        self.assertEqual(
            len(set(frases)),
            2,
            f"esperava duas frases distintas para as duas causas, veio {frases}",
        )

    def test_o_texto_do_servidor_continua_sendo_o_convite(self):
        """Controle positivo, e ele guarda a outra metade do defeito.

        A correção é no JavaScript de propósito: o texto do servidor está
        CERTO para quem tem push disponível, e é ele que aparece antes de o
        script rodar. Trocar a frase no template resolveria a tela quebrada
        criando outra — quem pode ativar deixaria de ser convidado.
        """
        html = HOJE.read_text(encoding="utf-8")

        self.assertIn("data-push-status", html)
        self.assertRegex(html, r"Ative para receber")
