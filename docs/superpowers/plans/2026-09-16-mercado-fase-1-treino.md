# Padrões de mercado — Fase 1 (treino) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na execução do treino, a melhor série (reps×carga) vira recorde ao lado do recorde de carga, os dois são celebrados na hora por um aviso animado que não cobre nada, e a tela do exercício ganha um gráfico SVG da carga máxima das últimas 12 sessões.

**Architecture:** Tudo nasce de dados já carregados: `load_history` (uma consulta) ganha o maior produto reps×carga anterior; `supera_recorde` devolve as espécies superadas numa consulta; uma segunda regra de conquista (`melhor-serie`) é anunciada pelo overlay existente. O overlay ganha animação por CSS com tokens, fecha por Esc e empurra o conteúdo (`body.tem-conquista`), e nunca aparece em página de erro. O gráfico é uma polilinha SVG produzida por `workouts/curva.py`, generalização de `_curva_de_peso`.

**Tech Stack:** Django 5.2, PostgreSQL, templates Django, CSS único `static/css/app.css` (seções numeradas), JS sem build, testes `django.test.TestCase` com `RunnerUnico`.

**Spec:** `docs/superpowers/specs/2026-09-16-mercado-fase-1-treino-design.md`

## Global Constraints

- **Não tocar** `workouts/test_ficha_de_verdade.py` (teste dourado), nem a branch `design/mesa-e-ferro`.
- **Não afrouxar** orçamento de consultas: `workouts/test_recorde_na_hora.py` (`CONSULTAS_DA_EXECUCAO = 22`, `CONSULTAS_DO_POST_SEM_RECORDE = 20`) e `workouts/test_exercicio_leitura.py::test_o_custo_e_fixo` continuam verdes com os mesmos números.
- **Contrato de `achievements.regras._recorde` intocado**: recorde de carga = maior `weight_kg`; chave `exercício:data`; nenhum número persistido ou exposto em card. A nova regra segue o mesmo contrato.
- **Movimento só por token**: `config/test_movimento.py::test_nenhuma_duracao_escrita_a_mao` — usar `var(--mov-sucesso)`, `var(--mov-tela)`, `var(--ease)`; toda animação nova entra na lista `@media (prefers-reduced-motion: reduce)` da seção 47.
- **`:has()` proibido** para estrutura; classe vem do servidor. **Sem biblioteca** de gráfico. **Números com vírgula** (`floatformat`).
- **Cor só por token** (`stroke: currentColor` + classe com `color: var(--…)`); `config/tests.py` recalcula contraste.
- Rodar testes: `.venv/Scripts/python.exe manage.py test <modulo> --noinput` a partir da raiz do worktree. Antes, confirmar banco de teste livre: `psql -U postgres -d postgres -tAc "select count(*) from pg_stat_activity where datname like 'test_nutriplan%'"` deve dar 0 (senão ESPERE — `RunnerUnico` recusa).
- Commits: mensagem em pt-BR no estilo do repositório (o QUÊ e o PORQUÊ, com o caso real); `git commit` roda o pre-commit (18 testes rápidos). Nunca `--no-verify`.
- Nada de sabotagem, arquivo temporário ou credencial no commit.

---

## Propriedade de arquivos (para paralelizar sem colisão)

| tarefa | arquivos que edita | pode rodar junto com |
|---|---|---|
| T1 | `workouts/services.py`, `workouts/views.py`, `achievements/regras.py`, `achievements/services.py`, `templates/workouts/agora.html`, novo `workouts/test_recorde_de_volume.py` | T2, T3 |
| T2 | `templates/partials/_conquista.html`, `templates/base.html`, `static/css/app.css` (seções 40 e 47), `templates/achievements/*.html` (interruptor de som), `static/js/conquista.js` (novo), novo `achievements/test_frame_de_recompensa.py` | T1, T3 |
| T3 | novo `workouts/test_prefill_por_serie.py` (só teste) | T1, T2 |
| T4 | novo `workouts/curva.py`, `workouts/services.py` (só `DATAS_DO_HISTORICO`), `workouts/views.py` (só `ExercicioView`), `templates/workouts/exercicio.html`, `static/css/app.css` (nova regra `.curva--carga`), novo `workouts/test_grafico_do_exercicio.py` | **depois** de T1 (mesmos arquivos) |

---

### Task 1: Recorde de melhor série (reps×carga), detectado e celebrado na hora

**Files:**
- Modify: `workouts/services.py` — `load_history` (~l. 2621–2700), `linhas_de_serie` (~l. 2866–2908), `supera_recorde` (~l. 3128–3144)
- Modify: `workouts/views.py` — `ConcluirSerieView.post`, o gatilho (~l. 1310–1319)
- Modify: `achievements/regras.py` — nova regra depois de `novo-recorde` (~l. 236–244)
- Modify: `achievements/services.py` — `reunir()` (~l. 88–115) calcula `melhores_series_hoje`; `Dados` em `regras.py` (~l. 49–75) ganha o campo
- Modify: `templates/workouts/agora.html` — pastilha (~l. 282–295) e fato (~l. 529–533)
- Test: `workouts/test_recorde_de_volume.py` (novo)

**Interfaces:**
- Consumes: `load_history(user, exercises, day)` (dict por exercício), `linhas_de_serie(item, load)`, `supera_recorde(user, exercise, weight_kg, dia)`, `achievements.services.avaliar/anunciar`, `Regra`/`Familia`/`Dados` de `achievements/regras.py`.
- Produces:
  - `load_history[...]["melhor_serie_anterior"]: Decimal | None` — maior `weight_kg * reps` de uma única série em QUALQUER data anterior (só séries com os dois campos).
  - `linhas_de_serie` → cada linha ganha `"melhor_serie": bool` (a série de hoje supera `melhor_serie_anterior`).
  - `supera_recorde(...) -> set[str]` com `"carga"` e/ou `"melhor_serie"`; conjunto vazio = nada. **Assinatura muda: ganha `reps=None`.** Quem chamava com `bool(...)` continua funcionando (conjunto vazio é falso).
  - `Dados.melhores_series_hoje: tuple[(exercicio_id, nome)]` e a regra `slug="melhor-serie"`, `familia=Familia.RECORDE`, `repetivel=True`, chave `"%d:%s" % (exercicio_id, hoje)`.

