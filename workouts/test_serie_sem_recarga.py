# -*- coding: utf-8 -*-
""""Concluir série" sem recarregar a página (decisão do dono, 20/09/2026).

Medido em L08 (CLAUDE.md): cada série era POST→302→GET de 31 KB, 180–330 ms
de `load` no Wi-Fi e ~550 ms no 3G lento — e o iframe do vídeo que a pessoa
abriu MORRIA com a recarga (1 → 0): a cada série, tocar "ver vídeo" de novo.
A auditoria de 20/09 pôs isso como o upgrade de maior impacto da execução.

Como funciona (nasceu no `proto/execucao-sem-recarga` da sessão auditoria):
o `submit` dos dois formulários marcados com `data-sem-recarga` (concluir
série e desfazer) vai por `fetch`, segue o 302 e recebe o MESMO HTML que o
servidor já renderiza; só o `<main>`, o título, a URL, a classe do `<body>`
e o aviso de conquista são trocados; o iframe aberto entra no lugar do botão
"ver vídeo" quando o exercício é o mesmo; os scripts do `<main>` são
recriados e rodam sobre os nós novos. Sem rede, `fila.js` continua dono.
Qualquer tropeço cai na recarga de sempre por `requestSubmit`, que dispara o
evento `submit` — e a fila offline continua enxergando o formulário.

O servidor NÃO mudou: o que se prova aqui é a estrutura servida e que a
rota continua respondendo 302 a um `fetch` (que o segue). O comportamento
— uma entrada de navegação antes e depois, iframe mantido, "SÉRIE 1 DE 4"
→ "2 DE 4" → desfazer → "1 DE 4" — foi provado no navegador (agent-browser)
e está no PR.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


def _sem_comentarios(texto):
    import re

    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


class OsFormulariosDaExecucaoVaoSemRecargaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="serie@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        escolher_opcao_de_hoje(self.pessoa)
        self.client.force_login(self.pessoa)

    def _tela(self):
        resposta = self.client.get(reverse("workouts:now"))
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode()

    def test_o_formulario_de_concluir_serie_esta_marcado(self):
        html = self._tela()
        self.assertRegex(html, r'<form class="registro registro--agora" method="post" data-sem-recarga')

    def test_o_desfazer_tambem_depois_da_primeira_serie(self):
        html = self._tela()
        atual = html.split('name="exercise_id" value="')[1].split('"')[0]
        ExerciseLog.objects.create(user=self.pessoa, exercise_id=int(atual), date=timezone.localdate(),
                                   set_number=1, weight_kg=Decimal("40"), reps=10)
        html = self._tela()
        self.assertRegex(html, r'<form method="post" action="[^"]+" class="agora__desfazer" data-sem-recarga>')

    def test_o_script_troca_o_main_e_cai_na_recarga_de_sempre_pelo_evento(self):
        js = _sem_comentarios(self._tela())
        self.assertIn('form.hasAttribute("data-sem-recarga")', js)
        self.assertIn("navigator.onLine", js, "sem rede, fila.js continua dono")
        self.assertIn("main.replaceChildren", js)
        self.assertIn('history.replaceState(null, "", r.url)', js)
        self.assertIn('form.setAttribute("data-recarga-de-sempre", "1")', js)
        self.assertIn("form.requestSubmit(", js, "o reenvio dispara o evento submit para a fila offline ver")
        self.assertIn('form.hasAttribute("data-recarga-de-sempre")', js)
        self.assertIn('".registro--agora button[type=submit]"', js, "o foco vai para o Concluir da série nova")

    def test_o_video_aberto_sobrevive_quando_o_exercicio_e_o_mesmo(self):
        js = _sem_comentarios(self._tela())
        self.assertIn('demoVivo.querySelector("iframe, video")', js)
        self.assertIn("idDepois === idAntes", js)
        # ...e sobrevive SEM sair do documento (a troca contorna o nó vivo).
        self.assertIn("if (manteve) trocarMantendo(main, novoMain, demoVivo, demoNovo)", js)

    def test_a_rota_continua_respondendo_302_a_um_fetch(self):
        """O servidor não mudou: o fetch segue o 302 e recebe a página."""
        html = self._tela()
        exercicio = html.split('name="exercise_id" value="')[1].split('"')[0]
        op_id = html.split('name="op_id" value="')[1].split('"')[0]
        resposta = self.client.post(reverse("workouts:record_set"),
                                    {"exercise_id": exercicio, "op_id": op_id, "weight_kg": "40", "reps": "10"},
                                    HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(ExerciseLog.objects.filter(user=self.pessoa).count(), 1)


def _texto(caminho):
    import io
    from django.conf import settings

    return _sem_comentarios(io.open(settings.BASE_DIR / caminho, encoding="utf-8").read())


class ATrocaDoMainNaoDeixaNadaVivoParaTrasTests(TestCase):
    """Revisão adversarial da troca de <main> (20/09/2026, sessão auditoria).

    Trocar o <main> por fetch tira a página do caminho "recarregar limpa
    tudo": o que a versão anterior deixava para trás eram três coisas, e as
    três foram medidas na leitura do código antes de virarem defeito em
    produção. O placar da última série chega num <main> novo que `pwa.js`
    nunca vê (ele só roda `aoCarregar` no DOMContentLoaded) — o número não
    conta do zero e a cascata não recebe `--i`. O iframe do vídeo movido por
    `replaceWith` SAI do documento por um instante, e o navegador descarta o
    browsing context: o vídeo recarrega, e o script recriado não acha
    `[data-demo-abrir]` — o "fechar" ficou no <main> velho. E o
    `setInterval` do descanso velho segue vivo sobre nós soltos: ao chegar a
    zero vibra "pode ir" para um descanso que não existe mais, junto com o
    novo — e o ouvinte do pulso de 35 ms, registrado no `document` por um
    script que mora no <main>, acumula um por troca.
    """

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="troca@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        escolher_opcao_de_hoje(self.pessoa)
        self.client.force_login(self.pessoa)

    def _tela(self):
        resposta = self.client.get(reverse("workouts:now"))
        self.assertEqual(resposta.status_code, 200)
        return resposta.content.decode()

    def assertIn(self, trecho, texto, msg=None):
        # A página inteira no relatório de falha esconde a asserção.
        self.assertTrue(trecho in texto, msg or "%r não está no texto" % trecho)

    def assertNotIn(self, trecho, texto, msg=None):
        self.assertFalse(trecho in texto, msg or "%r está no texto" % trecho)

    # ---- 1. o placar conta do zero depois da troca -------------------------

    def test_o_placar_mora_no_main_trocado(self):
        """A razão do defeito: o placar chega pela troca, não pelo carregamento."""
        estado = services.estado_do_treino(self.pessoa)
        for item in estado.itens:
            for n in range(1, item.sets + 1):
                ExerciseLog.objects.create(user=self.pessoa, exercise=item.exercise, date=timezone.localdate(),
                                           set_number=n, weight_kg=Decimal("40"), reps=10)
        html = self._tela()
        main = html.split("<main")[1].split("</main>")[0]
        self.assertIn('data-conta="zero"', main)
        self.assertIn("data-escalonado", main)

    def test_os_numeros_do_placar_contam_de_novo_quando_a_pagina_e_trocada(self):
        js = _texto("static/js/pwa.js")
        self.assertIn("function animarNumeros(raiz)", js, "os contadores precisam ser chamáveis fora do carregamento")
        self.assertIn("animarNumeros(document)", js, "o carregamento continua animando a página inteira")
        troca = js.split('addEventListener("nutriplan:pagina-trocada"')
        self.assertEqual(len(troca), 2, "pwa.js ouve a troca de <main> uma vez")
        self.assertIn("animarNumeros(", troca[1][:600], "e re-anima os números do <main> novo")
        html = _sem_comentarios(self._tela())
        # O evento é disparado DEPOIS de os scripts do <main> serem recriados:
        # a nervura do placar e a contagem dependem dos nós novos.
        self.assertLess(html.index("velho.replaceWith(novo)"),
                        html.index('new CustomEvent("nutriplan:pagina-trocada"'))

    # ---- 2. o vídeo aberto fica no documento e continua fechando -----------

    def test_o_video_aberto_nunca_sai_do_documento(self):
        js = _sem_comentarios(self._tela())
        self.assertIn("function trocarMantendo(", js, "a troca contorna o [data-demo] vivo em vez de removê-lo")
        self.assertIn('trocarMantendo(main, novoMain, demoVivo, demoNovo)', js)
        self.assertNotIn("abrir.replaceWith(video)", js, "mover o iframe é removê-lo: o navegador recarrega")
        self.assertNotIn("data-demo-aberto", js, "atributo sem consumidor")
        # A troca completa continua sendo o caminho de quem não tem vídeo
        # aberto ou trocou de exercício.
        self.assertIn("main.replaceChildren", js)

    # ---- 3. o descanso vibra uma vez ---------------------------------------

    def test_o_descanso_velho_para_antes_da_troca(self):
        js = _sem_comentarios(self._tela())
        self.assertIn("window.__descansoTique = tique", js, "o descanso deixa o interval onde a troca alcança")
        # Quem está com a tela na mão limpa o anterior ao nascer...
        self.assertIn("if (window.__descansoTique) clearInterval(window.__descansoTique)", js)
        # ...e a troca limpa ANTES de tirar os nós — o placar da última
        # série não tem descanso novo para limpar o velho.
        troca = js.split("main.replaceChildren")[0]
        self.assertIn("clearInterval(window.__descansoTique)", troca)
        # O relógio das fotos alternadas é o outro interval que mora no
        # <main>: medido no navegador, um a mais vivo por série (26 ao fim
        # do treino) antes de a troca o limpar.
        self.assertIn("clearInterval(window.__quadrosRelogio)", troca)
        self.assertIn("window.__quadrosRelogio = relogio", js)

    def test_o_pulso_de_35_ms_e_um_ouvinte_so_por_pagina(self):
        js = _sem_comentarios(self._tela())
        pulso = js.split("navigator.vibrate(35)")[0]
        self.assertIn("if (!window.__pulsoDaSerie)", pulso[-700:],
                      "o script mora no <main> e é recriado a cada troca: sem a guarda, um pulso por série acumulada")
