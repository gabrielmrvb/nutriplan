# Onboarding em três etapas (C-ONB) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (inline, com checkpoints) sob o protocolo `nutriplan-missao`. Steps use
> checkbox (`- [ ]`) syntax for tracking. Arquivos serializados (um editor por
> vez): `accounts/views.py`, `accounts/forms.py`, `accounts/tests.py`,
> `templates/accounts/onboarding/step.html`.

**Goal:** Substituir o wizard de seis passos (`/conta/onboarding/1..6/`,
"Passo N/6 · X%") por TRÊS etapas reais, progressivas e mobile-first —
"Etapa 1 de 3 · Sobre você", "Etapa 2 de 3 · Seu objetivo e rotina",
"Etapa 3 de 3 · Sua personalização" com CTA final "Criar meu plano" — sem
alterar uma regra sequer do motor nutricional ou de treino, e com quem já
passou pelo fluxo antigo continuando compatível.

**Architecture:** As seis views viram três, compondo os formulários que já
existem (`BodyDataForm`; `GoalForm` + `TrainingForm` + `SplitPreferenceForm`;
`RestrictionsForm` + `InteressesForm`) em vez de reescrevê-los — validação,
`save()` e "escolhas abrem em branco" continuam onde estão. A coluna
`Profile.onboarding_step` mantém o nome e passa a contar etapas (1..3);
`ONBOARDING_DONE = 7` NÃO muda, então toda conta concluída continua concluída
sem tocar em linha nenhuma; só quem parou no meio é remapeado por `RunPython`
(2..6 → 2..3). A divisão de treino é revelação progressiva dentro da etapa 2:
o servidor decide se ela é exigida (≥ 4 dias), o JavaScript só mostra antes.
"Criar meu plano" conclui, monta a ficha (`acertar_ficha`, já existente) E o
plano alimentar (`plans.services.sync_active_plan`, idempotente) e manda para
a Home.

**Tech Stack:** Django 5.2.17 · templates servidos · `app.css` único · JS sem
build (`pwa.js`) · agent-browser 0.37.1 (QA) · Render (deploy por `git push`).

