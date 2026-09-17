# Padrões de mercado — Fase 2 (corrida) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A corrida vira pilar inteiro: registro manual com histórico, edição e exclusão; conta na ofensiva e no gasto do dia; planos 5K/10K de 8 semanas lidos de uma doutrina escrita; e o aviso "GPS fraco" some depois de uma leitura boa.

**Architecture:** Tudo se apoia no que existe: `Corrida` ganha dois campos aditivos (`origem`, `sensacao`) e três telas Django clássicas (form/confirmação) com `op_id` escondido para idempotência; a ofensiva ganha uma consulta no ponto único de `streaks.calcular`; o gasto é uma função pura lida da doutrina e somada em `day_summary`; a doutrina da corrida usa o MESMO parser de tabelas do TREINO.md (extraído para reutilização) e um modelo `PlanoDeCorrida` de uma linha por pessoa; o B29 é uma linha no JS com teste por regex no padrão existente.

**Tech Stack:** Django 5.2, PostgreSQL, templates, CSS único, JS sem build, `RunnerUnico`.

**Spec:** `docs/superpowers/specs/2026-09-17-mercado-fase-2-corrida-design.md`

## Global Constraints

- **Não tocar** `workouts/test_ficha_de_verdade.py`, `workouts/test_treino_md.py`, os contratos da API (`api/tests.py`, `api/views.py`) nem a branch `design/mesa-e-ferro`.
- Os tetos da corrida vêm de `workouts/corrida_views.py` (`DISTANCIA_MINIMA_M`, `DISTANCIA_MAXIMA_M`, `DURACAO_MAXIMA_S`, `VELOCIDADE_MAXIMA_MS`) — importar, nunca copiar (`MesmosLimitesTests` compara as cópias).
- `achievements` intocado (contrato "treinou = um ExerciseLog na data" e `test_nao_ha_conquista_de_dado_que_o_app_nao_tem`).
- Números com vírgula (`floatformat`, `Decimal`); `:has()` proibido; 44 px de alvo; cor por token; pt-BR; docstrings dizem POR QUÊ com o caso real.
- Idempotência: todo POST que cria usa `op_id` + constraint `uma_corrida_por_operacao`; duplo toque = uma corrida.
- Banco de teste PRIVADO deste worktree: `test_nutriplan_corrida` (`.env` aponta para `nutriplan_corrida`). Rodar: `.venv/Scripts/python.exe manage.py test <modulos> --noinput` da raiz. **Nunca** `pg_terminate_backend`, nunca `NUTRIPLAN_IGNORAR_RUNNER_UNICO`, nunca a suíte inteira dentro de uma tarefa.
- Commits em pt-BR com o caso real; `git commit` roda o pre-commit; nunca `--no-verify`; sem sabotagem, temporário ou segredo no commit.
- Editar com Edit/Write (heredoc do Bash altera barras invertidas).

---

## Propriedade de arquivos

| tarefa | edita | ordem |
|---|---|---|
| T1 | `workouts/models.py` (Corrida), nova migração, `workouts/corrida_views.py` (views manuais), `workouts/forms_corrida.py` (novo), `workouts/urls.py`, `templates/workouts/corridas.html`, novos `templates/workouts/corrida_form.html` e `corrida_excluir.html`, `static/css/app.css` (seção da corrida), novo `workouts/test_corrida_manual.py` | 1ª |
| T2 | `plans/streaks.py`, `plans/tracking.py` (`day_summary`), `templates/plans/today.html` (ou o parcial do saldo), `workouts/corrida.py` (`gasto_kcal`), `docs/briefs/corrida/CORRIDA.md` (só a seção Gasto — T3 escreve o resto), novo `plans/test_gasto_da_corrida.py`, `plans/test_streaks.py` | 2ª (usa `origem` de T1 só para nada — independente, mas serial pelo banco) |
| T3 | `docs/briefs/corrida/CORRIDA.md` (planos e fontes), `workouts/doutrina.py` (extrair parser), novo `workouts/doutrina_corrida.py`, `workouts/models.py` (`PlanoDeCorrida`) + migração, `workouts/corrida_views.py` (plano), `workouts/urls.py`, `templates/workouts/corridas.html` (cartão do plano), novo `templates/workouts/corrida_plano.html`, novo `workouts/test_corrida_md.py` | 3ª (depois de T1: mesmos arquivos) |
| T4 | `static/js/corrida.js`, `workouts/test_corrida_v1.py` | 4ª (pequena) |

---

### Task 1: Registro manual, edição e exclusão

**Files:**
- Modify: `workouts/models.py` — `class Corrida` (~l. 1259–1342)
- Create: `workouts/migrations/00XX_corrida_origem_sensacao.py` (via `makemigrations`)
- Create: `workouts/forms_corrida.py`
- Modify: `workouts/corrida_views.py` (novas views), `workouts/urls.py` (~l. 37–38)
- Modify: `templates/workouts/corridas.html` (botão, itens, vazio)
- Create: `templates/workouts/corrida_form.html`, `templates/workouts/corrida_excluir.html`
- Modify: `static/css/app.css` (a seção onde vivem `.corrida*` — localizar com grep `corrida`)
- Test: `workouts/test_corrida_manual.py`

