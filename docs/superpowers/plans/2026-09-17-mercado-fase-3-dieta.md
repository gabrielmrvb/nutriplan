# Padrões de mercado — Fase 3 (dieta) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O cardápio vira cozinhável (medida caseira em toda quantidade, café que não escala acima de 1,5×) e comprável (mínimo de compra e fator cru para todo alimento de receita ativa); pesar dentro de ±1,5 kg não regenera o cardápio; "Cortar 150 kcal" só para quem quer perder.

**Architecture:** Dado novo em `FoodPortion` (`singular`/`plural`, do JSON), função pura `plans/porcoes.medida_caseira`, e `ingredient_list()` entregando a medida ao template. `compra.py` ganha `MINIMO_DE_COMPRA` e fatores crus, com um teste-régua que varre todo alimento de receita ativa. `plan_is_current` tolera 1,5 kg sem editar o plano. `weight_trend.analisar` decide a sugestão pelo `goal` e a view ganha a ação simétrica.

**Tech Stack:** Django 5.2, PostgreSQL, JSON de catálogo + `seed_catalog`, templates, `RunnerUnico`.

**Spec:** `docs/superpowers/specs/2026-09-17-mercado-fase-3-dieta-design.md`

## Global Constraints

- **Não tocar** `workouts/test_ficha_de_verdade.py`, `workouts/test_treino_md.py`, `workouts/test_corrida_md.py`, `api/*`, `achievements/*`, nem `plans/tests.py::ScalingTests::test_scale_is_clamped_to_edible_portions` (`MAX_SCALE` continua 2,5).
- **Plano é retrato:** nunca editar os números de um plano ativo; a tolerância decide se NASCE plano novo, nada mais.
- Números com vírgula (`floatformat`), `ROUND_HALF_UP` (a regra única do app, `plans/tracking.py`), pt-BR, docstrings dizem POR QUÊ com o caso real (a avaliação de 16/09: "Aveia 116 g", "Repolho 40 g", "Cortar 150 kcal" para quem ganha massa, pesar recalcula).
- Banco de teste PRIVADO: `test_nutriplan_dieta` (`.env` aponta para `nutriplan_dieta`). `.venv/Scripts/python.exe manage.py test <modulos> --noinput` da raiz, **em primeiro plano**. Nunca `pg_terminate_backend`, nunca `NUTRIPLAN_IGNORAR_RUNNER_UNICO`, nunca a suíte inteira dentro de uma tarefa.
- Catálogo: mudança em `catalog/data/*.json` exige rodar `seed_catalog` no teste (os fixtures já fazem — ver `plans/tests.py::CatalogFixture`) e o commit diz o que mudou por alimento.
- Commits pt-BR com o caso real; pre-commit; nunca `--no-verify`; Edit/Write (heredoc altera barras).

---

## Propriedade de arquivos

| tarefa | edita | ordem |
|---|---|---|
| T1 | `catalog/models.py` (FoodPortion) + migração, `catalog/data/foods.json` (85 porções: singular/plural), `catalog/management/commands/seed_catalog.py`, novo `plans/porcoes.py`, `plans/models.py::MealOption.ingredient_list`, `plans/views.py` (prefetch `__portions`), `templates/plans/today.html` (~l. 637), novos `catalog/test_porcoes.py`, `plans/test_cardapio_cozinhavel.py` (parte 3.1) | 1ª |
| T2 | `catalog/data/meal_templates.json` (16 cafés), `plans/test_cardapio_cozinhavel.py` (parte café ≤1,5×) | 2ª (depois de T1: mesmo teste) |
| T3 | `plans/compra.py`, `plans/shopping.py` (se precisar do food para o mínimo), `templates/plans/shopping.html` (só se o texto exigir), novo `plans/test_lista_compravel.py`, `plans/test_lista_de_compras.py` (ajustes) | 3ª |
| T4 | `plans/services.py::plan_is_current`, `plans/weight_trend.py`, `plans/views.py::RecalibrateView`, `templates/plans/_peso.html`, `plans/test_peso_tolerante.py` (novo), `plans/test_weight_trend.py`, `plans/tests.py` (só os casos que a tolerância muda) | 4ª |