- [ ] **Step 1: Ler as regiões acima** (não presumir; as linhas podem ter deslocado). Ler também `workouts/test_recorde_na_hora.py` inteiro — os helpers `create_user`, `dias_incluindo_hoje`, `escolher_opcao_de_hoje`, `sem_scripts` e o padrão `_log(dias_atras, serie, peso, reps)` são os que o novo teste reusa.

- [ ] **Step 2: Escrever o teste que falha** — `workouts/test_recorde_de_volume.py`:

```python
# -*- coding: utf-8 -*-
"""A melhor série (reps×carga) é recorde ao lado da maior carga.

BENCHMARK-2026-09 (a): Hevy, Strong e Fitbod celebram o recorde na hora — e
os dois que eles celebram são "maior carga" e "melhor série". O NutriPlan
tinha o primeiro (`test_recorde_na_hora.py`). Este arquivo acrescenta o
segundo SEM tocar o contrato de `_recorde` ("não é volume, não é carga por
repetição"): é uma SEGUNDA regra, `melhor-serie`, com a mesma chave
`exercício:data` e nenhum número persistido.

Estreia não é recorde (não há série anterior para superar); exercício sem
carga não tem melhor série; carga E melhor série no mesmo toque são DUAS
conquistas (uma de cada regra), anunciadas na mesma fila.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from achievements.models import UserAchievement as Conquista
from workouts import services
from workouts.models import ExerciseLog, Measure
from workouts.test_recorde_na_hora import CONSULTAS_DO_POST_SEM_RECORDE
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class AMelhorSerieTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="melhor@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def _log(self, dias_atras, serie, peso, reps):
        return ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.item.exercise,
            date=self.hoje - timedelta(days=dias_atras), set_number=serie,
            weight_kg=Decimal(str(peso)), reps=reps,
        )

    def _concluir(self, peso, reps):
        return self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": self.item.exercise.pk, "weight_kg": str(peso), "reps": str(reps)},
        )

    # ---- o serviço ----

    def test_load_history_traz_o_maior_produto_anterior(self):
        self._log(7, 1, 60, 10)   # 600
        self._log(7, 2, 62.5, 8)  # 500 — carga maior, produto menor
        load = services.load_history(self.pessoa, [self.item.exercise], day=self.hoje)
        self.assertEqual(load[self.item.exercise.pk]["melhor_serie_anterior"], Decimal("600"))
        self.assertEqual(load[self.item.exercise.pk]["recorde_anterior"], Decimal("62.5"))

    def test_supera_recorde_diz_qual_especie(self):
        self._log(7, 1, 60, 10)   # carga 60, produto 600
        ex = self.item.exercise
        self.assertEqual(services.supera_recorde(self.pessoa, ex, Decimal("65"), reps=8, dia=self.hoje), {"carga"})
        self.assertEqual(services.supera_recorde(self.pessoa, ex, Decimal("60"), reps=12, dia=self.hoje), {"melhor_serie"})
        self.assertEqual(services.supera_recorde(self.pessoa, ex, Decimal("65"), reps=10, dia=self.hoje), {"carga", "melhor_serie"})
        self.assertEqual(services.supera_recorde(self.pessoa, ex, Decimal("55"), reps=10, dia=self.hoje), set())

    def test_igualar_nao_e_superar(self):
        self._log(7, 1, 60, 10)
        self.assertEqual(services.supera_recorde(self.pessoa, self.item.exercise, Decimal("60"), reps=10, dia=self.hoje), set())

    def test_estreia_nao_e_recorde_de_especie_nenhuma(self):
        self.assertEqual(services.supera_recorde(self.pessoa, self.item.exercise, Decimal("100"), reps=20, dia=self.hoje), set())

    def test_sem_reps_nao_ha_melhor_serie(self):
        self._log(7, 1, 60, 10)
        self.assertEqual(services.supera_recorde(self.pessoa, self.item.exercise, Decimal("60"), reps=None, dia=self.hoje), set())

    def test_a_linha_da_serie_marca_a_melhor_serie(self):
        self._log(7, 1, 60, 10)
        self._log(0, 1, 60, 12)
        load = services.load_history(self.pessoa, [self.item.exercise], day=self.hoje)
        linhas = services.linhas_de_serie(self.item, load[self.item.exercise.pk])
        self.assertTrue(linhas[0]["melhor_serie"])
        self.assertFalse(linhas[0]["recorde"])

    # ---- a rota que a execução usa ----

    def test_a_melhor_serie_vira_conquista_na_hora(self):
        self._log(7, 1, 60, 10)
        self._concluir(60, 12)
        slugs = set(Conquista.objects.filter(user=self.pessoa).values_list("achievement__slug", flat=True))
        self.assertIn("melhor-serie", slugs)
        self.assertNotIn("novo-recorde", slugs)

    def test_carga_e_melhor_serie_no_mesmo_toque_sao_duas_conquistas(self):
        self._log(7, 1, 60, 10)
        self._concluir(65, 10)
        slugs = set(Conquista.objects.filter(user=self.pessoa).values_list("achievement__slug", flat=True))
        self.assertTrue({"novo-recorde", "melhor-serie"} <= slugs, slugs)

    def test_a_tela_diz_melhor_serie_na_pastilha_e_no_fato(self):
        self._log(7, 1, 60, 10)
        self._concluir(60, 12)
        html = self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.item.exercise.pk).content.decode()
        self.assertIn("melhor série", html.lower())
        self.assertIn("60 kg × 10", html)  # o fato: a melhor série anterior

    def test_o_post_sem_recorde_nao_custa_mais(self):
        self._log(7, 1, 60, 10)
        with CaptureQueriesContext(connection) as consultas:
            self._concluir(55, 8)
        self.assertLessEqual(len(consultas), CONSULTAS_DO_POST_SEM_RECORDE, consultas.captured_queries)

    def test_a_frase_da_conquista_nao_carrega_numero(self):
        self._log(7, 1, 60, 10)
        self._concluir(60, 12)
        conquista = Conquista.objects.get(user=self.pessoa, achievement__slug="melhor-serie")
        texto = (conquista.achievement.titulo + conquista.achievement.frase)
        self.assertFalse(any(c.isdigit() for c in texto), texto)
```

