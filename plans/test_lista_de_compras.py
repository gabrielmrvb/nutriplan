"""A lista de compras: o que se compra, a opção certa, e sem precisão fingida.

Três perguntas, e este arquivo responde as três com medição:

  - **forma de compra** — arroz cozido vira arroz cru, ovo vira unidade, atum
    vira lata. A conversão mora em `plans/compra.py`, como DADO, e o teste
    percorre a tabela em vez de conferir caso a caso;
  - **A e B não se misturam** — a lista de uma opção não pode carregar o que
    só a outra usa, e trocar de opção não pode somar as duas;
  - **nada finge precisão** — toda conversão aproximada sai marcada, e nenhuma
    quantidade sai em notação científica.
"""
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from plans import compra, shopping
from plans.models import ItemDaListaMarcado
from plans.shopping import humanize, round_up


class AConversaoParaFormaDeCompraTests(SimpleTestCase):
    """Sem banco: a conversão é função pura sobre nome, quantidade e unidade."""

    def test_cozido_vira_CRU(self):
        """Arroz cozido não existe na prateleira."""
        texto, aproximado = compra.converter(
            "Arroz branco cozido", Decimal("2000"), "g"
        )

        self.assertIn("cru", texto)
        self.assertIn("800 g", texto)
        self.assertTrue(aproximado)

    def test_o_fator_de_cada_alimento_e_o_da_tabela(self):
        """A tabela é a fonte. Um fator escrito à mão no meio do código seria
        a mesma regra em dois lugares."""
        for nome, (fator, rotulo) in compra.FATOR_CRU.items():
            with self.subTest(alimento=nome):
                self.assertGreater(fator, 1, "cru pesa MENOS que cozido")
                self.assertLess(fator, 4, "fator absurdo: %s" % fator)
                self.assertTrue(rotulo, "sem rótulo de compra")

    def test_ovo_vira_unidade_e_duzia_quando_fecha(self):
        doze, _ = compra.converter("Ovo de galinha cozido", Decimal("600"), "g")
        catorze, _ = compra.converter("Ovo de galinha cozido", Decimal("700"), "g")

        self.assertEqual(doze, "1 dúzia de ovos")
        # "1 dúzia e meia" é pior de ler que "14 ovos", e arredondar para a
        # dúzia mandaria comprar o que não precisa.
        self.assertEqual(catorze, "14 ovos")

    def test_o_singular_e_o_plural_saem_certos(self):
        uma, _ = compra.converter("Banana prata", Decimal("90"), "g")
        varias, _ = compra.converter("Banana prata", Decimal("300"), "g")
        uma_lata, _ = compra.converter("Atum em água (drenado)", Decimal("100"), "g")
        latas, _ = compra.converter("Atum em água (drenado)", Decimal("300"), "g")

        self.assertEqual(uma, "1 banana")
        self.assertEqual(varias, "4 bananas")
        self.assertEqual(uma_lata, "1 lata")
        self.assertEqual(latas, "3 latas")

    def test_conserva_conta_pelo_conteudo_DRENADO(self):
        """A lista pede sardinha drenada, e é isso que a lata entrega. Comparar
        com o peso bruto mandaria comprar lata a menos."""
        texto, _ = compra.converter(
            "Sardinha em óleo (drenada)", Decimal("450"), "g"
        )

        self.assertEqual(texto, "4 latas")

    def test_arredonda_a_embalagem_para_CIMA(self):
        """Faltar no meio da semana custa mais que sobrar."""
        texto, _ = compra.converter("Pão de forma integral", Decimal("501"), "g")

        self.assertEqual(texto, "2 pacotes")

    def test_quantidade_minuscula_ainda_pede_UMA_embalagem(self):
        """Zero latas seria uma lista que manda não comprar o que a receita usa."""
        texto, _ = compra.converter("Atum em água (drenado)", Decimal("5"), "g")

        self.assertEqual(texto, "1 lata")

    def test_quem_se_vende_por_PESO_continua_em_peso(self):
        """A conversão é a exceção, não a regra."""
        texto, aproximado = compra.converter("Tomate", Decimal("850"), "g")

        self.assertEqual(texto, "850 g")
        self.assertFalse(aproximado)

    def test_toda_conversao_sai_MARCADA_como_aproximada(self):
        """Fator de cozimento varia com a água e a panela; lata varia de marca.
        O que a tela não pode fazer é imprimir número exato que ninguém mediu.
        """
        for nome in list(compra.FATOR_CRU) + list(compra.POR_UNIDADE) + list(
            compra.EMBALAGEM
        ):
            with self.subTest(alimento=nome):
                _texto, aproximado = compra.converter(nome, Decimal("500"), "g")
                self.assertTrue(aproximado)