---

### Task 1: Medida caseira em toda quantidade do cardápio

**Files:** ver tabela. **Interfaces produzidas:** `FoodPortion.singular`, `FoodPortion.plural` (CharField 60, `blank=True`); `plans.porcoes.medida_caseira(quantidade_g, porcao) -> tuple[str, str] | None` (número formatado com vírgula e o rótulo, ex. `("7,5", "colheres de sopa")`); `ingredient_list()` item ganha `"caseira": ("7,5", "colheres de sopa") | None`.

- [ ] **Step 1: Ler** `catalog/models.py::FoodPortion`, `catalog/data/foods.json` (as porções: l. ~3–12 e adiante), `seed_catalog.py` l. ~96–104, `plans/models.py::MealOption.ingredient_list` (~l. 189–203), `templates/plans/today.html` l. ~618–640, `plans/views.py` l. ~323 (prefetch), `plans/tests.py::IngredientListTests` (~l. 1988) e `CatalogFixture` (~l. 770), `plans/tracking.py` l. 47–49 (`ROUND_HALF_UP`).

- [ ] **Step 2: Testes que falham**

`catalog/test_porcoes.py`:
```python
# -*- coding: utf-8 -*-
"""Toda porção tem nome no singular e no plural — escritos, não derivados.

"Aveia 116 g" (avaliação de 16/09, B15) não é o que uma pessoa mede na cozinha;
"7,5 colheres de sopa" é. A porção já estava no banco e nunca era lida. O plural
é escrito no catálogo porque pt-BR não deriva "colher → colheres" por regra.
"""
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from catalog.models import FoodPortion
from plans.porcoes import medida_caseira


class OCatalogoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def test_toda_porcao_tem_singular_e_plural(self):
        vazias = [str(p) for p in FoodPortion.objects.all() if not p.singular or not p.plural]
        self.assertEqual(vazias, [])

    def test_o_rotulo_nao_carrega_numero(self):
        com_numero = [p.singular for p in FoodPortion.objects.all() if p.singular[0].isdigit() or p.singular.startswith("1/")]
        self.assertEqual(com_numero, [])


class AMedidaCaseiraTests(TestCase):
    def _porcao(self, gramas):
        return FoodPortion(grams=Decimal(gramas), singular="colher de sopa", plural="colheres de sopa")

    def test_arredonda_a_meio_com_virgula(self):
        self.assertEqual(medida_caseira(Decimal("116"), self._porcao(15)), ("7,5", "colheres de sopa"))
        self.assertEqual(medida_caseira(Decimal("30"), self._porcao(15)), ("2", "colheres de sopa"))

    def test_singular_quando_e_um(self):
        self.assertEqual(medida_caseira(Decimal("16"), self._porcao(15)), ("1", "colher de sopa"))

    def test_menos_de_meia_porcao_nao_vira_medida(self):
        self.assertIsNone(medida_caseira(Decimal("5"), self._porcao(15)))

    def test_meio_sobe(self):
        # 3,25 porções → 3,5 (ROUND_HALF_UP no meio-degrau), não 3
        self.assertEqual(medida_caseira(Decimal("48.75"), self._porcao(15))[0], "3,5")
```

`plans/test_cardapio_cozinhavel.py` (parte 3.1):
```python
# -*- coding: utf-8 -*-
"""O cardápio da Home diz a medida caseira, e a grama fica entre parênteses."""
import re

from django.test import TestCase
from django.urls import reverse

from plans.tests import CatalogFixture, create_complete_user  # ler os nomes reais


class AHomeMostraMedidaCaseiraTests(CatalogFixture, TestCase):
    def test_alimento_com_porcao_sai_como_medida_e_grama(self):
        user = create_complete_user()
        self.client.force_login(user)
        html = self.client.get(reverse("plans:today")).content.decode()
        # Um ingrediente com porção: "<b>7,5 colheres de sopa (116 g)</b>" — o número
        # exato depende do cardápio; a FORMA é o que se prova.
        self.assertRegex(html, r'class="option__ingrediente">[^<]+</span>\s*<b>[0-9]+(,[05])? [a-zç ]+ \([0-9]+ (g|ml)\)</b>')

    def test_alimento_sem_porcao_continua_em_grama(self):
        # Abobrinha/Repolho/Couve não têm porção: a linha é só "N g".
        ...  # montar um plano com uma receita que tenha um deles, ou afirmar no ingredient_list() direto:
```
(o implementador completa o segundo teste chamando `ingredient_list()` de um `MealOption` cujo template tenha um alimento sem porção — `CatalogFixture` cria receitas; ler como.)