**Interfaces:**
- Consumes: `Corrida`, `corrida_views.{DISTANCIA_MINIMA_M, DISTANCIA_MAXIMA_M, DURACAO_MAXIMA_S, VELOCIDADE_MAXIMA_MS}`, `partials/field.html`, padrão de `ExcluirContaView`/`excluir_conta.html`.
- Produces: `Corrida.origem` (`"gps"|"manual"`, default `"gps"`), `Corrida.sensacao` (`""|"leve"|"normal"|"pesada"`); rotas `workouts:corrida_nova`, `workouts:corrida_editar`, `workouts:corrida_excluir`; `CorridaManualForm.para_corrida(user, op_id) -> Corrida` (não salva).

- [ ] **Step 1: Ler** `workouts/models.py::Corrida`, `workouts/corrida_views.py` inteiro, `templates/workouts/corridas.html`, `templates/accounts/excluir_conta.html`, `accounts/views.py::ExcluirContaView`, `accounts/forms.py::PesagemForm` (campo decimal com vírgula), `templates/partials/field.html`, `workouts/test_corrida_registro.py` (helpers e como cria corridas).

- [ ] **Step 2: Teste que falha** — `workouts/test_corrida_manual.py`:

```python
# -*- coding: utf-8 -*-
"""A corrida registrada à mão — esteira, relógio, celular no bolso.

BENCHMARK-2026-09 (d): Strava e NRC têm registro manual de graça; um pilar só
com GPS ao vivo parece inacabado (DELTA de 16/09, D5/U20). Aqui o registro
manual reutiliza os tetos do GPS (`corrida_views`), o `op_id` da fila
(duplo toque = uma corrida) e o padrão de exclusão em duas etapas da conta.

Corrida por GPS não se edita: o traço contradiria os números.
"""
import re
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts.models import Corrida
from workouts.tests import create_user


def _campos(html):
    return dict(re.findall(r'name="([a-z_]+)"[^>]*?value="([^"]*)"', html))


class ORegistroManualTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="manual@exemplo.com")
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()

    def _post(self, op_id=None, **extra):
        dados = {"distancia_km": "5,2", "tempo": "28:10", "data": self.hoje.isoformat(),
                 "sensacao": "normal", "op_id": op_id or uuid.uuid4().hex}
        dados.update(extra)
        return self.client.post(reverse("workouts:corrida_nova"), dados)

    def test_o_get_traz_um_op_id_escondido_e_a_data_de_hoje(self):
        html = self.client.get(reverse("workouts:corrida_nova")).content.decode()
        campos = _campos(html)
        self.assertEqual(len(campos["op_id"]), 32)
        self.assertEqual(campos["data"], self.hoje.isoformat())

    def test_cria_com_virgula_e_mm_ss(self):
        r = self._post()
        self.assertEqual(r.status_code, 302)
        c = Corrida.objects.get(user=self.pessoa)
        self.assertEqual((c.distancia_m, c.duracao_s, c.origem, c.sensacao), (5200, 1690, "manual", "normal"))
        self.assertEqual(timezone.localtime(c.comecou_em).hour, 12)
        self.assertEqual(c.terminou_em - c.comecou_em, timedelta(seconds=1690))

    def test_h_mm_ss_tambem_vale(self):
        self._post(distancia_km="21,1", tempo="1:58:30")
        self.assertEqual(Corrida.objects.get().duracao_s, 7110)

    def test_o_duplo_toque_grava_uma_corrida(self):
        op = uuid.uuid4().hex
        self._post(op_id=op); self._post(op_id=op)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 1)

    def test_recusa_data_futura_tetos_e_velocidade_impossivel(self):
        amanha = (self.hoje + timedelta(days=1)).isoformat()
        for extra in ({"data": amanha}, {"distancia_km": "0,01"}, {"distancia_km": "301"},
                      {"tempo": "13:00:00"}, {"distancia_km": "10", "tempo": "10:00"}):
            r = self._post(**extra)
            self.assertEqual(r.status_code, 200, extra)
            self.assertContains(r, 'aria-invalid="true"')
        self.assertEqual(Corrida.objects.count(), 0)

    def test_a_lista_mostra_a_mao_a_sensacao_e_os_links(self):
        self._post()
        html = self.client.get(reverse("workouts:corridas")).content.decode()
        c = Corrida.objects.get()
        self.assertIn("à mão", html)
        self.assertIn("normal", html.lower())
        self.assertIn(reverse("workouts:corrida_editar", args=[c.pk]), html)
        self.assertIn(reverse("workouts:corrida_excluir", args=[c.pk]), html)


class EdicaoEExclusaoTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="edita@exemplo.com")
        self.outra = create_user(email="outra@exemplo.com")
        self.client.force_login(self.pessoa)
        agora = timezone.now()
        self.manual = Corrida.objects.create(user=self.pessoa, op_id="m1", origem="manual", comecou_em=agora - timedelta(minutes=30), terminou_em=agora, distancia_m=5000, duracao_s=1800)
        self.gps = Corrida.objects.create(user=self.pessoa, op_id="g1", origem="gps", comecou_em=agora - timedelta(hours=2), terminou_em=agora - timedelta(hours=1), distancia_m=8000, duracao_s=3600)

    def test_edita_a_manual(self):
        url = reverse("workouts:corrida_editar", args=[self.manual.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"distancia_km": "5,5", "tempo": "30:00", "data": timezone.localdate().isoformat(), "sensacao": "pesada"})
        self.assertEqual(r.status_code, 302)
        self.manual.refresh_from_db()
        self.assertEqual((self.manual.distancia_m, self.manual.duracao_s, self.manual.sensacao), (5500, 1800, "pesada"))

    def test_gps_nao_edita_e_corrida_alheia_e_404(self):
        self.assertEqual(self.client.get(reverse("workouts:corrida_editar", args=[self.gps.pk])).status_code, 404)
        self.client.force_login(self.outra)
        self.assertEqual(self.client.get(reverse("workouts:corrida_editar", args=[self.manual.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("workouts:corrida_excluir", args=[self.manual.pk])).status_code, 404)

    def test_exclusao_em_duas_etapas_vale_para_gps_e_manual(self):
        for corrida in (self.manual, self.gps):
            url = reverse("workouts:corrida_excluir", args=[corrida.pk])
            html = self.client.get(url).content.decode()
            self.assertIn("Excluir esta corrida", html)
            self.assertIn("Cancelar", html)
            self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(Corrida.objects.filter(user=self.pessoa).count(), 0)
```
Conferir `create_user` em `workouts/tests.py` (assinatura) e ajustar; conferir se `Corrida` exige outros campos obrigatórios (ler o modelo).