**Spec:** a mensagem do dono de 15/09/2026 ("PARE TEMPORARIAMENTE A ONDA 2 E
CORRIJA A PENDÊNCIA C-ONB") e a decisão C-ONB do plano mestre
(`docs/superpowers/plans/2026-09-14-plano-mestre.md`, §3). Onde os dois
divergem no CONTEÚDO das etapas, vale a mensagem do dono (é mais recente e
mais específica).

## Global Constraints

- Exatamente TRÊS etapas reais: rotas `/conta/onboarding/1/`, `/2/`, `/3/`;
  nenhuma rota `/4/`, `/5/`, `/6/` responde 200 (404).
- Texto de progresso: "Etapa 1 de 3", "Etapa 2 de 3", "Etapa 3 de 3". Zero
  ocorrências de "Passo N/6", "/6" ou porcentagem em `templates/` e em
  qualquer HTML servido.
- CTAs: etapa 1 "Continuar"; etapa 2 "Continuar" + "Voltar"; etapa 3 "Criar
  meu plano" + "Voltar". Na EDIÇÃO de quem já concluiu: "Salvar" + "Voltar"
  (para a tela de origem), como hoje.
- Voltar/avançar não apagam dados (cada etapa salva no POST; GET reabre com o
  que está salvo). Atualizar a página não corrompe (GET idempotente; a guarda
  manda quem pula etapa para a etapa pendente).
- Erro junto ao campo (`partials/field.html` já faz isso; `non_field_errors`
  no topo do formulário só para a regra de prioridade e da janela do dia).
- Sem alterar regras do motor: `create_routine`, `prescrever_semana`,
  `sync_active_plan`, `calculate`, `TrainingForm.save` (horário preservado,
  duração de `perfil.duracao_treino`, experiência `or ""`), `acertar_rotina`
  (zero dias desliga a rotina) ficam como estão.
- Compatibilidade: `ONBOARDING_DONE = 7` inalterado; `onboarding_complete`
  inalterado; migration só `RunPython` sobre `onboarding_step < 7`, reversa
  no-op; nenhuma conta concluída é enviada ao onboarding; editar o perfil
  não reabre o wizard.
- Alvo de toque 44 px; sem `:has()`; sem valor cru novo no CSS (catracas
  `TETO_FONT_SIZE_CRU = 119`, `TETO_ESPACO_CRU = 244` só descem); nada rola
  na horizontal; texto ≥ 11 px.
- Conta demo (`carlos.demo@nutriplan.invalid`) intocada. Em produção, só a
  conta descartável `qa-onb-20260915@nutriplan-qa.invalid`, apagada no fim
  pela tela "Excluir conta".
- Nunca `git add -A`; `artifacts/` fora; suíte completa no `pre-push`;
  deploy provado por sinal observável, `/saude/`, smoke; notificação sonora
  ao terminar.

---

## Mapeamento do fluxo atual (baseline, lido no código em 15/09/2026)

| passo | rota | view | form | grava | condição |
|---|---|---|---|---|---|
| 1 Seus dados | `/conta/onboarding/1/` | `BodyDataStepView` | `BodyDataForm` | `Profile.sex/birth_date/height_cm`, `WeightEntry` de hoje | sempre |
| 2 Seu objetivo | `/2/` | `GoalStepView` | `GoalForm` | `Profile.goal/activity_level` | sempre |
| 3 Sua rotina | `/3/` | `TrainingStepView` | `TrainingForm` | `TrainingDay` (dias; horário preservado; `duration_min` de `duracao_treino`), `Profile.experiencia/wake_time/sleep_time/duracao_treino` | sempre (`PASSO_TREINOS = 3`) |
| 4 Sua divisão | `/4/` | `SplitPreferenceStepView` | `SplitPreferenceForm` | `Profile.split_preference`, `split_preference_confirmada=True` | só se `preferencia_muda_a_divisao(dias)` (≥ 4 dias) — `passos_de` |
| 5 Sua comida | `/5/` | `RestrictionsStepView` | `RestrictionsForm` | `Profile.meal_style`, `dietary_tags` | sempre |
| 6 Prioridade | `/6/` | `InteressesStepView` | `InteressesForm` | `Profile.interesse_*`, `prioridade` | sempre; último (`ONBOARDING_LAST_STEP = 6`) |

Progresso: `Profile.onboarding_step` = PRÓXIMO passo a fazer (default 2 após
o cadastro criar o perfil no passo 1); `ONBOARDING_DONE = 7`;
`advance_onboarding(step, proximo)` nunca retrocede. Tela: "Passo
{{posicao}}/{{total}} · {{pct}}%" com `posicao` no CAMINHO (4 ou 5 passos
para quem pula o 4). Efeitos colaterais no fim (`finish_step`, `proximo >=
ONBOARDING_DONE`): `acertar_ficha()` (T1.1 da onda 1) e redirect para
`plans:today`; o plano alimentar nasce na PRIMEIRA abertura da Home
(`sync_active_plan`). Na edição (`was_complete`): passo 3 salvo com ≥ 4 dias e
`split_preference_confirmada=False` desvia para o passo 4 antes de voltar;
`acertar_ficha()` nos passos 3 e 4; "Alterações salvas." e volta para
`?origem=` (lista fechada: `treino` → painel; senão Perfil).

Links que entram em passo específico: `templates/accounts/profile.html:98
(2), :109 (1), :122 (3), :181 (3), :228 (6), :279 (5), :327 (4)`;
`templates/workouts/routine.html:51, :408, :591 (3, ?origem=treino)`.

Baseline em produção (agent-browser, 15/09/2026 10:2x, conta descartável):
`/conta/onboarding/1/` mostra "Passo 1/6 · 16%", h1 "Seus dados", CTA
"Continuar" — capturas em `scratchpad/shots-onb/baseline/prod-passo1-{320,375,390,430}.png`.

## Estrutura final