class NenhumaQuantidadeSaiEmNotacaoCientificaTests(SimpleTestCase):
    """A armadilha que a lista já pagou: "5.0E+2 g de macarrão (cru)".

    `to_integral_value()` devolve `Decimal`, e `Decimal` com expoente imprime em
    notação científica. A varredura cobre inteiro, fracionário, grande e
    pequeno — os quatro formatos em que o defeito pode voltar.
    """

    VALORES = [
        Decimal("1"),
        Decimal("50"),
        Decimal("500"),
        Decimal("5.0E+2"),
        Decimal("1000"),
        Decimal("1E+3"),
        Decimal("1200"),
        Decimal("10000"),
        Decimal("1E+4"),
        Decimal("100000"),
        Decimal("2500.5"),
        Decimal("0.5"),
    ]

    def test_humanize_nunca_devolve_expoente(self):
        for valor in self.VALORES:
            for unidade in ("g", "ml"):
                with self.subTest(valor=str(valor), unidade=unidade):
                    self.assertNotIn("E+", humanize(valor, unidade))
                    self.assertNotIn("e+", humanize(valor, unidade))

    def test_a_conversao_tambem_nao_devolve_expoente(self):
        nomes = ["Arroz branco cozido", "Macarrão cozido", "Tomate"]
        for nome in nomes:
            for valor in self.VALORES:
                with self.subTest(alimento=nome, valor=str(valor)):
                    texto, _ = compra.converter(nome, round_up(valor), "g")
                    self.assertNotIn("E+", texto)

    def test_o_controle_positivo_o_defeito_EXISTIA(self):
        """Sem isto, a varredura acima poderia estar medindo um formato que
        nunca produziria expoente — e passaria sem provar nada."""
        cru = Decimal("1200") / Decimal("2.4")

        self.assertIn("E+", str(cru.to_integral_value()))
        self.assertNotIn("E+", humanize(cru, "g"))


class AsOpcoesAeBNaoSeMisturamTests(TestCase):
    """Uma opção por refeição por dia. Somar as duas encheria a lista de comida
    que ninguém vai cozinhar, e o primeiro efeito de uma lista inflada é a
    pessoa parar de confiar nela."""

    fixtures = []

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        from plans.tests import create_complete_user
        from plans import services

        self.user = create_complete_user(email="lista@exemplo.com")
        self.plan = services.create_plan(self.user)

    def _itens(self, label):
        return {
            item["food"].name: item["display"]
            for corredor in shopping.shopping_list(self.plan, label=label)
            for item in corredor["items"]
        }

    def test_as_duas_listas_sao_DIFERENTES(self):
        """Controle positivo de tudo o mais neste teste: se A e B fossem
        idênticas, "não se misturam" passaria sem medir nada."""
        a, b = self._itens("A"), self._itens("B")

        self.assertNotEqual(a, b, "A e B produziram a MESMA lista")

    def test_trocar_de_opcao_nao_SOMA_as_duas(self):
        """O defeito que a separação impede: sair do mercado com o dobro."""
        a, b = self._itens("A"), self._itens("B")
        juntas = self._itens(None)

        self.assertLessEqual(len(juntas), max(len(a), len(b)))

    def test_a_lista_cobre_SETE_dias(self):
        self.assertEqual(shopping.DAYS, 7)
        self.assertEqual(len(shopping.dias_da_semana()), 7)

    def test_ingrediente_repetido_e_somado_uma_linha_so(self):
        """Normalização: o mesmo alimento em três receitas vira uma linha com a
        soma, não três linhas."""
        nomes = [
            item["food"].name
            for corredor in shopping.shopping_list(self.plan, label="A")
            for item in corredor["items"]
        ]

        self.assertEqual(
            len(nomes), len(set(nomes)), "alimento repetido em duas linhas"
        )

    def test_cada_item_diz_de_QUAIS_receitas_veio(self):
        """A rastreabilidade que justifica a soma: se a linha junta três
        receitas, ela precisa dizer quais."""
        for corredor in shopping.shopping_list(self.plan, label="A"):
            for item in corredor["items"]:
                with self.subTest(alimento=item["food"].name):
                    self.assertTrue(item["recipes"])