- [ ] **Step 3: Rodar e ver falhar** — `.venv/Scripts/python.exe manage.py test workouts.test_corrida_manual --noinput` → erros de rota/campo.

- [ ] **Step 4: Modelo** — em `Corrida`:
```python
    class Origem(models.TextChoices):
        GPS = "gps", "GPS"
        MANUAL = "manual", "à mão"

    class Sensacao(models.TextChoices):
        LEVE = "leve", "leve"
        NORMAL = "normal", "normal"
        PESADA = "pesada", "pesada"

    #: De onde veio o número. O GPS traz parciais e traço; o registro à mão traz
    #: só distância e tempo — e por isso só ele se edita (BENCHMARK-2026-09, d).
    origem = models.CharField(max_length=8, choices=Origem.choices, default=Origem.GPS)
    #: Como foi. Vazio para o GPS (a tela do GPS não pergunta — ainda).
    sensacao = models.CharField(max_length=8, choices=Sensacao.choices, blank=True, default="")
```
`makemigrations workouts -n corrida_origem_sensacao`.

- [ ] **Step 5: Form** — `workouts/forms_corrida.py`:
```python
# -*- coding: utf-8 -*-
"""O registro manual de corrida: distância com vírgula, tempo como no relógio."""
import re
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone

from .corrida_views import DISTANCIA_MAXIMA_M, DISTANCIA_MINIMA_M, DURACAO_MAXIMA_S, VELOCIDADE_MAXIMA_MS
from .models import Corrida

_TEMPO = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})$")


class CorridaManualForm(forms.Form):
    distancia_km = forms.CharField(label="Distância", widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "5,2", "sufixo": "km"}))
    tempo = forms.CharField(label="Tempo", help_text="mm:ss ou h:mm:ss", widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "28:10"}))
    data = forms.DateField(label="Dia", widget=forms.DateInput(attrs={"type": "date"}))
    sensacao = forms.ChoiceField(label="Como foi?", choices=[("", "prefiro não dizer")] + list(Corrida.Sensacao.choices), required=False, widget=forms.RadioSelect)

    def clean_distancia_km(self):
        bruto = self.cleaned_data["distancia_km"].strip().replace(".", ",")
        try:
            km = Decimal(bruto.replace(",", "."))
        except InvalidOperation:
            raise forms.ValidationError("Use números, como 5,2.")
        metros = int(km * 1000)
        if metros < DISTANCIA_MINIMA_M:
            raise forms.ValidationError("Corrida de menos de %d m não entra." % DISTANCIA_MINIMA_M)
        if metros > DISTANCIA_MAXIMA_M:
            raise forms.ValidationError("Mais de %d km num dia só não." % (DISTANCIA_MAXIMA_M // 1000))
        return metros

    def clean_tempo(self):
        m = _TEMPO.match(self.cleaned_data["tempo"].strip())
        if not m:
            raise forms.ValidationError("Escreva como no relógio: 28:10 ou 1:58:30.")
        h, mi, s = (int(x) if x else 0 for x in m.groups())
        segundos = h * 3600 + mi * 60 + s
        if segundos <= 0:
            raise forms.ValidationError("O tempo precisa ser maior que zero.")
        if segundos > DURACAO_MAXIMA_S:
            raise forms.ValidationError("Mais de 12 horas não é uma corrida.")
        return segundos

    def clean_data(self):
        dia = self.cleaned_data["data"]
        if dia > timezone.localdate():
            raise forms.ValidationError("A corrida ainda não aconteceu.")
        return dia

    def clean(self):
        dados = super().clean()
        metros, segundos = dados.get("distancia_km"), dados.get("tempo")
        if metros and segundos and metros / segundos > VELOCIDADE_MAXIMA_MS:
            self.add_error("tempo", "Mais rápido que o recorde dos 100 m — confira distância e tempo.")
        return dados

    def preencher(self, corrida):
        """Aplica os campos limpos numa `Corrida` (nova ou existente); não salva."""
        inicio = timezone.make_aware(datetime.combine(self.cleaned_data["data"], time(12, 0)))
        corrida.comecou_em = inicio
        corrida.duracao_s = self.cleaned_data["tempo"]
        corrida.terminou_em = inicio + timedelta(seconds=corrida.duracao_s)
        corrida.distancia_m = self.cleaned_data["distancia_km"]
        corrida.sensacao = self.cleaned_data.get("sensacao") or ""
        corrida.origem = Corrida.Origem.MANUAL
        return corrida
```
Conferir se `corrida_views` importa algo de `forms_corrida` (evitar import circular: as views importam o form, o form importa só as constantes — se as constantes vivem em `corrida_views`, mover os quatro tetos para `workouts/corrida.py`? NÃO — `MesmosLimitesTests` os lê de `corrida_views`; importar de lá está certo, e `corrida_views` não deve importar o form no topo: importar dentro das views novas).