Se `create_user`/`dias_incluindo_hoje`/`escolher_opcao_de_hoje` tiverem nomes diferentes em `workouts/tests.py`, usar os de `test_recorde_na_hora.py` — o padrão é o mesmo. Se `Conquista.achievement` tiver outro nome de campo, ler `achievements/models.py` e ajustar (não inventar).

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test workouts.test_recorde_de_volume --noinput`
Expected: FAIL/ERROR — `melhor_serie_anterior` inexistente, `supera_recorde` sem `reps`, regra inexistente.

- [ ] **Step 4: `load_history` — o maior produto anterior, no mesmo laço**

Em `resultado[exercise_id] = {...}` acrescentar, calculado junto de `recorde_anterior`:

```python
        melhor_serie_anterior = max(
            (l.weight_kg * l.reps for l in anteriores
             if l.weight_kg is not None and l.reps is not None),
            default=None,
        )
```
e a chave `"melhor_serie_anterior": melhor_serie_anterior`. Atualizar a docstring (a lista de chaves) com uma linha: `"melhor_serie_anterior": Decimal|None,  # maior reps×carga de UMA série anterior`.

- [ ] **Step 5: `linhas_de_serie` — a linha marca a melhor série**

```python
    melhor = (load or {}).get("melhor_serie_anterior")
    ...
                "melhor_serie": bool(
                    registro is not None and melhor is not None
                    and registro.weight_kg is not None and registro.reps is not None
                    and registro.weight_kg * registro.reps > melhor
                ),
```

- [ ] **Step 6: `supera_recorde` devolve as espécies, numa consulta**

Substituir a função por:

```python
def supera_recorde(user, exercise, weight_kg, reps=None, dia=None) -> set:
    """Que recordes esta série supera: `{"carga"}`, `{"melhor_serie"}`, os dois, ou nada.

    Duas espécies, o mesmo contrato de `achievements.regras._recorde`: só
    SUPERAR conta, contra dias ANTERIORES a `dia`; estreia é o conjunto vazio.
    "carga" é a maior carga já registrada; "melhor_serie" é o maior produto
    reps×carga de UMA série — 60 kg × 12 supera 60 kg × 10 sem mexer na carga,
    que é o segundo eixo da dupla progressão e o que Hevy e Strong celebram
    (BENCHMARK-2026-09, padrão a).

    Uma consulta com duas agregações, porque isto roda em TODA série concluída
    (`ConcluirSerieView`) e o orçamento do POST é medido.
    """
    from django.db.models import DecimalField, ExpressionWrapper, F

    dia = dia or timezone.localdate()
    anteriores = ExerciseLog.objects.filter(
        user=user, exercise=exercise, date__lt=dia, weight_kg__isnull=False
    )
    agregado = anteriores.aggregate(
        maior=Max("weight_kg"),
        melhor=Max(
            ExpressionWrapper(F("weight_kg") * F("reps"), output_field=DecimalField(max_digits=10, decimal_places=2)),
            filter=Q(reps__isnull=False),
        ),
    )
    especies = set()
    if agregado["maior"] is not None and weight_kg > agregado["maior"]:
        especies.add("carga")
    if reps is not None and agregado["melhor"] is not None and weight_kg * reps > agregado["melhor"]:
        especies.add("melhor_serie")
    return especies
```
Conferir os imports já existentes no topo de `services.py` (`Max`, `Q`); não duplicar.

- [ ] **Step 7: a view passa `reps`** — em `ConcluirSerieView.post`, trocar `services.supera_recorde(request.user, exercise, peso, dia=dia)` por `services.supera_recorde(request.user, exercise, peso, reps=reps, dia=dia)`. O `if primeira_do_dia or ...` continua válido (conjunto vazio é falso).

- [ ] **Step 8: a regra `melhor-serie`** — em `achievements/regras.py`:

`Dados` ganha, ao lado de `recordes_hoje`:
```python
    #: Exercícios cuja MELHOR SÉRIE (reps×carga) foi superada HOJE: (id, nome).
    #: Mesmo contrato de `recordes_hoje`: o número não entra.
    melhores_series_hoje: tuple = ()
```
Nova função e regra, logo depois de `_recorde` / `novo-recorde`:
```python
def _melhor_serie(dados):
    """Melhor série num exercício: o maior reps×carga de UMA série.

    Segunda espécie de recorde, ao lado de `_recorde`, que continua sendo só
    a maior carga (o contrato dele não muda). Mesma chave `exercício:data`,
    pelos mesmos dois motivos: nada persistido, nada que vaze num card.
    """
    return [
        ("%d:%s" % (exercicio_id, dados.hoje.isoformat()), {"exercicio": nome})
        for exercicio_id, nome in dados.melhores_series_hoje
    ]
```
```python
    Regra(
        slug="melhor-serie",
        titulo="Melhor série",
        frase="Você fez sua melhor série num exercício: mais repetições com mais carga.",
        emoji="\U0001f4aa",
        familia=Familia.RECORDE,
        detectar=_melhor_serie,
        repetivel=True,
    ),
```
Ler como `_recorde` monta a lista (o `for` real) e copiar a forma exata.

- [ ] **Step 9: `reunir()` calcula `melhores_series_hoje`** — em `achievements/services.py`, onde `recordes_hoje` é montado (~l. 88–115), montar também `melhores_series_hoje` com a MESMA leitura (não uma consulta nova): para cada exercício com série hoje, comparar o maior `weight_kg*reps` de hoje com o maior de datas anteriores. Se `reunir` já itera os logs por exercício, é um `max` a mais no mesmo laço. Passar `melhores_series_hoje=tuple(...)` ao `Dados(...)`.

- [ ] **Step 10: a tela** — `templates/workouts/agora.html`:
  - pastilha (~l. 288–291): ao lado de `{% if linha.recorde %}<span class="series__recorde">recorde</span>{% endif %}` acrescentar `{% if linha.melhor_serie %}<span class="series__recorde">melhor série</span>{% endif %}` (mesma classe, mesma cor; se as duas valerem, aparecem as duas).
  - fato (~l. 529–533): depois de "Recorde: X kg", quando `atual.load.melhor_serie_anterior` existir, uma linha `Melhor série: {{ atual.load.melhor_serie_peso|floatformat:'-2' }} kg × {{ atual.load.melhor_serie_reps }}`. Para isso `load_history` também guarda `melhor_serie_peso`/`melhor_serie_reps` (a série que produziu o máximo — pegar o `l` do `max` com `key=`). Ajustar o Step 4 para guardar o registro, não só o produto:
    ```python
        melhor_registro = max(
            (l for l in anteriores if l.weight_kg is not None and l.reps is not None),
            key=lambda l: l.weight_kg * l.reps, default=None,
        )
        melhor_serie_anterior = melhor_registro.weight_kg * melhor_registro.reps if melhor_registro else None
        ...
            "melhor_serie_anterior": melhor_serie_anterior,
            "melhor_serie_peso": melhor_registro.weight_kg if melhor_registro else None,
            "melhor_serie_reps": melhor_registro.reps if melhor_registro else None,
    ```

