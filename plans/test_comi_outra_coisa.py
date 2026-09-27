# -*- coding: utf-8 -*-
"""A busca de "comi outra coisa": prefixo, sem acento, e a saída quando não acha.

O item 3 da missão "quem entra não desiste" pede quatro coisas medíveis, e
cada uma tem a sua classe aqui:

- busca por PREFIXO e SEM ACENTO (`ABuscaAchaOQueFoiDigitadoTests`);
- autocomplete de verdade — mínimo de duas letras, até oito sugestões
  (`OContratoDoEndpointTests`);
- o aviso de não encontrado AO LADO DO CARD, oferecendo registrar sem caloria
  (`OAvisoFicaNoCardTests`);
- e o que estava quebrado e é a razão de tudo isto: o nome digitado sem acento
  não casava, e a refeição entrava com zero caloria
  (`ORegistroCasaOQueFoiDigitadoTests`).

`plans/test_outra_coisa_datalist.py` era o guarda do `<datalist>` e do defeito
#102 ("62 `value=` vazios em produção"). O `<datalist>` saiu; o defeito que ele
descrevia — a tela sugerir nomes VAZIOS — continua guardado, agora sobre o
endpoint, em `test_a_sugestao_nunca_devolve_nome_vazio`.
"""
import re
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalog import busca
from catalog.models import Food, FoodSource
from plans.models import MealLog, MealStatus
from plans.tests import create_complete_user


class OContratoDoEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_taco", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="busca@exemplo.com")
        self.client.force_login(self.user)
        self.url = reverse("plans:buscar_alimento")

    def _itens(self, q):
        resposta = self.client.get(self.url, {"q": q})
        self.assertEqual(resposta.status_code, 200)
        return resposta.json()["itens"]

    def test_uma_letra_nao_busca(self):
        """"a" devolveria as primeiras oito de centenas de linhas — uma lista
        que não responde ao que a pessoa está escrevendo."""
        self.assertEqual(self._itens("a"), [])
        self.assertEqual(self._itens(""), [])

    def test_duas_letras_ja_buscam(self):
        self.assertTrue(self._itens("ov"))

    def test_no_maximo_oito_sugestoes(self):
        """"carne" casa com dezenas de linhas da TACO."""
        for termo in ("carne", "frango", "queijo", "arroz"):
            with self.subTest(termo=termo):
                self.assertLessEqual(len(self._itens(termo)), 8)

    def test_a_sugestao_nunca_devolve_nome_vazio(self):
        """O defeito #102 (21/09/2026) numa forma nova: a tela sugeria 62
        `value=""` porque lia `food.name` de uma lista de strings. Aqui o nome
        é sempre o nome, e o número é sempre um número."""
        for item in self._itens("ban"):
            self.assertTrue(item["nome"].strip())
            self.assertIsInstance(item["kcal"], int)

    def test_o_prefixo_vem_antes_do_contem(self):
        """Quem digita "carne" quer "Carne, bovina..." antes de "Sopa de carne
        com legumes" — é o que a pessoa está escrevendo."""
        itens = self._itens("carne")
        nomes = [i["nome"] for i in itens]
        prefixos = [n for n in nomes if busca.normalizar(n).startswith("carne")]
        self.assertTrue(prefixos)
        self.assertEqual(nomes[: len(prefixos)], prefixos)

    def test_anonimo_nao_busca(self):
        """É dado do app, e a rota não está em `ROTAS_PUBLICAS`."""
        self.client.logout()
        resposta = self.client.get(self.url, {"q": "arroz"})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("entrar", resposta["Location"])

    def test_a_resposta_nao_vira_cache_publico(self):
        """A rota exige sessão: um proxy não pode guardar a resposta e servi-la
        a outra pessoa. A sugestão é igual para todos, mas o caminho é
        autenticado, e isso é o que a diretiva descreve."""
        resposta = self.client.get(self.url, {"q": "arroz"})
        self.assertIn("private", resposta["Cache-Control"])