- [ ] **Step 6: Views e rotas** — em `workouts/corrida_views.py`:
```python
class CorridaNovaView(OnboardingRequiredMixin, View):
    """GET: formulário com `op_id` escondido; POST: cria. Duplo toque = uma corrida."""
    template_name = "workouts/corrida_form.html"

    def get(self, request):
        from .forms_corrida import CorridaManualForm
        form = CorridaManualForm(initial={"data": timezone.localdate()})
        return render(request, self.template_name, {"form": form, "op_id": uuid.uuid4().hex, "titulo": "Registrar corrida", "nav": "running"})

    def post(self, request):
        from .forms_corrida import CorridaManualForm
        form = CorridaManualForm(request.POST)
        op_id = (request.POST.get("op_id") or "")[:64]
        if not form.is_valid() or not op_id:
            return render(request, self.template_name, {"form": form, "op_id": op_id or uuid.uuid4().hex, "titulo": "Registrar corrida", "nav": "running"}, status=200)
        corrida = form.preencher(Corrida(user=request.user, op_id=op_id))
        try:
            with transaction.atomic():
                corrida.save()
        except IntegrityError:
            pass  # o mesmo op_id já entrou — é o duplo toque
        messages.success(request, "Corrida registrada.")
        return redirect("workouts:corridas")


class CorridaEditarView(OnboardingRequiredMixin, View):
    template_name = "workouts/corrida_form.html"

    def _corrida(self, request, pk):
        return get_object_or_404(Corrida, pk=pk, user=request.user, origem=Corrida.Origem.MANUAL)

    def get(self, request, pk):
        from .forms_corrida import CorridaManualForm
        c = self._corrida(request, pk)
        form = CorridaManualForm(initial={"distancia_km": ("%.2f" % (c.distancia_m / 1000)).replace(".", ","), "tempo": _relogio(c.duracao_s), "data": timezone.localdate(c.comecou_em), "sensacao": c.sensacao})
        return render(request, self.template_name, {"form": form, "titulo": "Editar corrida", "corrida": c, "nav": "running"})

    def post(self, request, pk):
        from .forms_corrida import CorridaManualForm
        c = self._corrida(request, pk)
        form = CorridaManualForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "titulo": "Editar corrida", "corrida": c, "nav": "running"})
        form.preencher(c).save()
        messages.success(request, "Corrida atualizada.")
        return redirect("workouts:corridas")


class CorridaExcluirView(OnboardingRequiredMixin, View):
    def get(self, request, pk):
        c = get_object_or_404(Corrida, pk=pk, user=request.user)
        return render(request, "workouts/corrida_excluir.html", {"corrida": c, "nav": "running"})

    def post(self, request, pk):
        get_object_or_404(Corrida, pk=pk, user=request.user).delete()
        messages.success(request, "Corrida excluída.")
        return redirect("workouts:corridas")
```
`_relogio(segundos)` → `"mm:ss"` ou `"h:mm:ss"` (reutilizar o filtro `relogio` de `templatetags/corrida.py` se for função pura; senão 4 linhas). Ler como `OnboardingRequiredMixin` é importado nas views existentes. Rotas em `urls.py` ao lado de `corridas/`: `corridas/nova/` (`corrida_nova`), `corridas/<int:pk>/editar/` (`corrida_editar`), `corridas/<int:pk>/excluir/` (`corrida_excluir`).