- [ ] **Step 11: Rodar até verde**

Run: `.venv/Scripts/python.exe manage.py test workouts.test_recorde_de_volume workouts.test_recorde_na_hora achievements --noinput`
Expected: OK. Se `test_o_custo_e_fixo` ou os orçamentos de `test_recorde_na_hora` caírem, a agregação virou duas consultas — voltar ao Step 6.

- [ ] **Step 12: Sabotagem (não commitar)** — (a) trocar `>` por `>=` no produto → `test_igualar_nao_e_superar` vermelho; (b) apagar `filter=Q(reps__isnull=False)` → `test_sem_reps_nao_ha_melhor_serie` continua verde? Se sim, o teste é fraco: acrescentar um log anterior com `reps=None` e carga alta e exigir que ele não conte; (c) remover a regra do catálogo → `test_a_melhor_serie_vira_conquista_na_hora` vermelho. Restaurar tudo; `git diff` limpo além do intencional.

- [ ] **Step 13: Commit**

```bash
git add workouts/services.py workouts/views.py achievements/regras.py achievements/services.py templates/workouts/agora.html workouts/test_recorde_de_volume.py
git commit -m "A melhor série (reps×carga) é recorde ao lado da maior carga, celebrada na hora"
```

---

### Task 2: Frame de recompensa, N1 e som opcional

**Files:**
- Modify: `templates/partials/_conquista.html` (classe de variante, botão de som lido do `localStorage`, `data-` para o JS)
- Modify: `templates/base.html` (~l. 447: `include` atrás de `{% if request.resolver_match %}`; classe `tem-conquista` no `<body>` quando `conquistas_novas`)
- Create: `static/js/conquista.js` (Esc fecha por `fetch`; som opcional; a fila que hoje está inline no parcial migra para cá)
- Modify: `static/css/app.css` — seção 40 (`.conquista--recorde`, `body.tem-conquista .container { padding-bottom }`) e seção 47 (keyframes `conquista-chega` e `conquista-emoji`, e as duas entradas na lista de reduced-motion)
- Modify: `templates/achievements/<a tela /conquistas/>.html` — interruptor "Tocar um som ao desbloquear"
- Test: `achievements/test_frame_de_recompensa.py` (novo)

**Interfaces:**
- Consumes: context processor `conquistas_novas` (lista de `UserAchievement` com `.achievement.familia`), rota `achievements:marcar_vistas` (POST `id`… e `proximo`; JSON quando `X-Requested-With: fetch`), `body.tem-convite` como padrão do `padding-bottom` (~`app.css:4142–4148`), tokens `--mov-sucesso`, `--mov-tela`, `--ease`, `--brand-soft`.
- Produces: classes `body.tem-conquista`, `.conquista--recorde`; atributo `data-som="1"` no aviso quando o interruptor está ligado (decidido no cliente); `localStorage["nutriplan.som-conquista"] = "1"`.

- [ ] **Step 1: Ler** `templates/partials/_conquista.html` inteiro, `templates/base.html` ~l. 1–40 (o `<body class=...>` e como `tem-convite`/`tem-tabbar` entram) e ~l. 440–450, `app.css` 4075–4150 (convite) e 6904–6969 (seção 40) e 7799–7960 (seção 47), `achievements/context_processors.py`, `achievements/views.py::MarcarVistasView.post`, `config/test_movimento.py` (o que ele cobra), a tela de `/conquistas/` em `templates/achievements/`.

- [ ] **Step 2: Escrever o teste que falha** — `achievements/test_frame_de_recompensa.py`:

```python
# -*- coding: utf-8 -*-
"""O aviso de conquista celebra sem cobrir nada.

N1 (DELTA de 16/09/2026): o aviso `position: fixed` ficava em toda página
até "Continuar" e cobria o CTA do rodapé — em /conta/excluir/, o clique em
"Excluir minha conta" caía no "Continuar" do aviso. Aqui: o `body` ganha
`tem-conquista` e o container recebe `padding-bottom` (o mesmo mecanismo do
convite de instalação), o aviso fecha por Esc, e não aparece em página de
erro (o 404 não tem `resolver_match`).

BENCHMARK-2026-09 (a): o recorde é celebrado com um "frame de recompensa" —
entrada animada com tokens de movimento, desligada em reduced-motion, e som
OPCIONAL (opt-in, `localStorage`), nunca por padrão.
"""
import re

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from achievements import services as conquistas
from achievements.models import Achievement, UserAchievement
from workouts import services
from workouts.tests import create_user, dias_incluindo_hoje

CSS = "static/css/app.css"


def _css():
    from django.conf import settings
    return (settings.BASE_DIR / CSS).read_text(encoding="utf-8")


class OAvisoNaoCobreNadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="frame@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def _com_aviso_pendente(self, slug="primeiro-treino"):
        regra = Achievement.objects.get(slug=slug)
        nova = UserAchievement.objects.create(user=self.pessoa, achievement=regra, unlocked_at=timezone.now())
        sessao = self.client.session
        sessao[conquistas.CHAVE_DA_SESSAO if hasattr(conquistas, "CHAVE_DA_SESSAO") else "conquistas_novas"] = [nova.pk]
        sessao.save()
        return nova

    def test_o_body_ganha_a_classe_e_o_css_empurra_o_conteudo(self):
        self._com_aviso_pendente()
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertRegex(html, r'<body[^>]*class="[^"]*\btem-conquista\b')
        css = _css()
        self.assertRegex(css, r"body\.tem-conquista[^{]*\.container\s*\{[^}]*padding-bottom")

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
        self.assertRegex(_css(), r"\.conquista--recorde\s*\{[^}]*--brand-soft")

    def test_a_entrada_e_animada_por_token_e_desligada_em_reduced_motion(self):
        css = _css()
        self.assertRegex(css, r"@keyframes conquista-chega")
        bloco = re.search(r"\.conquista\s*\{[^}]*animation:[^;]*conquista-chega[^;]*var\(--mov-", css)
        self.assertIsNotNone(bloco, "a animação de entrada precisa usar um token de duração")
        reduzido = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}\n", css, re.S)
        self.assertIsNotNone(reduzido)
        self.assertIn(".conquista", reduzido.group(1))

    def test_esc_fecha_pelo_mesmo_post(self):
        self._com_aviso_pendente()
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("conquista.js", html)
        js = (__import__("django.conf").conf.settings.BASE_DIR / "static/js/conquista.js").read_text(encoding="utf-8")
        self.assertIn('"Escape"', js)
        self.assertIn("X-Requested-With", js)

    def test_o_som_e_opt_in(self):
        js = (__import__("django.conf").conf.settings.BASE_DIR / "static/js/conquista.js").read_text(encoding="utf-8")
        self.assertIn("nutriplan.som-conquista", js)
        self.assertIn("AudioContext", js)
        html = self.client.get(reverse("achievements:lista")).content.decode()
        self.assertIn("Tocar um som ao desbloquear", html)
        self.assertNotIn('data-som="1"', html)  # o servidor nunca liga; só o cliente
```
Antes de rodar: conferir os nomes reais — a chave de sessão (`achievements/context_processors.py:14`), o nome da rota da lista de conquistas em `achievements/urls.py`, os campos de `UserAchievement` (`unlocked_at`?) em `achievements/models.py`, e o slug de uma conquista qualquer no catálogo (`Achievement.objects.first().slug`). Ajustar o teste ao que existe.

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test achievements.test_frame_de_recompensa --noinput`
Expected: FAIL em todos.

- [ ] **Step 4: `base.html`** — no `<body>`, junto de `tem-convite`/`tem-tabbar`, acrescentar `{% if conquistas_novas %} tem-conquista{% endif %}` (o context processor já está no template). Trocar o `include` por:
```django
  {% if request.resolver_match %}{% include "partials/_conquista.html" %}{% endif %}