class ABuscaAchaOQueFoiDigitadoTests(TestCase):
    """A camada de baixo, sem HTTP: `catalog.busca`."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_taco", verbosity=0)

    def test_sem_acento_acha_com_acento(self):
        """No teclado do celular, o acento é o que ninguém digita."""
        pares = [
            ("feijao", "feij"),
            ("acai", "aça"),
            ("pao", "pão"),
            ("acucar", "açúcar"),
            ("mamao", "mam"),
            ("abobora", "abóbora"),
        ]
        for digitado, esperado_em in pares:
            with self.subTest(digitado=digitado):
                nomes = [f.name.lower() for f in busca.sugerir(digitado)]
                self.assertTrue(nomes, digitado)
                self.assertTrue(
                    any(esperado_em in n for n in nomes),
                    "%s -> %s" % (digitado, nomes),
                )

    def test_maiuscula_nao_importa(self):
        self.assertTrue(list(busca.sugerir("ARROZ")))
        self.assertTrue(list(busca.sugerir("ArRoZ")))

    def test_o_nome_invertido_da_tabela_e_alcancavel(self):
        """A TACO escreve "Queijo, requeijão, cremoso". Quem digita
        "requeijao" não acharia isso por prefixo — é por essa razão que a busca
        tem o ramo "contém"."""
        nomes = [f.name.lower() for f in busca.sugerir("requeijao")]
        self.assertTrue(any("requeij" in n for n in nomes), nomes)

    def test_termo_que_nao_existe_devolve_vazio_e_nao_erro(self):
        self.assertEqual(list(busca.sugerir("xxxyyzz")), [])

    def test_alimento_desativado_nao_e_sugerido(self):
        """Aposentado continua no banco pelo histórico de quem já comeu, e não
        pode voltar pela porta da sugestão."""
        food = Food.objects.filter(is_active=True).first()
        termo = busca.normalizar(food.name)[:6]
        self.assertIn(food.pk, [f.pk for f in busca.sugerir(termo, limite=50)])
        Food.objects.filter(pk=food.pk).update(is_active=False)
        self.assertNotIn(food.pk, [f.pk for f in busca.sugerir(termo, limite=50)])


class ORegistroCasaOQueFoiDigitadoTests(TestCase):
    """O fim da linha: a refeição entra COM caloria.

    Era aqui que o achado das personas doía. `_itens_descritos` casava por
    `casefold()` sem tirar o acento, então "feijao" não achava "Feijão" e
    `macros_de_itens` devolvia zero — a refeição ficava registrada e o dia não
    mexia um número.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_taco", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="registro-fora@exemplo.com")
        self.client.force_login(self.user)
        from plans import services

        self.plano, _ = services.sync_active_plan(self.user)
        self.slot = self.plano.slots.order_by("time").first()

    def _registrar(self, alimento, gramas="100"):
        return self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {
                "status": MealStatus.OFF_PLAN,
                "notes": "comi na rua",
                "alimento": alimento,
                "gramas": gramas,
            },
        )

    def _log(self):
        return MealLog.objects.get(user=self.user, slot=self.slot)

    def test_sem_acento_o_dia_conta(self):
        alvo = Food.objects.filter(busca="arroz, integral, cozido").first()
        if alvo is None:  # pragma: no cover - a tabela mudou
            self.skipTest("a linha de arroz integral saiu da TACO")
        self.assertEqual(self._registrar("Arroz, integral, cozido").status_code, 302)
        self.assertGreater(self._log().kcal, 0)

    def test_com_o_nome_digitado_sem_acento_nenhum(self):
        """O caso exato da persona: o nome inteiro sem acento."""
        Food.objects.create(
            name="Feijão de teste",
            kcal=Decimal("100"),
            protein_g=Decimal("6"),
            carb_g=Decimal("18"),
            fat_g=Decimal("0.5"),
            source=FoodSource.MANUAL,
        )
        self.assertEqual(self._registrar("feijao de teste", "200").status_code, 302)
        self.assertEqual(self._log().kcal, Decimal("200.00"))

    def test_nome_que_nao_existe_registra_e_avisa(self):
        """A refeição entra pela descrição; o que fica de fora é a caloria
        daquela linha. Recusar a refeição inteira por uma linha mal digitada é
        o caminho mais curto para a pessoa parar de registrar."""
        resposta = self._registrar("bolo da vovó xyz", "150")
        self.assertEqual(resposta.status_code, 302)
        log = self._log()
        self.assertEqual(log.status, MealStatus.OFF_PLAN)
        self.assertEqual(log.kcal, 0)

    def test_duas_grafias_do_mesmo_alimento_somam_numa_linha(self):
        """"Arroz branco cozido" e "arroz branco cozido" são a mesma linha do
        catálogo escrita duas vezes, e o registro soma as duas — é o que o teto
        de gramas mede, e o que a chave normalizada garante.

        Com `casefold` sem tirar acento, "Feijão" e "feijao" eram chaves
        diferentes e a soma não somava.
        """
        from django.http import QueryDict

        from plans.views import _itens_descritos

        dados = QueryDict(mutable=True)
        dados.setlist("alimento", ["Arroz branco cozido", "arroz branco cozido"])
        dados.setlist("gramas", ["100", "200"])
        itens = _itens_descritos(dados)
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0][1], Decimal("300"))