- [ ] **Step 7: Templates** — `corrida_form.html` estende `base.html` como `corridas.html`; `<form method="post">` com `{% csrf_token %}`, `{% if op_id %}<input type="hidden" name="op_id" value="{{ op_id }}">{% endif %}`, os quatro campos via `{% include "partials/field.html" with field=form.distancia_km %}` etc., botão primário "Salvar corrida" e link "Cancelar" para `workouts:corridas`. `corrida_excluir.html`: cartão "Excluir esta corrida?" com `{{ corrida.distancia_m|km }} · {{ corrida.duracao_s|relogio }} · {{ corrida.comecou_em|date:"d/m/Y" }}`, `<form method="post">` botão `btn btn--perigo btn--block` "Excluir corrida", link `btn btn--ghost btn--block` "Cancelar". `corridas.html`: abaixo do painel GPS, `<a class="btn btn--ghost btn--block" href="{% url 'workouts:corrida_nova' %}">Registrar corrida à mão</a>`; em cada item: `{% if corrida.origem == "manual" %}<span class="corrida__origem">à mão</span>{% endif %}`, `{% if corrida.sensacao %}<span class="corrida__sensacao">{{ corrida.get_sensacao_display }}</span>{% endif %}`, links "editar" (só manual) e "excluir" com 44 px (classe de link-botão existente). Vazio: "Nenhuma corrida ainda. Comece pelo GPS ou registre uma à mão."

- [ ] **Step 8: Verde, sabotagem, commit** — rodar `workouts.test_corrida_manual workouts.test_corrida_registro workouts.test_corrida_legivel`. Sabotagens: (a) tirar `origem=MANUAL` do `get_object_or_404` de editar → `test_gps_nao_edita…` vermelho; (b) tirar `user=request.user` de excluir → `…corrida_alheia_e_404` vermelho; (c) trocar `>` por `>=` na velocidade → o caso `10 km em 10:00` (16,7 m/s) continua vermelho — então sabotar com `* 10` no limite → `test_recusa…` vermelho. Restaurar. Commit: "Corrida registrada à mão: histórico, edição e exclusão — o pilar deixa de ter uma ação só".

---

### Task 2: A corrida conta na ofensiva e no gasto

**Files:**
- Modify: `plans/streaks.py::calcular` (~l. 133–137)
- Create: `workouts/corrida.py::gasto_kcal` (função pura) — ler `docs/briefs/corrida/CORRIDA.md` seção Gasto via `workouts/doutrina_corrida.py` **só depois de T3**; nesta tarefa a constante vive em `workouts/corrida.py` como `FATOR_KCAL_POR_KG_KM = Decimal("0.9")` com docstring e fonte; T3 passa a lê-la do documento e cobra que os dois batem.
- Modify: `plans/tracking.py::day_summary` (~l. 153–203) e o template da Home que mostra o saldo (localizar "faltam" em `templates/plans/`)
- Test: `plans/test_streaks.py` (estender), `plans/test_gasto_da_corrida.py` (novo)

**Interfaces:**
- Consumes: `Corrida` (`user`, `comecou_em`, `distancia_m`), `Profile.current_weight`, `day_summary(user, day)` (dict com `remaining_kcal`).
- Produces: `workouts.corrida.gasto_kcal(distancia_m, peso_kg) -> int`; `day_summary[...]["gasto_corrida_kcal"]: int`; `remaining_kcal` já somado.

- [ ] **Step 1: Ler** `plans/streaks.py` inteiro, `plans/test_streaks.py` (helpers `_treinar`, `_comer`), `plans/tracking.py::day_summary`, o template da Home onde `remaining_kcal`/"faltam" aparece, `accounts.models.Profile.current_weight`.

- [ ] **Step 2: Testes que falham**

Em `plans/test_streaks.py`, na classe existente:
```python
    def test_a_corrida_cumpre_o_dia_previsto(self):
        """Dia de musculação em que a pessoa só correu: moveu-se, a ofensiva segue."""
        from workouts.models import Corrida
        dia = self._dia_previsto()  # usar o helper que a classe já tem para achar um dia de treino
        inicio = timezone.make_aware(datetime.combine(dia, time(7, 0)))
        Corrida.objects.create(user=self.user, op_id="c1", origem="manual", comecou_em=inicio, terminou_em=inicio + timedelta(minutes=30), distancia_m=5000, duracao_s=1800)
        self._comer(dia)
        self.assertTrue(calcular(self.user, hoje=dia)["hoje"]["treino"])  # ajustar à forma real do retorno
```
(ler `calcular` e os testes vizinhos para a forma exata do retorno e dos helpers; o teste existente "rest day não quebra" continua.)

