# -*- coding: utf-8 -*-
"""O aviso de conquista celebra sem cobrir nada.

N1 (DELTA de 16/09/2026): o aviso `position: fixed` ficava em toda página até
"Continuar" e cobria o CTA do rodapé — em /conta/excluir/, o clique em
"Excluir minha conta" caía no "Continuar" do aviso. Aqui: o `body` ganha
`tem-conquista` e o container recebe `padding-bottom` (o mesmo mecanismo do
convite de instalação), o aviso fecha por Esc, e não aparece em página de erro
(o 404 não tem `resolver_match` — `HttpRequest.__init__` já o inicia em
`None`, e só ganha valor quando `resolve()` acha rota).

BENCHMARK-2026-09 (a): o recorde é celebrado com um "frame de recompensa" —
entrada animada com tokens de movimento, desligada em reduced-motion, e som
OPCIONAL (opt-in, `localStorage`), nunca por padrão.
"""
import re

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from achievements.context_processors import CHAVE
from achievements.models import UserAchievement
from workouts import services
from workouts.tests import create_user, dias_incluindo_hoje

CSS = "static/css/app.css"
JS = "static/js/conquista.js"


def _ler(caminho):
    return (settings.BASE_DIR / caminho).read_text(encoding="utf-8")


def _blocos_reduzidos(css):
    """Todo o CSS dentro de QUALQUER `@media (prefers-reduced-motion: reduce)`,
    com as chaves balanceadas.

    O arquivo tem mais de uma dúzia desses blocos, e o da seção 47 — onde
    `.conquista` entra — é só mais um no meio, não o primeiro. Um
    `re.search` que pega o primeiro `@media (...) {` do arquivo e para no
    primeiro `\\n}\\n` que aparecer depois mede o bloco ERRADO (o de outra
    seção, bem mais cedo no arquivo). Balancear as chaves é o que garante
    medir o bloco que CADA `@media` realmente abre.
    """
    for m in re.finditer(r"@media \(prefers-reduced-motion: reduce\)\s*\{", css):
        i, nivel = m.end(), 1
        while nivel and i < len(css):
            nivel += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        yield css[m.end():i - 1]


class OAvisoNaoCobreNadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="frame@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def _com_aviso_pendente(self, slug="primeiro-treino"):
        # Não há model `Achievement`: o catálogo é `regras.CATALOGO`/`POR_SLUG`
        # (em código), e `UserAchievement.slug` é só um `CharField` — a
        # conquista nasce direto, sem buscar uma linha de catálogo no banco.
        nova = UserAchievement.objects.create(
            user=self.pessoa, slug=slug, unlocked_at=timezone.now()
        )
        sessao = self.client.session
        sessao[CHAVE] = [nova.pk]
        sessao.save()
        return nova

    def test_o_body_ganha_a_classe_e_o_css_empurra_o_conteudo(self):
        self._com_aviso_pendente()
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertRegex(html, r'<body[^>]*class="[^"]*\btem-conquista\b')
        css = _ler(CSS)
        # Há DUAS regras (móvel e a de `@media (min-width: 40rem)`) — checar
        # só "existe alguma com padding-bottom" deixa passar uma sabotagem
        # que troca só a móvel para `padding-top`, porque a outra ainda bate.
        blocos = re.findall(
            r"body\.tem-conquista[^{]*\.container\s*\{([^}]*)\}", css
        )
        self.assertTrue(blocos, "nenhuma regra de padding para body.tem-conquista")
        for bloco in blocos:
            with self.subTest(bloco=bloco):
                self.assertIn("padding-bottom", bloco)
                self.assertNotIn("padding-top", bloco)

    def test_sem_aviso_o_body_nao_tem_a_classe(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn("tem-conquista", html)

    def test_o_aviso_nao_aparece_em_pagina_de_erro(self):
        self._com_aviso_pendente()
        html = self.client.get("/rota/que/nao/existe/").content.decode()
        self.assertNotIn('class="conquista"', html)
        self.assertNotIn("tem-conquista", html)

    def test_o_recorde_tem_a_variante_visual(self):
        self._com_aviso_pendente("novo-recorde")
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("conquista--recorde", html)
        self.assertRegex(_ler(CSS), r"\.conquista--recorde\s*\{[^}]*--brand-soft")

    def test_a_entrada_e_animada_por_token_e_desligada_em_reduced_motion(self):
        css = _ler(CSS)
        self.assertRegex(css, r"@keyframes conquista-chega")
        bloco = re.search(
            r"\.conquista\s*\{[^}]*animation:[^;]*conquista-chega[^;]*var\(--mov-", css
        )
        self.assertIsNotNone(bloco, "a animação de entrada precisa usar um token de duração")
        reduzido = "\n".join(_blocos_reduzidos(css))
        # Armadilha real: `.conquista__compartilhar` e `.conquista__continuar`
        # já vivem num OUTRO bloco reduzido (o do toque, seção 8) — um `in`
        # ingênuo (`assertIn(".conquista", reduzido)`) acha aquele por
        # acidente e o teste passa mesmo sabotado. A fronteira de palavra
        # garante o NOME EXATO da classe, não um prefixo dela.
        self.assertRegex(reduzido, r"(?<![\w-])\.conquista(?![\w-])")
        self.assertRegex(reduzido, r"(?<![\w-])\.conquista__emoji(?![\w-])")

    def test_esc_fecha_pelo_mesmo_post(self):
        self._com_aviso_pendente()
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("conquista.js", html)
        js = _ler(JS)
        self.assertIn('"Escape"', js)
        self.assertIn("X-Requested-With", js)

    def test_o_som_e_opt_in(self):
        js = _ler(JS)
        self.assertIn("nutriplan.som-conquista", js)
        self.assertIn("AudioContext", js)
        html = self.client.get(reverse("achievements:list")).content.decode()
        self.assertIn("Tocar um som ao desbloquear", html)
        self.assertNotIn('data-som="1"', html)  # o servidor nunca liga; só o cliente