```
e, dentro do `{% if conquistas_novas %}` do parcial (ou logo após o include), `<script src="{% static 'js/conquista.js' %}" defer></script>` — seguir como `card_js_url` é montado em `base.html` (versão no query string) e fazer igual.

- [ ] **Step 5: `_conquista.html`** — no `<div class="conquista"` acrescentar a variante: `class="conquista{% if conquistas_novas.0.achievement.familia == 'recorde' %} conquista--recorde{% endif %}"` (conferir o valor real de `Familia.RECORDE` em `regras.py:39` — é `"recorde"`). Mover o `<script>` inline da fila para `static/js/conquista.js` (o parcial fica só com HTML).

- [ ] **Step 6: `static/js/conquista.js`**

```js
/* O aviso de conquista: a fila, o Esc e o som opcional.
 * Fila: "Próxima" avança um slide; só o último envia o formulário.
 * Esc: o mesmo POST de "Continuar", por fetch, e o aviso some sem recarregar.
 * Som: opt-in em localStorage("nutriplan.som-conquista"); três notas curtas
 * por AudioContext, só depois de um gesto (política de autoplay). */
(function () {
  var caixa = document.querySelector("[data-conquista]");
  if (!caixa) return;
  var slides = caixa.querySelectorAll("[data-conquista-slide]");
  var form = caixa.querySelector(".conquista__fechar-form");

  caixa.addEventListener("click", function (evento) {
    var botao = evento.target.closest("[data-conquista-proxima]");
    if (!botao) return;
    evento.preventDefault();
    for (var i = 0; i < slides.length; i++) {
      if (!slides[i].hidden) { slides[i].hidden = true; if (slides[i + 1]) slides[i + 1].hidden = false; return; }
    }
  });

  function fechar() {
    if (!form) return;
    fetch(form.action, {
      method: "POST", body: new FormData(form), credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" }
    }).catch(function () {}).finally(function () {
      caixa.remove();
      document.body.classList.remove("tem-conquista");
    });
  }
  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") fechar();
  });

  var querSom = false;
  try { querSom = localStorage.getItem("nutriplan.som-conquista") === "1"; } catch (e) {}
  if (querSom && window.AudioContext) {
    var tocar = function () {
      document.removeEventListener("pointerdown", tocar);
      var ctx = new AudioContext(), t = ctx.currentTime;
      [523.25, 659.25, 783.99].forEach(function (freq, i) {
        var osc = ctx.createOscillator(), ganho = ctx.createGain();
        osc.frequency.value = freq; osc.connect(ganho); ganho.connect(ctx.destination);
        ganho.gain.setValueAtTime(0.0001, t + i * 0.13);
        ganho.gain.exponentialRampToValueAtTime(0.2, t + i * 0.13 + 0.02);
        ganho.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.13 + 0.16);
        osc.start(t + i * 0.13); osc.stop(t + i * 0.13 + 0.18);
      });
    };
    document.addEventListener("pointerdown", tocar, { once: true });
  }
})();
```
Interruptor na tela `/conquistas/`: um `<label class="...">` com `<input type="checkbox" data-som-conquista>` e "Tocar um som ao desbloquear", e no mesmo `conquista.js` (ou num bloco no fim da tela) o `change` grava `"1"`/remove em `localStorage`, e o `checked` inicial é lido de lá. Sem `data-som="1"` vindo do servidor.

- [ ] **Step 7: CSS** — seção 40:
```css
.conquista--recorde { background: var(--brand-soft); }
/* N1: o aviso é fixo e ficava por cima do CTA do rodapé (Excluir minha
   conta, 16/09/2026). Como o convite de instalação, ele EMPURRA o conteúdo. */