`plans/test_gasto_da_corrida.py`:
```python
# -*- coding: utf-8 -*-
"""A corrida registrada entra no saldo do dia — por cima do plano, e visível.

`plans/calculations.py` rejeita MET para o PLANO (o fator de atividade cobre o
dia a dia). A corrida entra por cima, líquida: 0,9 kcal por kg por km (≈1
bruto, descontado o repouso; fonte no CORRIDA.md). Recomendo rever: quem se
declarou "altamente ativo" por correr conta duas vezes.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from plans import tracking
from workouts.corrida import gasto_kcal
from workouts.models import Corrida
from workouts.tests import create_user


class OGastoTests(TestCase):
    def test_a_formula(self):
        self.assertEqual(gasto_kcal(5000, Decimal("80")), 360)   # 0,9 × 80 × 5
        self.assertEqual(gasto_kcal(0, Decimal("80")), 0)
        self.assertEqual(gasto_kcal(5000, None), 0)

    def test_o_saldo_do_dia_soma_a_corrida_e_a_home_diz(self):
        pessoa = create_user(email="gasto@exemplo.com")  # com peso e plano — ver helper
        self.client.force_login(pessoa)
        hoje = timezone.localdate()
        antes = tracking.day_summary(pessoa, hoje)["remaining_kcal"]
        inicio = timezone.make_aware(datetime.combine(hoje, time(7, 0)))
        Corrida.objects.create(user=pessoa, op_id="g1", origem="manual", comecou_em=inicio, terminou_em=inicio + timedelta(minutes=30), distancia_m=5000, duracao_s=1800)
        depois = tracking.day_summary(pessoa, hoje)
        self.assertEqual(depois["gasto_corrida_kcal"], gasto_kcal(5000, pessoa.profile.current_weight))
        self.assertEqual(depois["remaining_kcal"], antes + depois["gasto_corrida_kcal"])
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("da corrida de hoje", html)

    def test_sem_corrida_a_home_nao_fala_em_corrida(self):
        pessoa = create_user(email="semcorrida@exemplo.com")
        self.client.force_login(pessoa)
        self.assertNotIn("da corrida de hoje", self.client.get(reverse("plans:today")).content.decode())
```

- [ ] **Step 3: Rodar e ver falhar.**

- [ ] **Step 4: `gasto_kcal`** em `workouts/corrida.py`:
```python
#: kcal por quilo por quilômetro, LÍQUIDO do repouso. Correr custa ≈1 kcal/kg/km
#: bruto (ACSM, equação metabólica da corrida); tirar o que o corpo gastaria
#: parado dá ≈0,9. Entra por cima do plano, que já cobre o dia a dia pelo fator
#: de atividade (`plans/calculations.py` rejeita MET para o plano, de propósito).
FATOR_KCAL_POR_KG_KM = Decimal("0.9")


def gasto_kcal(distancia_m, peso_kg) -> int:
    """Quanto uma corrida gastou, em kcal inteiras. Sem peso, zero — nunca um chute."""
    if not distancia_m or peso_kg is None:
        return 0
    return int((FATOR_KCAL_POR_KG_KM * Decimal(peso_kg) * Decimal(distancia_m) / 1000).to_integral_value())
```

- [ ] **Step 5: Ofensiva** — em `streaks.calcular`, logo após montar `treinou`:
```python
    # Correu conta: a régua da ofensiva é "moveu-se", não "fez a letra". Uma
    # consulta, no mesmo ponto que decide a musculação (BENCHMARK-2026-09, d).
    from workouts.models import Corrida
    treinou |= {
        timezone.localtime(c).date()
        for c in Corrida.objects.filter(user=user, comecou_em__date__gte=inicio).values_list("comecou_em", flat=True)
    }
```
(conferir como `inicio` é definido; usar `__date__gte` com o fuso local — ler como o projeto faz em outros lugares, ex. `localdate`.)

- [ ] **Step 6: `day_summary`** — somar as corridas do dia: `gasto = sum(gasto_kcal(c.distancia_m, peso) for c in Corrida.objects.filter(user=user, comecou_em__date=day))`; `resumo["gasto_corrida_kcal"] = gasto`; `resumo["remaining_kcal"] += gasto`. Template da Home: perto de "faltam N kcal", `{% if resumo.gasto_corrida_kcal %}<span class="hint">+{{ resumo.gasto_corrida_kcal }} kcal da corrida de hoje</span>{% endif %}` (nome da variável conforme o template real).

