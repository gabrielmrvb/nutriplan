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
        html = self.client.get(reverse("plans:alimentacao")).content.decode()
        self.assertIn("data-busca-alimento", html)
        self.assertIn("data-busca-vazio", html)
        # A região do aviso mora DENTRO do bloco do campo: é o que a põe no
        # card da refeição em vez da faixa de mensagens do topo.
        bloco = html.split("data-busca-alimento", 1)[1].split("</div>")[0]
        self.assertIn("data-busca-vazio", html.split("data-busca-alimento", 1)[1][:2000])
        self.assertIn("data-busca-campo", bloco)

    def test_a_tela_oferece_registrar_sem_caloria_no_proprio_javascript(self):
        """A frase é escrita por `pwa.js` na região ao lado do campo. O que se
        cobra aqui é que a SAÍDA esteja dita — "registrar assim mesmo" — e não
        só o "não encontramos", que é constatação sem porta."""
        from pathlib import Path
        from django.conf import settings

        js = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(
            encoding="utf-8"
        )
        bloco = js.split("BUSCA DE ALIMENTO", 1)[1]
        # A frase é montada em pedaços de linha no JavaScript, então a busca é
        # sobre o texto com as quebras e a concatenação achatadas.
        corrido = re.sub(r'["\s+]+', " ", bloco)
        self.assertIn("registrar assim mesmo", corrido)
        self.assertIn("sem contar a caloria deste item", corrido)

    def test_o_datalist_de_todos_os_nomes_saiu_da_pagina(self):
        """Com a TACO, ele seriam ~20 kB de `<option>` nesta tela em toda
        visita — e ele casava por prefixo do nome inteiro, que é o que não
        achava "requeijao"."""
        html = self.client.get(reverse("plans:alimentacao")).content.decode()
        self.assertNotIn("<datalist", html)
        self.assertNotIn("alimentos-do-catalogo", html)