body.tem-conquista .container { padding-bottom: 13rem; }
```
(ajustar 13rem à altura real do aviso medida no navegador; a regra do convite usa 13rem/6rem por breakpoint — seguir o mesmo par). Seção 47 (Movimento), junto dos outros keyframes:
```css
/* O frame de recompensa: o aviso sobe e assenta; o emoji dá um pulso. */
@keyframes conquista-chega { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
@keyframes conquista-emoji { 0% { transform: scale(.8); } 60% { transform: scale(1.15); } 100% { transform: none; } }
.conquista { animation: conquista-chega var(--mov-sucesso) var(--ease) both; }
.conquista__emoji { animation: conquista-emoji var(--mov-sucesso) var(--ease) both; animation-delay: var(--mov-tela); }
```
e na lista `@media (prefers-reduced-motion: reduce)` da seção 47 acrescentar `.conquista, .conquista__emoji` ao grupo `{ animation: none; }`.

- [ ] **Step 8: Rodar até verde**

Run: `.venv/Scripts/python.exe manage.py test achievements config.test_movimento config.test_design_system config.tests --noinput`
Expected: OK (contraste de `--brand-soft` como fundo do aviso já é medido em `config/tests.py`; se reprovar, usar `--surface-3` em vez de `--brand-soft` e registrar).

- [ ] **Step 9: Sabotagem** — (a) tirar `.conquista` da lista de reduced-motion → `test_a_entrada_e_animada…` vermelho; (b) `padding-bottom` → `padding-top` → `test_o_body_ganha_a_classe…` vermelho; (c) remover o `{% if request.resolver_match %}` → `test_o_aviso_nao_aparece_em_pagina_de_erro` vermelho. Restaurar.

- [ ] **Step 10: Commit**

```bash
git add templates/partials/_conquista.html templates/base.html static/js/conquista.js static/css/app.css templates/achievements/ achievements/test_frame_de_recompensa.py
git commit -m "O aviso de conquista celebra sem cobrir nada: entra animado, fecha por Esc, empurra o conteúdo e não aparece em página de erro"
```

---

### Task 3: A ordem do pré-preenchimento, pinada por teste

**Files:**
- Test: `workouts/test_prefill_por_serie.py` (novo) — **só teste**; nenhuma alteração de código de produção é esperada (a spec decidiu manter a ordem). Se algum caso reprovar, PARAR e reportar em vez de mudar `_sugestao_de_carga`.

**Interfaces:**
- Consumes: `services.estado_do_treino` (ou a view `workouts:now`) e os campos `sugestao_carga`/`sugestao_reps` do item; helpers de `workouts/test_dupla_progressao.py::ATelaTests` (ler como ele monta histórico completo e abre a tela).

- [ ] **Step 1: Ler** `workouts/services.py::_sugestao_de_carga` e `_sugestao_de_reps`, `workouts/test_dupla_progressao.py` (classe `ATelaTests`, helpers de histórico) e `workouts/test_fluxo_do_treino.py::ACargaAnteriorNaoViraRecomendacaoTests`.

- [ ] **Step 2: Escrever os testes** — `workouts/test_prefill_por_serie.py`:

```python
# -*- coding: utf-8 -*-
"""Cada série abre com um número que a pessoa já levantou — e com QUAL.

BENCHMARK-2026-09 (c): Hevy, Strong e Fitbod pré-preenchem cada série com a
MESMA série da última sessão. O NutriPlan faz isso na abertura da sessão, e
põe duas coisas na frente, por decisão escrita (`_sugestao_de_carga`, 30/08
e T2.3): a última série de HOJE (ninguém troca de carga entre a 1ª e a 2ª de
propósito) e a sugestão da adaptação (frase == campo). A mais pesada do
último treino é o ÚLTIMO recurso, nunca o primeiro.

Este arquivo pina a ordem — carga e reps lado a lado — para que ninguém a
"corrija" para o comportamento literal do Hevy sem ler o motivo.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog, Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class AOrdemDoPrefillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="prefill@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS and i.sets >= 3
        )

    def _log(self, dias_atras, serie, peso, reps):
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.item.exercise,
            date=self.hoje - timedelta(days=dias_atras), set_number=serie,
            weight_kg=Decimal(str(peso)), reps=reps,
        )

    def _campos(self):
        html = self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.item.exercise.pk).content.decode()
        import re
        carga = re.search(r'name="weight_kg"[^>]*value="([^"]*)"', html)
        reps = re.search(r'name="reps"[^>]*value="([^"]*)"', html)
        return (carga.group(1) if carga else ""), (reps.group(1) if reps else "")

    def test_sem_historico_o_campo_abre_vazio(self):
        self.assertEqual(self._campos(), ("", ""))

    def test_na_abertura_a_serie_1_vem_da_mesma_serie_da_ultima_sessao_quando_nao_ha_sugestao(self):
        # Uma série só na última sessão: sem faixa fechada em todas, a
        # adaptação não sugere, e o que sobra é a mesma série da última vez.
        self._log(7, 1, 57.5, 9)
        self.assertEqual(self._campos(), ("57,5", "9"))

    def test_a_mesma_serie_da_ultima_sessao_vence_a_mais_pesada(self):
        self._log(7, 1, 50, 10)
        self._log(7, 2, 60, 8)   # a mais pesada foi a 2ª
        self.assertEqual(self._campos()[0], "50")  # série 1 abre com a série 1

    def test_a_serie_anterior_de_hoje_vence_tudo(self):
        self._log(7, 1, 60, 10)
        self._log(7, 2, 55, 10)
        self._log(0, 1, 62.5, 8)  # hoje a pessoa subiu
        self.assertEqual(self._campos(), ("62,5", "8"))  # a 2ª abre com a 1ª de hoje, não com 55

    def test_a_pastilha_pendente_mostra_a_mesma_serie_da_ultima_sessao(self):
        self._log(7, 1, 60, 10)
        self._log(7, 2, 55, 8)
        html = self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.item.exercise.pk).content.decode()
        self.assertIn("55", html)
        self.assertIn("60", html)
```
Se `sets >= 3` não existir em nenhum item da opção 1, relaxar para `>= 2`. Se o `value` de carga sair como `"57,50"`, aceitar a forma que `floatformat:'-2'` produz (é `57,5`).

- [ ] **Step 3: Rodar** — `.venv/Scripts/python.exe manage.py test workouts.test_prefill_por_serie --noinput`. Expected: OK sem mudar produção. Se algo falhar, o teste está afirmando uma ordem que não existe: ler `_sugestao_de_carga` de novo e corrigir o TESTE (não o serviço), ou reportar.

- [ ] **Step 4: Sabotagem** — em `_sugestao_de_carga`, mover `de_hoje` para depois de `anterior` → `test_a_serie_anterior_de_hoje_vence_tudo` vermelho; trocar `anterior.get(serie)` por `melhor_anterior` → `test_a_mesma_serie…vence_a_mais_pesada` vermelho. Restaurar.

- [ ] **Step 5: Commit**

```bash
git add workouts/test_prefill_por_serie.py
git commit -m "A ordem do pré-preenchimento fica pinada: hoje, depois a sugestão, depois a mesma série da última vez — nunca a mais pesada primeiro"
```

---

### Task 4: Gráfico da carga máxima por sessão (12 sessões, SVG por template)

**Files:**
- Create: `workouts/curva.py`
- Modify: `workouts/services.py` — `DATAS_DO_HISTORICO = 12` e a docstring de `historico_do_exercicio` (dizer "doze")
- Modify: `workouts/views.py` — `ExercicioView` contexto (~l. 1031–1042): `"curva_carga": curva.curva([s["carga"] for s in historico[::-1]])` (do mais antigo ao mais novo) quando `not exercicio.sem_carga`
- Modify: `templates/workouts/exercicio.html` — o SVG acima da lista "Como fui"
- Modify: `static/css/app.css` — na seção onde vive `.curva__linha` (~l. 1295–1312): `.curva--carga .curva__grafico { color: var(--brand); }` e `.curva__ponto { fill: currentColor; }`
- Test: `workouts/test_grafico_do_exercicio.py` (novo)

**Interfaces:**
- Consumes: `services.historico_do_exercicio(user, exercise)` → lista de `{"data", "carga", "reps"}` do mais RECENTE ao mais antigo; padrão `templates/plans/_peso.html` + `plans/views._curva_de_peso`.
- Produces: `workouts.curva.curva(valores, largura=300, altura=64, piso=0.4) -> dict | None` com `{"largura", "altura", "pontos": "x,y x,y …", "ultimo": (x, y), "primeiro": valor, "maximo": valor}`; `None` com <2 valores.

- [ ] **Step 1: Ler** `plans/views.py::_curva_de_peso` inteiro, `templates/plans/_peso.html` ~l. 55–75, `app.css` ~l. 1290–1315, `templates/workouts/exercicio.html` ~l. 60–85, `workouts/test_exercicio_leitura.py` (o orçamento e como monta 8 sessões).

- [ ] **Step 2: Teste que falha** — `workouts/test_grafico_do_exercicio.py`:

```python
# -*- coding: utf-8 -*-
"""A tela do exercício mostra a carga máxima das últimas doze sessões como curva.

BENCHMARK-2026-09 (b): gráfico de progressão por exercício é padrão em Hevy,
Strong, Fitbod e Strava. Aqui é uma polilinha SVG por template — o mesmo
padrão da curva de peso (`plans/views._curva_de_peso`), generalizado em
`workouts/curva.py` —, com cor por token e sem biblioteca.

SÓ carga máxima. Volume por sessão ficou de fora por duas decisões escritas
(`progresso.py`, `historico_do_exercicio`); a divergência com o benchmark
está registrada na spec como "recomendo rever".
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import curva, services
from workouts.models import Exercise, ExerciseLog
from workouts.tests import create_user, dias_incluindo_hoje


class ACurvaTests(TestCase):
    def test_menos_de_dois_pontos_nao_e_curva(self):
        self.assertIsNone(curva.curva([]))
        self.assertIsNone(curva.curva([Decimal("60")]))

    def test_a_escala_e_a_do_periodo_e_o_tempo_corre_para_a_direita(self):
        c = curva.curva([Decimal("50"), Decimal("60"), Decimal("55")], largura=200, altura=100)
        pontos = [tuple(float(v) for v in p.split(",")) for p in c["pontos"].split()]
        self.assertEqual([p[0] for p in pontos], [0.0, 100.0, 200.0])
        self.assertEqual(pontos[1][1], 0.0)     # o maior no topo
        self.assertEqual(pontos[0][1], 100.0)   # o menor embaixo
        self.assertEqual(c["ultimo"], pontos[-1])

    def test_faixa_estreita_tem_piso(self):
        c = curva.curva([Decimal("60"), Decimal("60.1")], largura=100, altura=100, piso=0.4)
        pontos = [tuple(float(v) for v in p.split(",")) for p in c["pontos"].split()]
        self.assertGreater(pontos[0][1] - pontos[1][1], 0)
        self.assertLess(pontos[0][1] - pontos[1][1], 100)  # 0,1 kg não vira montanha


class ATelaDoExercicioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="curva@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        self.exercicio = Exercise.objects.filter(is_active=True, sem_carga=False).exclude(equipment="bodyweight").first()

    def _sessoes(self, n, base=50):
        for i in range(n):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.exercicio, date=self.hoje - timedelta(days=(n - i) * 3),
                set_number=1, weight_kg=Decimal(base + i), reps=10,
            )

    def _tela(self):
        return self.client.get(reverse("workouts:exercicio", args=[self.exercicio.pk])).content.decode()

    def test_doze_sessoes_e_nao_oito(self):
        self._sessoes(14)
        self.assertEqual(len(services.historico_do_exercicio(self.pessoa, self.exercicio)), 12)

    def test_com_duas_ou_mais_sessoes_ha_curva_com_rotulo_acessivel(self):
        self._sessoes(3)
        html = self._tela()
        self.assertIn('class="curva__grafico"', html)
        self.assertIn('role="img"', html)
        self.assertIn("Carga máxima", html)
        self.assertIn("52 kg", html)  # a última no rótulo
        self.assertIn('class="curva__ponto"', html)

    def test_com_uma_sessao_nao_ha_curva(self):
        self._sessoes(1)
        self.assertNotIn('class="curva__grafico"', self._tela())

    def test_exercicio_sem_carga_nao_tem_curva(self):
        self.exercicio = Exercise.objects.filter(is_active=True, sem_carga=True).first()
        if self.exercicio is None:
            self.skipTest("catálogo sem exercício sem carga")
        for i in range(3):
            ExerciseLog.objects.create(user=self.pessoa, exercise=self.exercicio, date=self.hoje - timedelta(days=3 * (i + 1)), set_number=1, weight_kg=None, reps=30)
        self.assertNotIn('class="curva__grafico"', self._tela())

    def test_a_cor_vem_de_token(self):
        from django.conf import settings
        css = (settings.BASE_DIR / "static/css/app.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.curva--carga \.curva__grafico\s*\{[^}]*color:\s*var\(--")