- [ ] **Step 7: Verde, sabotagem, commit** — módulos: `plans.test_streaks plans.test_gasto_da_corrida plans.tests`. Sabotagens: tirar o `|=` → vermelho; fator 0,9 → 1,9 → `test_a_formula` vermelho; `remaining_kcal += gasto` removido → vermelho. Commit: "A corrida conta: cumpre a ofensiva do dia e entra no saldo por cima do plano".

---

### Task 3: Planos 5K e 10K lidos da doutrina

**Files:**
- Create: `docs/briefs/corrida/CORRIDA.md`
- Modify: `workouts/doutrina.py` — extrair `_faixa` e `_tabelas` para `workouts/doutrina_md.py` (novo) e reimportar (sem mudar comportamento; `test_treino_md.py` continua verde)
- Create: `workouts/doutrina_corrida.py`
- Modify: `workouts/models.py` (`PlanoDeCorrida`) + migração; `workouts/corrida_views.py` (`PlanoDeCorridaView`, contexto da lista); `workouts/urls.py`; `templates/workouts/corridas.html` (cartão); novo `templates/workouts/corrida_plano.html`
- Test: `workouts/test_corrida_md.py`

**Interfaces:**
- Produces: `doutrina_corrida.planos() -> {("5k","iniciante"): {"semanas": 8, "sessoes_por_semana": 3}, …}`, `doutrina_corrida.sessoes(plano, nivel, semana) -> [ {"sessao": 1, "descricao": str, "minutos": int}, … ]`, `doutrina_corrida.fator_kcal() -> Decimal` (cobra que bate com `workouts.corrida.FATOR_KCAL_POR_KG_KM`); modelo `PlanoDeCorrida(user, plano, nivel, comecou_em, ativo)` com `semana_atual(hoje)` (1–8, `None` depois) e `sessoes_feitas(semana) -> int`.

- [ ] **Step 1: Ler** `docs/briefs/treino/TREINO.md` (forma das tabelas e das Fontes), `workouts/doutrina.py` inteiro, `workouts/test_treino_md.py` inteiro.

- [ ] **Step 2: O documento** — `docs/briefs/corrida/CORRIDA.md`, seções: título e propósito; `## Planos` com a tabela `| plano | nivel | semanas | sessoes_por_semana |` (5k/iniciante 8/3, 5k/intermediario 8/3, 10k/iniciante 8/3, 10k/intermediario 8/3); `## Sessões` com `| plano | nivel | semana | sessao | descricao | minutos |` — 96 linhas. Conteúdo (escrever de verdade, com progressão semanal):
  - 5k iniciante (Couch to 5K comprimido de 9 para 8 semanas; dizer na fonte): sem.1 `8 × (1 min corrida + 1,5 min caminhada)` 25 min ×3; sem.2 `6 × (1,5 + 2)` 26; sem.3 `2 × (1,5 + 1,5 + 3 + 3)` 24; sem.4 `3 + 1,5 + 5 + 2,5 + 3 + 1,5 + 5` 26; sem.5 `5 + 3 + 5 + 3 + 5` 25 / `8 + 5 + 8` 26 / `20 corridos` 25; sem.6 `5+3+8+3+5` 28 / `10+3+10` 28 / `25 corridos` 30; sem.7 `25 corridos` 30 ×3; sem.8 `28 / 28 / 30 corridos (5 km)` 33.
  - 5k intermediário: sem.1–8 três sessões: `fácil 20–35 min`, `intervalos 6–10 × 400 m`, `longo 30–50 min`, progredindo 10 %/semana com a 4ª e a 8ª mais leves (Higdon 5K Intermediate).
  - 10k iniciante (Higdon 10K Novice, 8 sem.): três corridas de `2,5 → 5 mi` em progressão com semana 4 e 8 de descarga — converter para km e minutos.
  - 10k intermediário (Higdon 10K Intermediate): fácil / tempo run / longo, 8 semanas.
  `## Gasto`: `| medida | valor |` com `fator_kcal_por_kg_km | 0,9`. `## Fontes`: NHS Couch to 5K; Hal Higdon 5K Intermediate, 10K Novice, 10K Intermediate; ACSM Guidelines (equação metabólica da corrida). `## Como o motor obedece`: 3 frases.

- [ ] **Step 3: Teste que falha** — `workouts/test_corrida_md.py`, no molde de `test_treino_md.py`: leitor devolve o que está escrito (compara `doutrina_corrida` com um segundo parser do próprio teste), 4 planos × 8 semanas × 3 sessões = 96, minutos > 0 e descrição não vazia, `fator_kcal() == corrida.FATOR_KCAL_POR_KG_KM`, seção Fontes cita "Couch to 5K" e "Higdon", `ValueError` quando uma linha falta (copiar o documento para tmp sem uma linha e apontar `DOCUMENTO`); `PlanoDeCorrida.semana_atual` (dia 0 → 1; dia 7 → 2; dia 56 → `None`); `sessoes_feitas` conta corridas da semana; a tela mostra "Semana 1 de 8" e as 3 sessões; escolher plano cria um ativo e desativa o anterior.

