"""O aviso de conquista não cobre "Concluir série" na execução.

Achado #3 das personas (21/09/2026), nas duas que treinaram: ao concluir a
série 1 do primeiro treino, o toast "Conquista desbloqueada · Primeiro
treino" — `position: fixed`, ancorado embaixo — cobria "CONCLUIR SÉRIE 2"
e o descanso (`elementFromPoint` no centro do botão devolvia
COMPARTILHAR). O `padding-bottom` de `body.tem-conquista` só ajuda quando
a página está rolada até o fim; no meio do treino o botão está no meio da
tela.

Na execução o aviso entra NO FLUXO, logo abaixo do botão: `agora.html`
oferece `[data-conquista-alvo]` e `conquista.js` move a caixa para lá
(`.conquista--em-fluxo`, `position: static`). Sem JavaScript continua o
fixo de sempre — que ao menos não é pior do que era.
"""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ToastNoFluxoDaExecucaoTests(SimpleTestCase):
    def test_a_execucao_tem_o_alvo_logo_depois_do_botao(self):
        html = (Path(settings.BASE_DIR) / "templates" / "workouts" / "agora.html").read_text(encoding="utf-8")
        botao = html.index('class="btn btn--primary agora__concluir"')
        alvo = html.index("data-conquista-alvo")
        self.assertGreater(alvo, botao)
        self.assertLess(alvo - botao, 1500, "o alvo mora logo abaixo do botão, não no fim da página")

    def test_o_script_move_a_caixa_para_o_alvo(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "conquista.js").read_text(encoding="utf-8")
        self.assertIn("data-conquista-alvo", js)
        self.assertIn("conquista--em-fluxo", js)
        self.assertIn('classList.remove("tem-conquista")', js)

    def test_no_fluxo_a_caixa_nao_e_fixa(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
        regra = css.split(".conquista--em-fluxo", 1)[1].split("}", 1)[0]
        self.assertIn("position: static", regra)