```
Conferir os nomes reais: a rota do detalhe em `workouts/urls.py:26` (`name=`), os campos `is_active`/`sem_carga`/`equipment` em `workouts/models.py::Exercise`, e como `test_exercicio_leitura.py` cria logs. Ajustar ao que existe.

- [ ] **Step 3: Rodar e ver falhar** — `.venv/Scripts/python.exe manage.py test workouts.test_grafico_do_exercicio --noinput`. Expected: ImportError `workouts.curva`.

- [ ] **Step 4: `workouts/curva.py`**

```python
# -*- coding: utf-8 -*-
"""Pontos de uma polilinha SVG a partir de uma lista de valores.

Apresentação, não cálculo: nenhum número novo nasce aqui — é a generalização
de `plans.views._curva_de_peso` para qualquer série de valores (a carga
máxima por sessão de um exercício, hoje), com as mesmas três decisões:
escala do próprio período (zero-based esconderia a variação), piso para a
faixa estreita não virar montanha, e nada com menos de dois pontos.
"""


def curva(valores, largura=300, altura=64, piso=0.4):
    """`valores` do mais ANTIGO ao mais NOVO. Devolve None com menos de dois."""
    pontos = [float(v) for v in valores if v is not None]
    if len(pontos) < 2:
        return None
    menor, maior = min(pontos), max(pontos)
    faixa = max(maior - menor, piso)
    passo = largura / (len(pontos) - 1)
    coords = []
    for i, valor in enumerate(pontos):
        x = i * passo
        # y invertido: em SVG a origem é em cima, e valor maior tem de subir.
        y = altura - (valor - menor) / faixa * altura
        coords.append((round(x, 1), round(y, 1)))
    return {
        "largura": largura,
        "altura": altura,
        "pontos": " ".join("%g,%g" % c for c in coords),
        "ultimo": coords[-1],
        "primeiro": pontos[0],
        "maximo": pontos[-1],
    }