class AMarcacaoSOBREVIVEAoRecarregamentoTests(TestCase):
    """A tela avisava que a marcação valia "só enquanto a página estiver
    aberta". Quem recarregava no meio do corredor perdia tudo o que já pegou —
    e esta é justamente a tela que se usa andando pelo mercado.
    """

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        from plans.tests import create_complete_user
        from plans import services

        self.user = create_complete_user(email="marcacao@exemplo.com")
        self.plan = services.create_plan(self.user)
        self.client.force_login(self.user)
        self.semana = shopping.dias_da_semana()[0]
        self.alimento = self._primeiro_alimento("A")

    def _primeiro_alimento(self, label):
        for corredor in shopping.shopping_list(self.plan, label=label):
            for item in corredor["items"]:
                return item["food"]
        raise AssertionError("a lista %s nasceu vazia" % label)

    def _marcar(self, food, marcado="1", opcao="A", semana=None):
        from django.urls import reverse

        return self.client.post(
            reverse("plans:marcar_item"),
            {
                "food_id": food.pk,
                "opcao": opcao,
                "semana": str(semana or self.semana),
                "marcado": marcado,
            },
        )

    def _marcados(self, label="A"):
        from django.urls import reverse

        url = reverse("plans:shopping") + "?opcao=" + label
        resposta = self.client.get(url)
        return {
            item["food"].id
            for corredor in resposta.context["aisles"]
            for item in corredor["items"]
            if item["marcado"]
        }

    def test_marcar_e_recarregar_mantem_o_risco(self):
        self._marcar(self.alimento)

        self.assertIn(self.alimento.id, self._marcados())

    def test_desmarcar_tambem_persiste(self):
        self._marcar(self.alimento)
        self._marcar(self.alimento, marcado="0")

        self.assertNotIn(self.alimento.id, self._marcados())

    def test_marcar_DUAS_vezes_e_o_mesmo_que_uma(self):
        """Estado absoluto, nunca alternância: a fila offline reenvia, e um
        "alterne" reproduzido desfaz o que a pessoa fez."""
        self._marcar(self.alimento)
        self._marcar(self.alimento)

        self.assertEqual(
            ItemDaListaMarcado.objects.filter(user=self.user).count(), 1
        )
        self.assertIn(self.alimento.id, self._marcados())

    def test_a_marcacao_de_A_nao_vaza_para_B(self):
        """A e B compram coisas diferentes. Riscar o atum na lista A não pode
        aparecer riscado na B, que talvez nem tenha atum."""
        self._marcar(self.alimento, opcao="A")

        self.assertNotIn(self.alimento.id, self._marcados("B"))

    def test_a_marcacao_da_semana_passada_nao_volta(self):
        """Sem a data na chave, a lista da semana seguinte nasceria riscada."""
        from datetime import timedelta

        passada = self.semana - timedelta(days=7)
        self._marcar(self.alimento, semana=passada)

        self.assertNotIn(self.alimento.id, self._marcados())

    def test_a_marcacao_de_OUTRA_pessoa_nao_aparece(self):
        """Isolamento por usuário: a chave tem a pessoa, e a leitura filtra por
        ela. Sem isso, duas pessoas no mesmo aparelho veriam a lista uma da
        outra."""
        from plans.tests import create_complete_user
        from plans import services

        outra = create_complete_user(email="outra-lista@exemplo.com")
        services.create_plan(outra)
        ItemDaListaMarcado.objects.create(
            user=outra, food=self.alimento, opcao="A", semana=self.semana
        )

        self.assertNotIn(self.alimento.id, self._marcados())

    def test_quem_nao_entrou_nao_marca(self):
        """Autorização: a rota exige sessão como todas as outras que escrevem."""
        self.client.logout()

        resposta = self._marcar(self.alimento)

        self.assertNotEqual(resposta.status_code, 200)
        self.assertEqual(ItemDaListaMarcado.objects.count(), 0)

    def test_alimento_inexistente_da_404_e_nao_500(self):
        """Corpo corrompido merece 404, não página de erro."""
        from django.urls import reverse

        resposta = self.client.post(
            reverse("plans:marcar_item"),
            {"food_id": "abc", "opcao": "A", "semana": str(self.semana), "marcado": "1"},
        )

        self.assertEqual(resposta.status_code, 404)

    def test_alimento_que_saiu_do_cardapio_nao_reaparece_riscado(self):
        """Invalidação por construção: a marcação é lida pelo CRUZAMENTO com a
        lista de agora. Linha órfã fica no banco sem efeito — apagar em massa
        arriscaria o dado de quem só trocou de opção e vai voltar."""
        from catalog.models import Food

        fora = Food.objects.exclude(
            id__in=[
                item["food"].id
                for corredor in shopping.shopping_list(self.plan, label="A")
                for item in corredor["items"]
            ]
        ).first()
        ItemDaListaMarcado.objects.create(
            user=self.user, food=fora, opcao="A", semana=self.semana
        )

        marcados = self._marcados()

        self.assertNotIn(fora.id, marcados)
        self.assertTrue(
            ItemDaListaMarcado.objects.filter(food=fora).exists(),
            "a marcação órfã foi APAGADA em vez de ignorada",
        )