class OAvisoFicaNoCardTests(TestCase):
    """O aviso de "não encontramos" nasce ao lado do campo, e não no topo."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_taco", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="aviso@exemplo.com")
        self.client.force_login(self.user)

    def test_o_campo_tem_a_regiao_do_aviso_dentro_do_card(self):
        """A região do aviso mora DENTRO do bloco de CADA campo — é o que a põe
        no card da refeição em vez da faixa de mensagens do topo.

        POR BLOCO (revisão do PR #162): a versão anterior media PROXIMIDADE em
        bytes (`[:2000]`), e com três blocos de menos de 1 kB cada ela achava
        a região do bloco seguinte quando a de um faltava. Aqui cada bloco é
        recortado até o início do próximo, e cada um tem de ter as três marcas.
        """
        html = self.client.get(reverse("plans:alimentacao")).content.decode()
        pedacos = html.split("data-busca-alimento")[1:]
        self.assertGreater(len(pedacos), 0, "nenhum campo de busca na tela")
        for i, pedaco in enumerate(pedacos):
            # O fim do bloco é o `name="gramas"` dele, que vem DEPOIS do
            # envoltório `.busca` (onde moram o campo, a lista e o aviso).
            bloco = pedaco.split('name="gramas"', 1)[0]
            with self.subTest(bloco=i):
                self.assertIn("data-busca-campo", bloco)
                self.assertIn("data-busca-lista", bloco)
                self.assertIn("data-busca-vazio", bloco)
                # SEMPRE na árvore: região `aria-live` com `hidden` só é
                # anunciada pela inserção, e isso os leitores não fazem direito.
                regiao = bloco.split("data-busca-vazio", 1)[0].rsplit("<p", 1)[1]
                self.assertNotIn("hidden", regiao)

    def test_a_tela_oferece_registrar_sem_caloria_no_proprio_javascript(self):
        """A frase é escrita por `pwa.js` na região ao lado do campo. O que se
        cobra aqui é que a SAÍDA esteja dita — "registrar assim mesmo" — e não
        só o "não encontramos", que é constatação sem porta."""
        from pathlib import Path
        from django.conf import settings

        from config.estaticos import sem_comentarios

        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(
            encoding="utf-8"
        )
        # SEM COMENTÁRIOS (revisão do PR #162): o comentário do próprio bloco
        # diz "a saída dita: registrar assim mesmo", e satisfazia a asserção —
        # reescrever a MENSAGEM para "Registre assim mesmo" ficava verde. A
        # âncora também é código: "BUSCA DE ALIMENTO" só existe em comentário.
        js = sem_comentarios(js)
        self.assertIn("[data-busca-alimento]", js)
        bloco = js.split("[data-busca-alimento]", 1)[1]
        # A frase é montada em pedaços de linha no JavaScript, então a busca é
        # sobre o texto com as quebras e a concatenação achatadas.
        corrido = re.sub(r'["\s+]+', " ", bloco)
        self.assertIn("registrar assim mesmo", corrido)
        self.assertIn("sem contar a caloria deste item", corrido)

    def test_o_formulario_aberto_nao_faz_a_pagina_rolar_na_horizontal(self):
        """ACHADO DO QA DE NAVEGADOR (26/09/2026), medido a 390 px.

        `.meal__secundarias .fora` era `flex: 1 0 auto`. Com `flex-shrink: 0` o
        item nunca encolhe abaixo do conteúdo — e `min-width: 0` NÃO muda isso,
        porque ele só libera o limite automático; quem proíbe encolher é o
        shrink. Aberto o "Comi outra coisa", a largura natural do campo "O que
        você comeu?" (~539 px) virava a largura do `<details>`: 568 px dentro de
        um container de 293, e `scrollWidth` ia de 375 para 609 — a PÁGINA
        rolando na horizontal.

        A asserção é sobre o CSS porque a suíte não tem motor de layout; a
        medição está no relatório e no comentário da regra. O que se prende aqui
        é a causa: aquele item não pode voltar a ter shrink zero.
        """
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        from config.estaticos import sem_comentarios

        css = sem_comentarios(css)
        regras = css.split(".meal__secundarias .fora {")[1:]
        self.assertTrue(regras, "a regra do `.fora` no rodapé da refeição saiu")
        erro = (
            "o `.fora` aberto voltou a ter flex-shrink 0 — a página rola na "
            "horizontal a 390 px (medido: scrollWidth 609 numa janela de 390)"
        )
        for regra in regras:
            corpo = regra.split("}", 1)[0]
            declaracoes = {
                chave.strip(): valor.strip()
                for chave, _, valor in (
                    d.partition(":") for d in corpo.split(";") if ":" in d
                )
            }
            # O ATALHO: `flex: <grow> <shrink> <basis>`. Com UM número só
            # (`flex: 1`) o shrink é 1 — que é o certo, e a versão anterior
            # desta guarda reprovava.
            atalho = declaracoes.get("flex", "").split()
            if len(atalho) >= 2:
                self.assertNotEqual(atalho[1], "0", erro)
            # A LONGHAND: `flex-shrink: 0` ao lado do atalho escapava da versão
            # anterior, que só lia o segundo token do atalho (revisão do PR
            # #162, sabotagem executada pelo revisor de testes).
            self.assertNotEqual(declaracoes.get("flex-shrink"), "0", erro)
            # E `min-width` que TRAVA o encolhimento pelo conteúdo é o mesmo
            # defeito por outra porta.
            self.assertNotIn(
                declaracoes.get("min-width"), ("fit-content", "max-content", "min-content"), erro
            )

    def test_aberto_o_formulario_nao_recorta_a_lista_de_sugestoes(self):
        """BUG (revisor de UI, confirmado na captura do QA a 390 px): quatro das
        oito sugestões visíveis, a lista cortada na borda do formulário.
        `.fora__interno` tem `overflow: hidden` para esconder o formulário com a
        linha em `0fr` — e isso recortava a lista `position: absolute`, que mora
        num descendente dele. Aberto, o recorte tem de sair."""
        from pathlib import Path

        from django.conf import settings

        from config.estaticos import sem_comentarios

        css = sem_comentarios(
            (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
        )
        regra = css.split(".fora[open] .fora__interno {", 1)
        self.assertEqual(len(regra), 2, "sumiu a regra que desliga o recorte com o <details> aberto")
        self.assertIn("overflow: visible", regra[1].split("}", 1)[0])
        # CONTROLE POSITIVO: o recorte do FECHADO continua — é ele que esconde
        # o formulário quando a linha da grade é `0fr`.
        self.assertIn(".fora__interno { overflow: hidden; }", css)

    def test_o_endereco_da_busca_vem_do_servidor(self):
        """BUG (revisor de Django): o `fetch` tinha `/alimentos/buscar/` escrito
        à mão, e sob `/demo/` ele saía do prefixo, caía anônimo no login e a
        busca morria calada na vitrine do produto."""
        html = self.client.get(reverse("plans:alimentacao")).content.decode()
        self.assertIn('data-busca-url="%s"' % reverse("plans:buscar_alimento"), html)

    def test_o_javascript_nao_escreve_o_endereco_a_mao(self):
        from pathlib import Path

        from django.conf import settings

        from config.estaticos import sem_comentarios

        js = sem_comentarios(
            (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        )
        self.assertNotIn('"/alimentos/buscar/', js)
        self.assertIn('getAttribute("data-busca-url")', js)

    def test_as_opcoes_seguem_o_padrao_de_combobox(self):
        """UX REAL (revisor de UI): `role="listbox"` com `<li>` no meio deixava
        o listbox sem opção (axe `aria-required-children`); as opções
        focáveis roubavam o Tab do campo; o aviso ligava `hidden` DEPOIS de
        escrever o texto, e a região `aria-live` não era anunciada; e o toque
        numa sugestão tirava o foco do campo no Safari antes do `click`."""
        from pathlib import Path

        from django.conf import settings

        from config.estaticos import sem_comentarios

        js = sem_comentarios(
            (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        )
        bloco = js.split('closest("[data-busca-alimento]")', 1)[1]
        self.assertIn('li.setAttribute("role", "presentation")', bloco)
        self.assertIn("botao.tabIndex = -1", bloco)
        avisar = bloco.split("function avisar", 1)[1].split("function ", 1)[0]
        self.assertNotIn("hidden", avisar)
        self.assertIn('addEventListener("mousedown"', bloco)
        # O cache é declarado ANTES das funções do bloco, no topo do IIFE.
        topo = js.split("var ESPERA_MS", 1)[1].split("function bloco", 1)[0]
        self.assertIn("Object.create(null)", topo)

    def test_o_datalist_de_todos_os_nomes_saiu_da_pagina(self):
        """Com a TACO, ele seriam ~20 kB de `<option>` nesta tela em toda
        visita — e ele casava por prefixo do nome inteiro, que é o que não
        achava "requeijao"."""
        html = self.client.get(reverse("plans:alimentacao")).content.decode()
        self.assertNotIn("<datalist", html)
        self.assertNotIn("alimentos-do-catalogo", html)