- [ ] **Step 4: Extrair o parser** — `workouts/doutrina_md.py` com `faixa(texto)` e `tabelas(texto) -> dict[tuple(cabecalho)] -> list[dict]` movidos de `doutrina.py`, que passa a `from .doutrina_md import faixa as _faixa, tabelas as _tabelas`. `test_treino_md.py` verde sem alteração.

- [ ] **Step 5: `doutrina_corrida.py`** — `DOCUMENTO = BASE_DIR / "docs/briefs/corrida/CORRIDA.md"`; `carregar()` `@lru_cache` lendo as duas tabelas e a de gasto; `planos()`, `sessoes(plano, nivel, semana)`, `fator_kcal()`; `ValueError` com o nome da linha que falta.

- [ ] **Step 6: Modelo, view, tela** — `PlanoDeCorrida` (`user` FK, `plano` `5k|10k`, `nivel` `iniciante|intermediario`, `comecou_em` date, `ativo` bool; `UniqueConstraint(user, condition=Q(ativo=True), name="um_plano_de_corrida_ativo")`); `semana_atual(hoje)`; `sessoes_feitas(hoje)` = corridas entre o início da semana atual e hoje. `PlanoDeCorridaView` (`corridas/plano/`): GET lista as 4 opções; POST `plano`+`nivel` desativa o ativo e cria um novo com `comecou_em=hoje`; POST `encerrar=1` desativa. `HistoricoDeCorridasView.get_context_data` ganha `plano` (ativo ou `None`), `semana`, `sessoes` (com `feita: bool` para as `k ≤ sessoes_feitas`). Cartão em `corridas.html` acima da lista: "Semana N de 8 · Plano 5K iniciante", `<ol>` das sessões (descrição · minutos · ✓ quando feita), link "trocar ou encerrar"; sem plano: "Quer um plano? 5K ou 10K em 8 semanas" → link.

- [ ] **Step 7: Verde, sabotagem, commit** — módulos: `workouts.test_corrida_md workouts.test_treino_md workouts.test_corrida_manual`. Sabotagens: apagar uma linha do CORRIDA.md → `ValueError` no teste de faltando (e o teste de 96 vermelho); fator 0,9 → 0,8 só no doc → `fator_kcal` vermelho; `semana_atual` sem o teto 8 → vermelho. Commit: "Planos 5K e 10K de oito semanas, escritos em CORRIDA.md e lidos pelo motor".

---

### Task 4: "GPS fraco" some depois de uma leitura boa (B29)

**Files:**
- Modify: `static/js/corrida.js::receber` (~l. 150–197)
- Test: `workouts/test_corrida_v1.py` (nova classe ao lado de `OErroDizOQueAconteceuTests`)

- [ ] **Step 1: Teste que falha**
```python
class ALeituraBoaApagaOAvisoTests(SimpleTestCase):
    """B29: "Sinal de GPS fraco" ficava na tela para sempre depois de o sinal voltar."""

    def test_toda_leitura_aceita_limpa_a_mensagem(self):
        corpo = corpo_da_funcao("receber")
        # `dizer("")` precisa existir FORA do ramo da primeira âncora: contamos as
        # ocorrências — a versão com bug tinha uma só (na âncora).
        self.assertGreaterEqual(corpo.count('dizer("")'), 2, corpo)
```
(ler os helpers de `test_corrida_v1.py:13-36` e usar `corpo_da_funcao` como os vizinhos.)

- [ ] **Step 2: Correção** — em `receber`, no ramo em que a leitura é ACEITA com âncora existente (antes de empurrar o ponto/parcial), acrescentar `dizer("");` com o comentário `// B29: sinal voltou — o aviso de GPS fraco sai.`

- [ ] **Step 3: Verde, sabotagem, commit** — `workouts.test_corrida_v1`; sabotagem: remover a linha → vermelho. Commit: "B29: 'GPS fraco' some na primeira leitura boa, não só na primeira âncora".

---

## Depois das quatro tarefas (o orquestrador)

1. Suíte completa no banco privado (`fundo.py rodar`), exit code direto.
2. Browser QA local (390/768, claro/escuro): registrar à mão (vírgula, `mm:ss`), erro de velocidade impossível, editar, excluir em duas etapas, lista com "à mão"/sensação, Home com "+N kcal da corrida de hoje", ofensiva marcada num dia só de corrida, escolher plano 5K → cartão "Semana 1 de 8" → registrar corrida → sessão 1 ✓.
3. Revisão adversarial de branch inteira; uma onda de correção; re-revisão.
4. PR `mercado/corrida` → CI → merge pela API → `/saude/` → smoke → QA em produção com conta descartável (registrar à mão, editar, excluir; apagar a conta) → demo intacto.