| etapa | rota | h1 | campos | CTA |
|---|---|---|---|---|
| 1 de 3 — Sobre você | `/conta/onboarding/1/` | "Sobre você" | sexo biológico, data de nascimento, altura, peso atual (com a razão curta de cada dado) | Continuar |
| 2 de 3 — Seu objetivo e rotina | `/conta/onboarding/2/` | "Seu objetivo e rotina" | objetivo, nível de atividade, experiência de treino, dias da semana (0 a 7), janela do dia (acorda/dorme, que o cardápio usa), **divisão de treino revelada só com ≥ 4 dias** | Continuar · Voltar |
| 3 de 3 — Sua personalização | `/conta/onboarding/3/` | "Sua personalização" | estilo do cardápio, restrições alimentares, áreas de interesse + prioridade; **resumo** das escolhas das etapas 1-2 | Criar meu plano · Voltar |

Duração (`duracao_treino`) e horário do treino continuam FORA da tela
(decisões de 10/09/2026: "não tem como responder" e "opcional, ausência é
estado de verdade"). Nada novo entra no motor.

`Profile.onboarding_step` (mesma coluna): 1 = etapa 1 pendente, 2 = etapa 2
pendente, 3 = etapa 3 pendente, 7 = concluído (`ONBOARDING_DONE`, inalterado).
Migration `accounts/00XX_onboarding_em_tres_etapas` (`RunPython`, só
`onboarding_step < 7`): {1→1, 2→2, 3→2, 4→3, 5→3, 6→3}.

---

### Task 1: Guarda textual — o app não mostra seis passos

**Files:**
- Create: `accounts/test_tres_etapas.py`

**Interfaces:**
- Produces: a régua que os outros tasks têm de fazer passar: rotas, textos,
  CTAs, persistência ida-e-volta, efeitos da conclusão.

- [x] **Step 1: Escrever os testes que reprovam o wizard de seis passos**

```python
"""O onboarding tem TRÊS etapas reais — nem seis, nem seis maquiadas de três.

Decisão C-ONB (14/09/2026) e ordem do dono (15/09/2026): a produção ainda
mostrava "Passo 1/6 · 16%" em `/conta/onboarding/1/`, seis rotas e CTA
"Salvar". Aqui: três rotas (1, 2, 3), "Etapa N de 3", CTAs "Continuar" /
"Continuar" / "Criar meu plano", voltar sem perder dado, atualizar sem
corromper, e a conclusão montando cardápio E ficha.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ONBOARDING_DONE, Profile, TrainingDay, User
from plans.models import NutritionPlan
from workouts.models import TrainingPlan

ETAPA1 = {"sex": "M", "birth_date": "1995-04-12", "height_cm": 178, "weight_kg": "82,4"}
ETAPA2 = {
    "goal": "cut", "activity_level": "light", "experiencia": "intermediario",
    "weekdays": ["0", "2", "4"], "wake_time": "07:00", "sleep_time": "23:30",
}
ETAPA3 = {"meal_style": "quick", "interesses": ["treino"], "prioridade": "treino"}


def etapa(n):
    return reverse("accounts:onboarding_step", kwargs={"step": n})


class TresEtapasReaisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = User.objects.create_user(email="tres@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)

    def test_so_existem_tres_rotas(self):
        self.assertEqual(self.client.get(etapa(1)).status_code, 200)
        for n in (4, 5, 6, 0, 7):
            with self.subTest(n=n):
                self.assertEqual(self.client.get(etapa(n)).status_code, 404)

    def test_a_etapa_1_diz_1_de_3_e_continuar(self):
        html = self.client.get(etapa(1)).content.decode()
        self.assertIn("Etapa 1 de 3", html)
        self.assertIn("Sobre você", html)
        self.assertIn(">Continuar<", html.replace("\n", "").replace("  ", ""))
        self.assertNotIn("Passo 1/6", html)
        self.assertNotIn("/6", html.split("<main", 1)[1])
        self.assertNotIn("%", re.search(r'class="wizard__label[^"]*"[^>]*>([^<]*)<', html).group(1))

    def test_ida_e_volta_nao_perde_dados(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        volta = self.client.get(etapa(1)).content.decode()
        self.assertIn('value="178"', volta)
        self.assertIn('value="82,4"', volta.replace("82.4", "82,4"))
        de_novo = self.client.get(etapa(2)).content.decode()
        self.assertIn('value="0"', de_novo)  # segunda-feira continua marcada
        self.assertIn("checked", de_novo)
        self.assertEqual(Profile.objects.get(user=self.user).goal, "cut")

    def test_atualizar_a_pagina_nao_corrompe_o_andamento(self):
        self.client.post(etapa(1), ETAPA1)
        for _ in range(3):
            self.assertEqual(self.client.get(etapa(2)).status_code, 200)
        self.assertEqual(Profile.objects.get(user=self.user).onboarding_step, 2)
        # Pular para a 3 antes da 2 devolve para a 2.
        self.assertRedirects(self.client.get(etapa(3)), etapa(2))

    def test_criar_meu_plano_conclui_e_monta_cardapio_e_ficha(self):
        hoje = timezone.localdate().weekday()
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), {**ETAPA2, "weekdays": [str(hoje), str((hoje + 2) % 7), str((hoje + 4) % 7)]})
        html = self.client.get(etapa(3)).content.decode()
        self.assertIn("Etapa 3 de 3", html)
        self.assertIn("Criar meu plano", html)
        resposta = self.client.post(etapa(3), ETAPA3)
        self.assertRedirects(resposta, reverse("plans:today"))
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.onboarding_step, ONBOARDING_DONE)
        self.assertEqual(NutritionPlan.objects.filter(user=self.user, is_active=True).count(), 1)
        self.assertEqual(TrainingPlan.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_concluir_duas_vezes_nao_duplica_planos(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        self.client.post(etapa(3), ETAPA3)
        self.client.post(etapa(3), ETAPA3)
        self.assertEqual(NutritionPlan.objects.filter(user=self.user, is_active=True).count(), 1)
        self.assertEqual(TrainingPlan.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_zero_dias_conclui_sem_ficha_e_sem_500(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), {**ETAPA2, "weekdays": []})
        resposta = self.client.post(etapa(3), ETAPA3)
        self.assertRedirects(resposta, reverse("plans:today"))
        self.assertFalse(TrainingPlan.objects.filter(user=self.user).exists())
        self.assertTrue(NutritionPlan.objects.filter(user=self.user, is_active=True).exists())

    def test_treino_sem_horario_e_o_padrao_e_nao_quebra_nada(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        self.assertTrue(all(d.start_time is None for d in TrainingDay.objects.filter(user=self.user)))
        self.client.post(etapa(3), ETAPA3)
        self.assertEqual(self.client.get(reverse("plans:today")).status_code, 200)

    def test_a_divisao_so_e_exigida_com_quatro_dias_ou_mais(self):
        self.client.post(etapa(1), ETAPA1)
        quatro = {**ETAPA2, "weekdays": ["0", "1", "3", "5"]}
        resposta = self.client.post(etapa(2), quatro)
        self.assertEqual(resposta.status_code, 200)  # reprovou: falta a divisão
        self.assertContains(resposta, "divisão")
        self.assertEqual(Profile.objects.get(user=self.user).onboarding_step, 2)
        resposta = self.client.post(etapa(2), {**quatro, "split_preference": "two"})
        self.assertRedirects(resposta, etapa(3))
        perfil = Profile.objects.get(user=self.user)
        self.assertTrue(perfil.split_preference_confirmada)
        self.assertEqual(perfil.split_preference, "two")

    def test_com_tres_dias_a_divisao_nao_e_pedida_nem_confirmada(self):
        self.client.post(etapa(1), ETAPA1)
        self.assertRedirects(self.client.post(etapa(2), ETAPA2), etapa(3))
        self.assertFalse(Profile.objects.get(user=self.user).split_preference_confirmada)

    def test_a_etapa_3_resume_as_escolhas(self):
        self.client.post(etapa(1), ETAPA1)
        self.client.post(etapa(2), ETAPA2)
        html = self.client.get(etapa(3)).content.decode()
        for trecho in ("Emagrecer", "Seg", "Qua", "Sex", "178 cm", "82,4"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, html)


class QuemJaConcluiuTests(TestCase):
    """Compatibilidade: quem passou pelo fluxo antigo continua concluído e edita sem refazer."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        from plans.tests import create_complete_user
        self.user = create_complete_user(email="antigo@exemplo.com")
        self.client.force_login(self.user)

    def test_a_home_abre_e_nao_manda_para_o_onboarding(self):
        self.assertEqual(self.client.get(reverse("plans:today")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("accounts:onboarding")), reverse("plans:today"))

    def test_editar_uma_etapa_salva_e_volta_ao_perfil(self):
        html = self.client.get(etapa(2)).content.decode()
        self.assertIn(">Salvar<", html.replace("\n", "").replace("  ", ""))
        self.assertNotIn("Criar meu plano", html)
        resposta = self.client.post(etapa(2), {**ETAPA2, "goal": "bulk"})
        self.assertRedirects(resposta, reverse("accounts:profile"))
        self.assertEqual(Profile.objects.get(user=self.user).goal, "bulk")
        self.assertEqual(Profile.objects.get(user=self.user).onboarding_step, ONBOARDING_DONE)

    def test_editar_os_dias_pelo_treino_volta_ao_treino(self):
        resposta = self.client.post(etapa(2) + "?origem=treino", ETAPA2)
        self.assertRedirects(resposta, reverse("workouts:routine"), fetch_redirect_response=False)


class NenhumTemplateDizSeisPassosTests(TestCase):
    def test_zero_ocorrencias_de_passo_n_de_6(self):
        from pathlib import Path
        from django.conf import settings
        base = Path(settings.BASE_DIR)
        for arquivo in list((base / "templates").rglob("*.html")) + [base / "accounts" / "views.py"]:
            texto = arquivo.read_text(encoding="utf-8")
            with self.subTest(arquivo=arquivo.name):
                self.assertNotRegex(texto, r"Passo \{\{|Passo \d/6|/6 ·|step=[456]\b")
```

- [x] **Step 2: Rodar e ver reprovar** — `manage.py test accounts.test_tres_etapas`: rotas 4-6 respondem 200 (ou 302), "Etapa 1 de 3" ausente, etc.
- [x] **Step 3:** não implementar nada ainda; commit só do teste NÃO (o commit vem com a implementação, para o `pre-commit` não quebrar).

### Task 2: Modelo, constantes e migration

**Files:**
- Modify: `accounts/models.py:419-420` (`ONBOARDING_LAST_STEP = 3`; `ONBOARDING_DONE = 7` fica), docstring de `onboarding_step` (:589).
- Create: `accounts/migrations/00XX_onboarding_em_tres_etapas.py` (`RunPython`).
- Modify: `accounts/test_duracao_portao.py` / testes de migration existentes só se quebrarem.

- [x] Teste (em `accounts/test_tres_etapas.py`, classe `MigracaoTests` com `MigrationExecutor`, no molde de `plans/tests.py`/`accounts/test_duracao_portao.py`): perfis com `onboarding_step` ∈ {1,2,3,4,5,6,7} antes; depois {1,2,2,3,3,3,7}; reversa no-op; `tearDown` migra para `leaf_nodes()`.
- [x] Migration:

```python
from django.db import migrations

DE_PARA = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 3}

def para_tres_etapas(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    for antigo, novo in DE_PARA.items():
        if antigo != novo:
            Profile.objects.filter(onboarding_step=antigo).update(onboarding_step=novo)

class Migration(migrations.Migration):
    dependencies = [("accounts", "<última>")]
    operations = [migrations.RunPython(para_tres_etapas, migrations.RunPython.noop)]
```

- [x] `manage.py makemigrations --check` continua limpo (não há mudança de schema). Verde.

### Task 3: Views das três etapas

**Files:**
- Modify: `accounts/views.py` (`PASSO_TREINOS = 2`; `CAMINHO_*` e `passos_de` viram `ETAPAS = (1, 2, 3)`; `STEP_META` para 3; `OnboardingStepMixin` sem o desvio para o passo 4; `finish_step` chama `sync_active_plan` depois de `advance`; `STEP_VIEWS = {1: SobreVoceView, 2: ObjetivoERotinaView, 3: PersonalizacaoView}`; `onboarding_step()` responde 404 fora de 1..3).
- Modify: `accounts/forms.py` — nada estrutural; `RestrictionsForm.sem_resposta_previa` passa a `onboarding_step <= 3`; `TrainingForm` ganha o campo `split_preference` OPCIONAL? NÃO: composição, ver abaixo.

**Interfaces:**
- `ObjetivoERotinaView.get_forms()` → `{"objetivo": GoalForm, "rotina": TrainingForm, "divisao": SplitPreferenceForm}`; `divisao` só entra na validação quando `len(weekdays) >= 4` (`preferencia_muda_a_divisao`).
- `PersonalizacaoView.get_forms()` → `{"comida": RestrictionsForm, "areas": InteressesForm}`; contexto `resumo` = lista de `(rótulo, valor)`.
- `finish_step(profile)` → após `advance_onboarding(self.step, proximo)`: se concluiu agora, `self.acertar_ficha()` e `plans.services.sync_active_plan(user)` (dentro de `try/except IncompleteProfile` — não pode acontecer, mas não vira 500), `messages.success("Seu plano está pronto…")`, redirect Home.

- [x] Implementar `EtapaCompostaView(OnboardingStepMixin, TemplateView)` com `get_forms()` (instâncias com `data=request.POST or None`, `instance=profile`, `user=`), `post()` validando todas (todas `is_valid()` antes de salvar; salva em `transaction.atomic()`), `get_context_data` com `forms` e `form` = a primeira (para o template e para `non_field_errors`).
- [x] Divisão progressiva: `mostrar_divisao = dias >= 4` (dias = POST se houver, senão salvos); `SplitPreferenceForm` só valida se `mostrar_divisao`; ao salvar com ≥ 4 dias grava `split_preference_confirmada=True` (o `SplitPreferenceStepView.form_valid` antigo fazia isso).
- [x] Edição (`was_complete`): etapa 2 salva → `acertar_ficha()`; "Alterações salvas."; volta a `?origem=`.
- [x] Verde nos testes de Task 1 que dependem de view (rotas, ida-e-volta, conclusão, divisão).

### Task 4: Template das três etapas

**Files:**
- Modify: `templates/accounts/onboarding/step.html` (progresso "Etapa N de 3", trilha `N/3`, blocos por etapa, resumo na 3, CTAs, bloco `data-revela-divisao`, montagem só na 3).
- Modify: `static/css/app.css` (só se precisar de uma classe nova; sem valor cru).
- Modify: `static/js/pwa.js` (revelação progressiva: mostra `[data-revela-divisao]` quando ≥ 4 `input[name=weekdays]:checked`; sem JS o servidor mostra quando exigido).

- [x] Texto e razões curtas por campo (etapa 1): sexo "só para o cálculo da taxa metabólica", nascimento "a idade entra no gasto", altura e peso "a base do cálculo".
- [x] Verde nos testes textuais de Task 1; `config.tests` (CSS/alvos) verde.

### Task 5: Links de edição e telas vizinhas

**Files:**
- Modify: `templates/accounts/profile.html` (:98 → 2, :109 → 1, :122 → 2, :181 → 2, :228 → 3, :279 → 3, :327 → 2), `templates/workouts/routine.html` (:51, :408, :591 → 2, `?origem=treino`).
- [x] Teste em `accounts/test_tres_etapas.py`: nenhum `step=[456]` em templates (já na guarda de Task 1); `config/test_nomenclatura.py` continua verde.

### Task 6: Adaptar os testes que assumem seis passos

**Files:** `accounts/tests.py` (177 `step_url(`; fixtures `STEP1..STEP6`,
`complete_all_steps`, `PlanBuildingScreenTests`, `WizardProgressBarTests`,
`ValidationTests`, `AccessControlTests`, `WizardChromeTests`),
`accounts/test_primeira_passagem_em_branco.py`, `accounts/test_pilares.py`,
`accounts/test_prioridade_clara.py`, `accounts/test_areas.py`,
`accounts/test_ficha_nasce_no_concluir.py`, `config/test_nomenclatura.py`,
`plans/test_home_adaptativa.py`, `push/test_convite_instalacao.py` (só o
que reprovar), e a lista do Explore.

- [x] Fixtures: `STEP1` = etapa 1; `STEP2_3 = {**STEP2, **STEP3}` (+ `split_preference` quando ≥ 4 dias) = etapa 2; `STEP5_6 = {**STEP5, **STEP6}` = etapa 3; `step_url(n)` só com n ∈ {1,2,3}. Cada teste que afirmava "vai para o passo 4/5/6" passa a afirmar o equivalente em etapas — sem apagar a intenção do teste (ex.: "o passo 4 só aparece com 4 dias" vira "a divisão só é exigida com 4 dias").
- [x] `manage.py test accounts config plans.test_home_adaptativa push.test_convite_instalacao` verde.

### Task 7: Sabotagens, revisão adversarial, QA no navegador

- [x] Sabotagens (registro em `scratchpad/sabotagem_onb.txt`): (a) `ETAPAS = (1,2,3,4)` / rota 4 de volta → `test_so_existem_tres_rotas` vermelho; (b) template com "Passo {{ posicao }}/{{ total }}" → textual vermelho; (c) GET da etapa 1 sem `initial` (dados perdidos ao voltar) → ida-e-volta vermelho; (d) `finish_step` sem `acertar_ficha` → ficha vermelho; (e) `sync_active_plan` duas vezes criando plano novo (`create_plan` direto) → duplicação vermelho; (f) `OnboardingEntryView` mandando concluído para a etapa 1 → compatibilidade vermelho.
- [x] Revisão adversarial por subagente (leitura): diff inteiro contra as Global Constraints; o que ele achar entra antes do push.
- [x] QA local com agent-browser (conta descartável local): fluxo 1→2→1→2→3→Criar meu plano; 320/375/390/430/1024; 0 alvos < 44, 0 rolagem horizontal; capturas em `scratchpad/shots-onb/local/`.

### Task 8: Publicar e provar

- [ ] `manage.py check`, `makemigrations --check`, `git diff --check`, commits por unidade, `git fetch`, push pelo `pre-push` (suíte completa), deploy provado (HTML servido de `/conta/onboarding/1/` com "Etapa 1 de 3" — com a conta descartável de produção), `/saude/`, smoke.
- [ ] QA em PRODUÇÃO com agent-browser, conta `qa-onb-20260915@nutriplan-qa.invalid` (já criada no baseline): os 13 passos do dono, nas 4 larguras + desktop; capturas em `scratchpad/shots-onb/prod/`. Ao fim, "Excluir conta" pela tela; demo intocado (GET em `/demo/hoje/` antes/depois com a mesma impressão).
- [ ] Relatório final + notificação sonora; retomar a onda 2 em T2.1.

## Self-review

- **Cobertura da spec:** rotas/textos/CTAs (T1, T3, T4); persistência ida-e-volta e refresh (T1, T3); erros junto ao campo (partial existente, T4); teclado/CTA (QA T7/T8 — sem tabbar no wizard); compatibilidade e edição (T1 `QuemJaConcluiuTests`, T2 migration, T5 links); conclusão com cálculo + cardápio + ficha + zero dias + sem horário + redirect (T1, T3); sem alterar motor (Global); demo intocado (T8); testes obrigatórios da lista (T1 + T6 cobrem cadastro novo, edição, ida-e-volta, refresh, validação/limites — `ValidationTests` existentes adaptados —, objetivos, atividades, experiências, zero/3/4/5 dias, sem horário, cardápio, ficha, duplicação, sessão expirada — `AccessControlTests` —, etapa fora de ordem, compatibilidade, ausência de "/6", três rotas).
- **Placeholders:** `00XX` da migration é o próximo número livre (conferir `ls accounts/migrations`); `<última>` idem.
- **Consistência:** `ETAPAS`, `PASSO_TREINOS = 2`, `ONBOARDING_LAST_STEP = 3`, `ONBOARDING_DONE = 7`, `acertar_ficha()` (existe desde T1.1), `sync_active_plan(user) -> (plano, mudou)`.