- [ ] **Step 3: Rodar e ver falhar.**

- [ ] **Step 4: Modelo + JSON + seed** — `FoodPortion.singular = CharField(max_length=60, blank=True, default="")`, `plural` idem; migração `catalog/migrations/00XX_porcao_singular_plural.py`. Em `foods.json`, cada porção ganha `"singular"` e `"plural"` (85 entradas — escrever à mão, revisando gênero e número: "colher de sopa/colheres de sopa", "copo/copos", "unidade/unidades", "unidade média/unidades médias", "fatia/fatias", "ovo médio/ovos médios", "xícara/xícaras", "punhado/punhados", "tapioca média/tapiocas médias", "concha/conchas", "filé/filés", "posta/postas", "lata/latas", "pote/potes", "1/2 unidade" → singular "meia unidade", plural "meias unidades"). `seed_catalog.py` grava os dois campos no `update_or_create` (`defaults`).

- [ ] **Step 5: `plans/porcoes.py`**
```python
# -*- coding: utf-8 -*-
"""A medida caseira de uma quantidade: "7,5 colheres de sopa" para 116 g de aveia."""
from decimal import Decimal, ROUND_HALF_UP

MEIO = Decimal("0.5")


def _formatar(n):
    texto = ("%s" % n.normalize()).replace(".", ",")
    return texto[:-2] if texto.endswith(",0") else texto


def medida_caseira(quantidade_g, porcao):
    """`("7,5", "colheres de sopa")`, ou None quando não dá meia porção.

    Arredonda a MEIO pelo ROUND_HALF_UP do app (`plans/tracking.py`): 3,25
    porções viram 3,5, e 7,73 viram 7,5 — é o que uma colher consegue medir.
    Abaixo de meia porção a medida mentiria mais que a grama.
    """
    if porcao is None or not porcao.grams or not porcao.singular:
        return None
    n = (Decimal(quantidade_g) / Decimal(porcao.grams) / MEIO).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * MEIO
    if n < MEIO:
        return None
    rotulo = porcao.singular if n == 1 else porcao.plural
    return _formatar(n), rotulo
```

- [ ] **Step 6: `ingredient_list()` e template** — em `MealOption.ingredient_list`, para cada item: `porcao = next((p for p in item.food.portions.all() if p.is_default), None)` (com o prefetch `options__template__items__food__portions` na view, zero consulta a mais — conferir com o orçamento de `plans/test_stress.py`), `"caseira": medida_caseira(quantidade, porcao)`. Template l. ~637: `<b>{% if item.caseira %}{{ item.caseira.0 }} {{ item.caseira.1 }} ({{ item.quantity|floatformat:0 }} {{ item.unit }}){% else %}{{ item.quantity|floatformat:0 }} {{ item.unit }}{% endif %}</b>`.

- [ ] **Step 7: Verde, sabotagem, commit** — módulos: `catalog.test_porcoes plans.test_cardapio_cozinhavel plans.tests plans.test_stress`. Sabotagens: `MEIO` → `Decimal("1")` → `test_arredonda_a_meio` vermelho; apagar um `plural` no JSON → `test_toda_porcao…` vermelho; tirar o prefetch `__portions` → `test_stress` (teto da Home) vermelho. Commit: "Medida caseira em toda quantidade do cardápio: 7,5 colheres de sopa (116 g), não 116 g".

---

### Task 2: O café não escala acima de 1,5×

**Files:** `catalog/data/meal_templates.json` (os 16 `breakfast`), `plans/test_cardapio_cozinhavel.py` (classe nova).