```
(`"maximo"` aqui é o ÚLTIMO valor — renomear para `"final"` se ficar ambíguo; o teste usa `ultimo` e o rótulo usa o último valor. Escolher um nome e usar o mesmo no template.)

- [ ] **Step 5: serviço, view e template**
  - `services.py`: `DATAS_DO_HISTORICO = 12`; na docstring "Oito datas" → "Doze datas"; o comentário do template `exercicio.html` ("Oito datas") idem.
  - `views.py::ExercicioView`: importar `from . import curva as _curva` e no contexto:
    ```python
        historico = services.historico_do_exercicio(self.request.user, exercicio)
        contexto["historico"] = historico
        contexto["curva_carga"] = (
            _curva.curva([s["carga"] for s in reversed(historico)])
            if not exercicio.sem_carga else None
        )
    ```
  - `exercicio.html`, dentro de `{% if historico %}` e antes do `<dl>`:
    ```django
      {% if curva_carga %}
        <figure class="curva curva--carga">
          <svg class="curva__grafico" viewBox="0 0 {{ curva_carga.largura }} {{ curva_carga.altura }}"
               preserveAspectRatio="none" role="img"
               aria-label="Carga máxima por sessão: de {{ curva_carga.primeiro|floatformat:'-2' }} kg há {{ historico|length }} sessões a {{ curva_carga.maximo|floatformat:'-2' }} kg na última">
            <polyline class="curva__linha" points="{{ curva_carga.pontos }}"/>
            <circle class="curva__ponto" cx="{{ curva_carga.ultimo.0 }}" cy="{{ curva_carga.ultimo.1 }}" r="3"/>
          </svg>
          <figcaption class="hint">Carga máxima por sessão — últimas {{ historico|length }}.</figcaption>
        </figure>
      {% endif %}
    ```
    Conferir como `_peso.html` escreve o `<svg>` (classes, `preserveAspectRatio`, wrapper) e copiar a forma exata.
  - `app.css` junto de `.curva__linha`: `.curva--carga .curva__grafico { color: var(--brand); }` e `.curva__ponto { fill: currentColor; }`. Se `.curva` já tem `width: 100%` etc., nada mais.

- [ ] **Step 6: Rodar até verde** — `.venv/Scripts/python.exe manage.py test workouts.test_grafico_do_exercicio workouts.test_exercicio_leitura config.tests --noinput`. Expected: OK, inclusive `test_o_custo_e_fixo` (a curva não consulta nada) e `test_o_historico_do_exercicio_aparece_por_sessao_e_para_em_oito` — **este vai reprovar de propósito** porque o teto virou doze: atualizar o nome e o número desse teste em `test_exercicio_leitura.py` (é o único ajuste permitido nele) e dizer no commit.

- [ ] **Step 7: Sabotagem** — (a) `reversed(historico)` → `historico` → `test_a_escala_e_a_do_periodo…` continua verde (é unitário) mas a curva desenha o tempo de trás para frente: acrescentar em `ATelaDoExercicioTests` um caso que lê `points` do HTML e exige que o último `x` corresponda ao maior valor quando a série é crescente; (b) `piso` → 0 → `test_faixa_estreita_tem_piso` vermelho; (c) tirar `role="img"` → vermelho. Restaurar.

- [ ] **Step 8: Commit**

```bash
git add workouts/curva.py workouts/services.py workouts/views.py templates/workouts/exercicio.html static/css/app.css workouts/test_grafico_do_exercicio.py workouts/test_exercicio_leitura.py
git commit -m "A tela do exercício desenha a carga máxima das últimas doze sessões — SVG por template, cor por token"
```

---

## Depois das quatro tarefas (o orquestrador)

1. Suíte completa no worktree (`manage.py test --noinput`, banco livre), exit code capturado direto.
2. Browser QA local (`scripts/qa/nav.py`, 390 claro/escuro): série que supera → aviso `--recorde` animado; Esc fecha; `/conta/excluir/` com aviso pendente → botão clicável (`elementFromPoint`); 404 sem aviso; detalhe do exercício com curva; reduced-motion sem animação.
3. Revisão adversarial por subagente somente-leitura (procura teste fraco, sabota).
4. Entrega: branch `mercado/padroes` → PR → CI → merge pela API (`scripts/github.py`, quando `ci/gate-no-github` estiver em `main`; senão push com hook) → `/saude/` → smoke → QA em produção com conta descartável → conta apagada → demo intacto.