class OJavaScriptDaMarcacaoESERVIDOTests(TestCase):
    """A guarda que faltou, e que deixou passar um arquivo órfão.

    A primeira versão deste código foi para `static/js/app.js` — um arquivo que
    NÃO existia e que ninguém carrega: `app_js_url` aponta para `pwa.js`
    (`push/context_processors.py:19`), e a lista serve pwa, fila e card. O
    endpoint funcionava, os testes de persistência passavam, e a caixa não
    salvava nada no navegador.

    Testar o endpoint não prova a tela. Este teste fecha a distância: o código
    tem de estar num arquivo que a página realmente pede.
    """

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        from plans.tests import create_complete_user
        from plans import services

        self.user = create_complete_user(email="js-lista@exemplo.com")
        services.create_plan(self.user)
        self.client.force_login(self.user)

    def test_o_codigo_da_marcacao_vive_num_arquivo_que_a_pagina_carrega(self):
        from django.conf import settings
        from django.urls import reverse
        from pathlib import Path
        import re

        html = self.client.get(reverse("plans:shopping")).content.decode()
        carregados = set(re.findall(r'src="[^"]*/js/([a-z]+)\.', html))

        self.assertTrue(carregados, "a tela não carrega nenhum script próprio")

        raiz = Path(settings.BASE_DIR) / "static" / "js"
        tem_marcacao = {
            nome
            for nome in carregados
            if (raiz / f"{nome}.js").exists()
            and "data-lista-compras" in (raiz / f"{nome}.js").read_text(encoding="utf-8")
        }
        self.assertTrue(
            tem_marcacao,
            "o código da marcação não está em nenhum script que a tela carrega: "
            "carregados=%s" % sorted(carregados),
        )

    def test_a_tela_publica_o_endereco_para_o_script(self):
        """O endereço vem do `{% url %}` e não escrito no JavaScript: o demo
        serve esta tela sob outro prefixo, e um caminho fixo quebraria lá em
        silêncio."""
        from django.urls import reverse

        html = self.client.get(reverse("plans:shopping")).content.decode()

        self.assertIn('data-lista-compras="%s"' % reverse("plans:marcar_item"), html)