- [ ] **Step 1: Ler** `plans/meal_planner.py::scale_for` (l. ~284–303), `DAY_BLUEPRINT` (l. ~127–133), os 16 cafés no JSON (`"slot": "breakfast"` ou equivalente), `plans/tests.py::create_complete_user` (~l. 388) e como montar o perfil de referência (homem, 30 a, 178 cm, 82,5 kg, `Goal.BULK`, `ActivityLevel.LIGHT`, 5 dias de treino → 2 859 kcal; conferir com `calculate`).

- [ ] **Step 2: Teste que falha**
```python
class OCafeNaoEscalaAcimaDeUmEMeioTests(CatalogFixture, TestCase):
    """"Aveia 116 g · Leite 462 ml" era a receita-base de 50 g/200 ml escalada 2,31×.

    A base dos cafés era pequena demais para o slot de 25 % de uma dieta de
    2 859 kcal (715 kcal). Subir a base mantém a proporção e deixa o fator
    perto de 1 — a receita continua parecendo uma receita.
    """
    def test_todo_cafe_fica_entre_0_7_e_1_5_no_perfil_de_referencia(self):
        from catalog.models import MealTemplate
        from plans.meal_planner import scale_for
        alvo = 715  # 25 % de 2 859 — o perfil da avaliação
        fora = []
        for t in MealTemplate.objects.filter(slot="breakfast", is_active=True):  # nome real do campo
            f = scale_for(t, alvo)
            if not (Decimal("0.7") <= f <= Decimal("1.5")):
                fora.append((t.name, f))
        self.assertEqual(fora, [])
```

- [ ] **Step 3: Recalibrar o JSON** — para cada café abaixo de 480 kcal escaláveis, subir as quantidades escaláveis proporcionalmente até a base escalável ficar em 480–540 kcal, arredondando a porções inteiras (aveia em múltiplos de 15 g, leite de 50 ml, pão em unidades/fatias, ovo em unidades, tapioca em múltiplos de 30 g). Manter itens não escaláveis (banana, mel) como estão. Anotar a tabela `receita | alimento | antes | depois` no relatório e no commit.

- [ ] **Step 4: Verde, sabotagem, commit** — `plans.test_cardapio_cozinhavel plans.tests` (SeedContentTests/MealGenerationTests podem citar quantidades antigas — ajustar só os números, dizendo no commit). Sabotagem: voltar a aveia do mingau a 50 g → vermelho. Commit: "O café escala no máximo 1,5× no perfil de referência: a base sobe, a proporção fica".

---

### Task 3: Lista de compras comprável

**Files:** `plans/compra.py`, `plans/shopping.py` (se `converter` passar a receber o `food`), `plans/test_lista_compravel.py` (novo), `plans/test_lista_de_compras.py` (ajustes de texto).

- [ ] **Step 1: Ler** `plans/compra.py` inteiro, `plans/shopping.py::shopping_list` (l. ~192–234), `plans/test_lista_de_compras.py`, `plans/test_quantidade_legivel.py`, `CLAUDE.md` l. ~1201–1207 (doutrina da lista).

- [ ] **Step 2: Teste-régua que falha** — `plans/test_lista_compravel.py`:
```python
# -*- coding: utf-8 -*-
"""Nenhum item da lista sai em fração de unidade de venda.

"Repolho 40 g", "Azeite 20 ml", "Café coado 300 ml" (avaliação de 16/09, B16)
não se compram. Todo alimento de receita ativa precisa de UMA forma de compra:
unidade, embalagem, mínimo de venda, ou cru em kg. Alimento novo sem forma
fica vermelho aqui.
"""
import re
from decimal import Decimal

from django.test import TestCase

from catalog.models import Food, MealTemplateItem
from plans import compra
from plans.tests import CatalogFixture

SOLTO = re.compile(r"^\d+(,\d+)? (g|ml)$")


class ARéguaDaCompraTests(CatalogFixture, TestCase):
    def test_todo_alimento_de_receita_ativa_tem_forma_de_compra(self):
        nomes = sorted({i.food.name for i in MealTemplateItem.objects.filter(template__is_active=True).select_related("food")})
        soltos = []
        for nome in nomes:
            texto, _ = compra.converter(nome, Decimal("40"), "g")
            if SOLTO.match(texto):
                soltos.append((nome, texto))
        self.assertEqual(soltos, [])

    def test_o_minimo_nunca_fraciona(self):
        self.assertEqual(compra.converter("Azeite de oliva extra virgem", Decimal("20"), "ml"), ("1 garrafa (500 ml)", True))
        self.assertEqual(compra.converter("Café coado sem açúcar", Decimal("300"), "ml"), ("1 pacote de café (250 g)", True))
        self.assertEqual(compra.converter("Repolho", Decimal("40"), "g"), ("1 unidade", True))

    def test_carne_sai_crua(self):
        self.assertEqual(compra.converter("Carne moída (patinho) refogada", Decimal("600"), "g")[0], "~800 g (cru)")  # 600×1,3=780 → degrau

    def test_a_banana_usa_a_porcao_do_catalogo(self):
        self.assertIn("banana", compra.converter("Banana prata", Decimal("210"), "g")[0])  # 3 bananas de 70 g
```
(ajustar textos ao que `converter`/`humanize` produzem de verdade; o que importa é a régua.)

