"""A DICA DO MOVIMENTO NÃO QUEBRA LETRA A LETRA SEM VÍDEO (caça-bugs BA9;
pente-fino de qualidade, onda 2, 28/09/2026).

`.demo` é uma linha flex: mídia de 8rem à esquerda, dica com `flex: 1` ao
lado. Sem demonstração, o lugar da mídia é o parágrafo "Sem demonstração
cadastrada · Buscar no YouTube", que não tinha largura fixa e crescia até o
texto dele caber — medido a 390 no exercício de peso do corpo: a dica ficou
com 49 px e cada linha com uma sílaba ("ombro / s;"). Agora a linha QUEBRA:
o aviso ocupa a largura inteira e a dica desce para baixo dele. Só CSS: o
template (`workouts/_demonstracao.html`) não muda.
"""
from django.test import SimpleTestCase

from config.test_design_system import CSS, sem_comentarios
from config.test_nervura import _regra


class ADicaSemVideoTemALarguraTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_a_linha_da_demonstracao_pode_quebrar(self):
        self.assertIn("flex-wrap: wrap", _regra(self.css, ".demo", contendo="display: flex"))

    def test_o_aviso_sem_video_ocupa_a_linha_inteira(self):
        self.assertIn("flex: 1 1 100%", _regra(self.css, ".agora__sem-media", contendo="display: grid"))

    def test_a_dica_embaixo_do_aviso_ganha_margem_da_esquerda(self):
        self.assertIsNotNone(_regra(self.css, ".agora__sem-media + .demo__cue"))