- [ ] **Step 3: Implementar** — `MINIMO_DE_COMPRA` (tabela com docstring e a lista da avaliação como caso real), `FATOR_CRU` estendido (carnes 1,3–1,35, peixe 1,25, couve/espinafre 1,25–1,4, legumes cozidos 1,1), `POR_UNIDADE` lendo `FoodPortion` quando existir (a porção vence: banana 70 g), e `converter` com o passo do mínimo (`ROUND_CEILING` ao múltiplo). Sempre `aproximado=True` no mínimo.

- [ ] **Step 4: Verde, sabotagem, commit** — `plans.test_lista_compravel plans.test_lista_de_compras plans.test_lista_nome_e_quantidade plans.test_quantidade_legivel plans.tests`. Sabotagem: apagar "Repolho" de `MINIMO_DE_COMPRA` → a régua vermelha; mínimo do azeite → arredondar para baixo → `test_o_minimo_nunca_fraciona` vermelho. Commit: "A lista de compras vira comprável: mínimo de venda e fator cru para todo alimento de receita ativa".

---

### Task 4: Pesar não regenera; "Cortar 150" só para perda

**Files:** `plans/services.py::plan_is_current` (~l. 167–192), `plans/weight_trend.py::analisar` (~l. 167–203), `plans/views.py::RecalibrateView` (~l. 808–862), `templates/plans/_peso.html` (~l. 106–136), `plans/test_peso_tolerante.py` (novo), `plans/test_weight_trend.py`, `plans/tests.py` (só onde a tolerância muda o resultado).

- [ ] **Step 1: Ler** os quatro arquivos; `plans/tests.py` l. ~470–479 e ~1821, `GeracaoIdempotenteTests` (~l. 4311); `CLAUDE.md` l. 261–264 ("Plano é retrato").

- [ ] **Step 2: Testes que falham**

`plans/test_peso_tolerante.py`:
```python
# -*- coding: utf-8 -*-
"""Pesar +1 kg não troca o cardápio; +1,6 kg troca.

Avaliação de 16/09 (B17): qualquer peso novo invalidava o plano e
reescolhia A/B. O plano continua um RETRATO — nada nele é editado; a
tolerância só decide se nasce um novo. 1,5 kg movem a TMB em ~15 kcal,
menos que o degrau de 10 g do cardápio.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import WeightEntry
from plans import services
from plans.tests import CatalogFixture, create_complete_user

TOLERANCIA = Decimal("1.5")


class APesagemToleranteTests(CatalogFixture, TestCase):
    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)
        self.plano = services.get_active_plan(self.user)  # nome real
        self.hoje = timezone.localdate()

    def _pesar(self, peso):
        WeightEntry.objects.update_or_create(user=self.user, date=self.hoje, defaults={"weight_kg": Decimal(str(peso))})

    def _opcoes_de_hoje(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        return re.findall(r'class="option__nome">([^<]+)<', html)  # seletor real das opções A/B

    def test_um_quilo_a_mais_mantem_o_plano_e_o_cardapio(self):
        antes = self._opcoes_de_hoje()
        self._pesar(Decimal(self.plano.weight_kg) + 1)
        self.client.get(reverse("plans:today"))
        self.assertEqual(services.get_active_plan(self.user).pk, self.plano.pk)
        self.assertEqual(self._opcoes_de_hoje(), antes)

    def test_mais_de_um_e_meio_gera_plano_novo(self):
        self._pesar(Decimal(self.plano.weight_kg) + Decimal("1.6"))
        r = self.client.get(reverse("plans:today"))
        self.assertNotEqual(services.get_active_plan(self.user).pk, self.plano.pk)
        self.assertContains(r, "recalculamos")

    def test_o_plano_nao_e_editado(self):
        peso = self.plano.weight_kg
        self._pesar(Decimal(peso) + 1)
        self.client.get(reverse("plans:today"))
        self.plano.refresh_from_db()
        self.assertEqual(self.plano.weight_kg, peso)

    def test_recalcular_explicito_sempre_regenera(self):
        self._pesar(Decimal(self.plano.weight_kg) + 1)
        self.client.post(reverse("plans:recalibrar"), {"acao": "recalcular"})  # nome/ação reais
        self.assertNotEqual(services.get_active_plan(self.user).pk, self.plano.pk)
```

`plans/test_weight_trend.py` (estender `RecalibragemTests`):
```python
    def test_quem_ganha_massa_ouve_aumentar_nao_cortar(self):
        self.user.profile.goal = Goal.BULK; self.user.profile.save()
        self._tres_semanas_paradas()  # helper real (registrar_semana)
        self.assertEqual(analisar(self.user).sugestao, "aumentar")

    def test_quem_mantem_nao_ouve_nada(self):
        self.user.profile.goal = Goal.MAINTAIN; ...
        self.assertIsNone(analisar(self.user).sugestao)

    def test_a_view_aceita_aumentar_e_recusa_o_resto(self):
        ...  # POST acao=aumentar → kcal_adjustment +150; acao=inventada → 400/ignorada
```

- [ ] **Step 3: Implementar** — `plan_is_current(plan, inputs)`: se todas as entradas exceto `weight_kg` batem e `abs(plan.weight_kg − inputs.weight_kg) <= TOLERANCIA_DE_PESO_KG (1.5)` → `True` (sem comparar saídas); senão o caminho de hoje. Docstring com o caso real e a frase do retrato. `analisar` devolve `sugestao` (`"cortar"|"aumentar"|None`) mantendo `sugerir_recalibragem` como `bool(sugestao)` para quem já lê. `RecalibrateView`: `acao == "aumentar"` → `kcal_adjustment += AJUSTE_KCAL` com teto simétrico ao piso (ler `calculations.py` l. ~386–412 e espelhar). `_peso.html`: frase e botão por `sugestao` ("Sua média estabilizou — para ganhar massa, +150 kcal" / "…para perder, cortar 150 kcal"); nada quando `None`.

- [ ] **Step 4: Verde, sabotagem, commit** — `plans.test_peso_tolerante plans.test_weight_trend plans.tests plans.test_piso_em_todos_os_objetivos`. Ajustar em `plans/tests.py` só os testes cuja variação de peso cai dentro de 1,5 kg (dizer quais no commit). Sabotagens: tolerância → 0 → `test_um_quilo_a_mais…` vermelho; ignorar `goal` em `analisar` → `test_quem_mantem…` vermelho. Commit: "Pesar dentro de 1,5 kg não regenera o cardápio, e 'Cortar 150 kcal' só fala com quem quer perder".

---

## Depois das quatro tarefas (o orquestrador)

1. Suíte completa no banco privado (`fundo.py rodar`).
2. Browser QA local (390, claro/escuro): Home com "7,5 colheres de sopa (116 g)" e café com fator ≤ 1,5 (ler `scale_factor` na tela ou no banco); lista de compras sem "40 g"/"20 ml" soltos; pesar +1 kg → mesmas opções; +1,6 kg → "recalculamos"; perfil BULK com 3 semanas estáveis → "+150 kcal".
3. Revisão adversarial de branch inteira; uma onda; re-revisão.
4. PR `mercado/dieta` → CI → merge → `/saude/` → smoke → QA em produção com conta descartável (cardápio com medida caseira; lista) → conta apagada → demo intacto.
