# A Alimentação sugere, não impõe — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (escolhido pelo dono) para executar tarefa a tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** a tela `/alimentacao/` deixa de repetir a Home e de decidir pela pessoa: sem o cartão AGORA, com toda refeição fechada (a da vez apenas marcada), o CTA chamado "Registrar", os dois CTAs com o mesmo peso, a sugestão do dia virando chip, e "Não comi"/"Comi outra coisa" como duas ações secundárias de verdade.

**Architecture:** tudo acontece no template `templates/plans/alimentacao.html` e no CSS; o servidor não muda — `slot.estado` continua vindo de `plans/agora.py` e o orçamento de consultas fica onde está. O parcial `_agora.html` perde o ramo `sugestao` (ele só existia para esta tela) e continua servindo a Home como ponteiro.

**Tech Stack:** Django 5.2 templates, CSS sem framework (`static/css/app.css`, seções numeradas), testes `django.test.TestCase`, agent-browser para o QA.

**Spec:** a missão do dono de 24/09/2026 (cinco decisões, no corpo da conversa e reproduzidas aqui em Global Constraints). Ela SUBSTITUI, com data e motivo: a doutrina de 20/09 "só a refeição da vez nasce aberta" e as de 23/09 "só a sugestão do dia é verde" e "o CTA é Comi esta".

## Global Constraints

- **Decisões do dono (24/09/2026), verbatim no que decidem:**
  1. o cartão AGORA sai da Alimentação (fica só na Home); a tela abre com o anel e o cardápio;
  2. **nenhuma** `<details>` nasce aberta, em hora nenhuma; a refeição da vez (`slot.estado == "agora"`) e a pendente ganham marca discreta na própria linha;
  3. o botão de cada opção se chama **"Registrar"** ("Comi esta" sai de toda tela);
  4. as duas opções têm o **mesmo peso visual**; a sugestão do rodízio vira um **chip "sugestão de hoje"** no card;
  5. "Pulei" e "Comi outra coisa" viram **duas ações secundárias iguais** (`btn--ghost`, 44 px) abaixo dos cards: **"Não comi"** e **"Comi outra coisa"**, esta abrindo um campo de verdade (`<details>`, `<input>` com o `<datalist>` que já existe, placeholder "o que você comeu", botão "Registrar" ao lado).
- **Não muda:** o card de receita (ilustração, macros, ingredientes, porção, "Ver a receita"), a folha/painel da receita, o anel e o `topo.modo`, a lista de compras, `OptionLabel` no banco, `plans/agora.py`, `plans/views.py` e o orçamento de consultas de `plans:alimentacao` (18, em `plans/test_stress.py`).
- **Idempotência intacta:** "Não comi" (`status=skipped`) e "Comi outra coisa" (`status=off_plan`) continuam com o mesmo formulário, a mesma URL (`plans:mark_meal`), o mesmo `data-celebra` e o mesmo `op_id` da fila offline.
- **44 px** de alvo em tudo que se toca (a régua é `config/tests.py::TouchTargetTests`); texto de interface nunca abaixo de 11 px; `:has()` proibido para estrutura; número com vírgula e `tabular-nums`; nada rola na horizontal.
- **Sem valor cru novo** de espaçamento/tamanho de texto no CSS: os tetos de `config/test_design_system.py` (`TETO_FONT_SIZE_CRU = 107`, `TETO_ESPACO_CRU = 229`) não sobem. Use tokens.
- **Sem `<script>` inline sem nonce e sem `on*=`** (a régua da CSP é `config/test_cabecalhos.py`); esta missão não precisa de JS novo.
- **Medida antes (agent-browser, conta local com plano, 390 px):** `/alimentacao/` tem **2.614 px** às 09:00, 14:00 e 20:00 — cartão AGORA presente, 1 refeição aberta, 4 fechadas. O número final entra no relatório.
- Commits em pt-BR no estilo do `git log`, terminando com `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Ledger antes de tocar `app.css`/`templates/plans/` — já escrito às 15:50.
- Testes SEMPRE em primeiro plano, por módulo; banco privado `nutriplan_alim`; nunca `pg_terminate_backend`, nunca `NUTRIPLAN_IGNORAR_RUNNER_UNICO`.

---

### Task 1: O cartão AGORA sai da Alimentação

**Files:**
- Modify: `templates/plans/alimentacao.html:49-63` (o `{% if acao.tipo == 'refeicao' %}` e o comentário acima dele)
- Modify: `templates/plans/_agora.html:44-85` (o ramo `{% elif acao.tipo == 'refeicao' and sugestao %}`)
- Modify: `static/css/app.css:9703-9719` (`.agora__sugestao`, `.agora__receita*`, `.agora__ver`) e `:7441,7466,7493,7517` (as entradas de `.agora__ver` nas regras de foco/toque)
- Test: `plans/test_card_de_refeicao.py` (classe nova `OCartaoAgoraFicaSoNaHomeTests`)

**Interfaces:**
- Produces: `/alimentacao/` sem `.agora-card`; `_agora.html` sem o parâmetro `sugestao`.
- Consumes: nada.

- [ ] **Step 1: Teste que falha**

Em `plans/test_card_de_refeicao.py`, depois de `CardDeRefeicaoTests`:

```python
class OCartaoAgoraFicaSoNaHomeTests(TestCase):
    """O cartão AGORA repetia a refeição que estava logo abaixo, com o mesmo
    botão (decisão do dono, 24/09/2026, depois de usar o app). A Alimentação
    abre com o anel e o cardápio; quem orquestra o dia é a Hoje."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        cls.user = create_complete_user(email="sem-agora@exemplo.com")
        cls.plan = services.create_plan(cls.user)

    def setUp(self):
        self.client.force_login(self.user)

    def test_a_alimentacao_nao_tem_o_cartao_agora(self):
        with mock.patch("plans.views.relogio", return_value=_as(8)):
            html = self.client.get(reverse("plans:alimentacao")).content.decode()
        self.assertNotIn("agora-card", html)
        self.assertNotIn("agora__sugestao", html)
        # Controle positivo: a tela continua sendo a da Alimentação, com o
        # anel e o cardápio — a asserção de ausência não passou por engano
        # numa página de erro ou num redirect.
        self.assertIn("today-hero", html)
        self.assertIn('<article class="receita', html)

    def test_a_hoje_continua_com_o_cartao_agora_apontando_a_refeicao(self):
        with mock.patch("plans.views.relogio", return_value=_as(8)):
            html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("agora-card", html)
        self.assertIn("Ver refeição", html)
        # E a Hoje nunca registrou comida: o ramo que fazia isso era da
        # Alimentação e saiu junto.
        self.assertNotIn("agora__sugestao", html)
```

- [ ] **Step 2: Rodar e ver vermelho**

Run: `.venv/Scripts/python.exe manage.py test plans.test_card_de_refeicao.OCartaoAgoraFicaSoNaHomeTests -v 1`
Expected: FAIL em `test_a_alimentacao_nao_tem_o_cartao_agora` ("agora-card" presente).

- [ ] **Step 3: Tirar o cartão da tela**

Em `templates/plans/alimentacao.html`, apague o bloco inteiro do `{% if acao.tipo == 'refeicao' %}…{% endif %}` (linhas ~49-63) e o comentário acima, e ponha no lugar:

```
      {% comment %}
        O CARTÃO AGORA NÃO ENTRA AQUI (decisão do dono, 24/09/2026, depois de
        usar o app). Ele repetia a refeição que está logo abaixo, com o mesmo
        botão: o herói e o primeiro card do cardápio eram a mesma coisa dita
        duas vezes, e a tela abria 2.614px de altura por causa disso. O cartão
        fica na Hoje, que é o orquestrador do dia; a Alimentação abre com o
        anel (meta e saldo) e o cardápio.
      {% endcomment %}
```

- [ ] **Step 4: Tirar o ramo morto do parcial**

Em `templates/plans/_agora.html`, apague o `{% elif acao.tipo == 'refeicao' and sugestao %}` inteiro (o comentário, `.agora__sugestao`, o `<form>` e o `<a class="btn-link agora__ver">`) — com a Alimentação fora, ninguém mais passa `sugestao`, e o ramo vira código que não roda. Ajuste o comentário do topo do arquivo (linhas 1-14): ele diz que o parcial é incluído por DUAS telas; passa a dizer que é da Hoje, com a data e o motivo. O ramo `{% else %}` (o ponteiro `acao.cta`) atende refeição como atende treino.

- [ ] **Step 5: CSS morto sai**

Em `static/css/app.css`, apague `.agora__sugestao`, `.agora__receita`, `.agora__receita-nome`, `.agora__receita-num` e `.agora__ver` (bloco ~9703-9719) e as ocorrências de `.agora__ver` nas listas de foco/toque (~7441, 7466, 7493, 7517) — deixe as vírgulas das listas coerentes. `.agora__cta` FICA (o ponteiro da Hoje usa).

- [ ] **Step 6: Verde e vizinhança**

Run: `.venv/Scripts/python.exe manage.py test plans.test_card_de_refeicao plans.test_home_adaptativa plans.test_hidratacao_v2 config.test_superficie_de_foco accounts.test_pilares -v 1`
Expected: PASS. Sabotagem: devolva o `{% include %}` do cartão na Alimentação → `test_a_alimentacao_nao_tem_o_cartao_agora` fica vermelho. Restaure.

- [ ] **Step 7: Commit**

```bash
git add templates/plans/alimentacao.html templates/plans/_agora.html static/css/app.css plans/test_card_de_refeicao.py
git commit -m "O cartão AGORA sai da Alimentação: ele repetia a refeição de baixo"
```

---

### Task 2: Nenhuma refeição nasce aberta — a da vez é marcada na linha

**Files:**
- Modify: `templates/plans/alimentacao.html:379-471` (o `{% if slot.estado == 'agora' or slot.log %}` do cabeçalho, o `{% if slot.estado != 'agora' %}` do `<details>` e o `<summary class="meal__linha">`)
- Modify: `static/css/app.css` (seção da linha da refeição, ~9505-9545: a marca dentro do `summary`)
- Test: `plans/test_opcoes_tocaveis.py` (`ARefeicaoFuturaFicaEmSegundoPlanoTests`), `plans/test_card_de_refeicao.py` (`CardDeRefeicaoTests.test_a_refeicao_da_vez_nasce_aberta_com_as_duas_receitas`)

**Interfaces:**
- Consumes: `slot.estado` (`resolvida`/`agora`/`pendente`/`futura`), inalterado.
- Produces: toda refeição não resolvida dentro de `<details class="meal__futuro">` fechado; `<summary class="meal__linha">` com `<span class="meal__marca meal__marca--agora">Agora</span>` quando `agora` e `<span class="meal__marca">Ficou para trás</span>` quando `pendente`.

- [ ] **Step 1: Testes que falham**

Em `plans/test_opcoes_tocaveis.py`, SUBSTITUA `test_a_refeicao_da_vez_continua_aberta` por:

```python
    def test_nenhuma_refeicao_nasce_aberta(self):
        """Decisão do dono, 24/09/2026: a pessoa abre a que quiser.

        Antes a da vez nascia aberta (doutrina de 20/09) e, com cards de
        receita no lugar de linhas, era ela sozinha que fazia a tela passar de
        2.600px. O estado continua vindo do servidor; o que mudou é o que a
        tela faz com ele — marcar em vez de abrir.
        """
        for corpo in self.cards():
            with self.subTest(card=corpo[:60]):
                self.assertNotIn("<details class=\"meal__futuro\" open", corpo)
        abertos = re.findall(r"<details[^>]*\sopen", self.html)
        self.assertEqual(abertos, [], "nenhuma sanfona do cardápio abre sozinha")

    def test_a_refeicao_da_vez_esta_marcada_na_linha(self):
        """Fechada, mas achável sem abrir: a marca vive no `<summary>`."""
        da_vez = [c for c in self.cards() if 'class="meal meal--agora"' in c]
        self.assertTrue(da_vez, "precisa de uma refeição de agora para medir")
        for corpo in da_vez:
            resumo = re.search(r"<summary.*?</summary>", corpo, re.S).group(0)
            self.assertIn("meal__marca--agora", resumo)
            self.assertIn("Agora", resumo)
```

(Use o helper `cards()` que a classe já tem para recortar cada `<article class="meal…">`; se ela não tiver, escreva um `_cards(html)` no módulo com `re.findall(r'<article class="meal.*?</article>', html, re.S)`.)

Em `ARefeicaoFuturaFicaEmSegundoPlanoTests.test_a_vencida_fica_em_uma_linha_com_o_convite_a_registrar`, acrescente a marca da pendente:

```python
            self.assertIn("Ficou para trás", corpo)
```

Em `plans/test_card_de_refeicao.py`, renomeie `test_a_refeicao_da_vez_nasce_aberta_com_as_duas_receitas` para `test_a_refeicao_da_vez_nasce_fechada_e_marcada` e troque as duas asserções finais:

```python
        pedaco = _card(html, primeiro.pk)
        self.assertIn('<details class="meal__futuro">', pedaco)
        self.assertIn("meal__marca--agora", pedaco)
```
(o resto — `meal--agora`, 10 cards de receita, o CTA — continua: as opções seguem no HTML, atrás de um toque.)

- [ ] **Step 2: Vermelho**

Run: `.venv/Scripts/python.exe manage.py test plans.test_opcoes_tocaveis plans.test_card_de_refeicao -v 1`

- [ ] **Step 3: Template**

Em `templates/plans/alimentacao.html`:
1. o cabeçalho de duas linhas passa a ser só de quem está RESOLVIDA: troque `{% if slot.estado == 'agora' or slot.log %}` por `{% if slot.log %}`;
2. o `<details>` passa a valer para todo mundo: troque as duas guardas `{% if slot.estado != 'agora' %}` (abertura na ~452 e fechamento na ~664) por `<details class="meal__futuro">` e `</details>` sem condição (o bloco inteiro já está dentro do `{% else %}` do `{% if slot.log %}`);
3. no `<summary class="meal__linha">`, depois do `{% if slot.estado == 'pendente' %}…{% else %}…{% endif %}` do kcal, acrescente a marca:

```
                  {% comment %}
                    A MARCA NA LINHA, e não a sanfona aberta (decisão do dono,
                    24/09/2026). A pessoa precisa ACHAR a refeição da vez sem
                    abrir nada; abrir era responder à pergunta errada — e
                    custava a tela inteira em altura. O texto é o `slot.estado`
                    que o servidor já escreve; a tela só escolhe a palavra.
                  {% endcomment %}
                  {% if slot.estado == 'agora' %}
                    <span class="meal__marca meal__marca--agora">Agora</span>
                  {% elif slot.estado == 'pendente' %}
                    <span class="meal__marca">Ficou para trás</span>
                  {% endif %}
```
4. o comentário grande acima do `<details>` (sobre "quem abre é o estado") é reescrito com a decisão nova, a data e o motivo.

- [ ] **Step 4: CSS**

A marca já existe (`.meal__marca`, `.meal__marca--agora`, app.css ~7691) e nasceu para o `.meal__head`; dentro do `<summary>` ela precisa de duas coisas: não empurrar o kcal (o `margin-left: auto` do `.meal__linha-kcal` já resolve a ordem) e não crescer a linha. Acrescente, na seção da linha (~9530, junto de `.meal__linha-kcal`):

```css
/* A marca dentro da LINHA fechada (24/09/2026): ela divide a linha que a hora
   e o nome já ocupam, e por isso não pode ter `margin-left: auto` — quem
   empurra para a direita é o kcal/o convite que vem antes dela. */
.meal__linha .meal__marca { margin-left: 0; }
```
Se a medição no navegador mostrar a linha passando de duas linhas a 320 px, acrescente `.meal__linha { flex-wrap: wrap; }` — e só então.

- [ ] **Step 5: Verde, altura e sabotagem**

Run: `.venv/Scripts/python.exe manage.py test plans.test_opcoes_tocaveis plans.test_card_de_refeicao plans.tests.OsSelosDaListaTests -v 1` (o nome exato da classe dos selos sai de `grep -n "selo de agora" plans/tests.py`).
Sabotagem: devolva `{% if slot.estado != 'agora' %}` → `test_nenhuma_refeicao_nasce_aberta` vermelho. Restaure.

- [ ] **Step 6: Commit**

```bash
git commit -am "Nenhuma refeição nasce aberta: a da vez é marcada na linha"
```

---

### Task 3: O botão de cada opção se chama "Registrar"

**Files:**
- Modify: `templates/plans/alimentacao.html:571-586` (o comentário e o rótulo)
- Modify: `templates/plans/_receita.html:97` (`{% translate "Comi esta" %}` → `{% translate "Registrar" %}`) e o comentário da linha 85
- Modify: `locale/pt_BR/LC_MESSAGES/django.po` (a entrada `msgid "Comi esta"` vira `msgid "Registrar"`; `msgstr` continua vazio — pt-BR é o idioma-fonte)
- Modify: `plans/tests.py:1453`, `plans/views.py:996,1015`, `config/acoes.py:8`, `config/test_acoes_com_tela.py:8`, `static/js/pwa.js:523,2186` — só COMENTÁRIOS que citam o rótulo antigo
- Test: `config/test_linguagem.py` (régua nova), `plans/test_opcoes_tocaveis.py`, `plans/test_card_de_refeicao.py`

**Interfaces:**
- Produces: nenhuma tela com "Comi esta"; o `aria-label` (`Registrar <receita> em <horário>`) continua como está.

- [ ] **Step 1: Régua + testes que falham**

Em `config/test_linguagem.py`, classe nova:

```python
#: O rótulo que saiu (decisão do dono, 24/09/2026): o card já diz QUAL receita
#: é, e o botão diz a AÇÃO. "Comi esta" era o card contando a mesma coisa duas
#: vezes, e virava mentira na folha da receita, onde não há "esta" nenhuma.
COMI_ESTA = re.compile(r"\bcomi esta\b", re.IGNORECASE)


class NenhumaTelaDizComiEstaTests(ComCadastroCompleto):
    def test_o_cardapio_e_a_receita_dizem_registrar(self):
        self.pessoa_completa()
        cardapio = self.client.get(reverse("plans:alimentacao")).content.decode()
        self.assertIsNone(COMI_ESTA.search(texto_visivel(cardapio)), "o cardápio")
        self.assertIn("Registrar", texto_visivel(cardapio))
        slot = ...  # o primeiro slot do plano da pessoa; a folha é `plans:receita`
        folha = self.client.get(reverse("plans:receita", args=[slot.pk, opcao.pk])).content.decode()
        self.assertIsNone(COMI_ESTA.search(texto_visivel(folha)), "a folha da receita")
        self.assertIn("Registrar", texto_visivel(folha))

    def test_nenhuma_tela_de_quem_tem_cardapio_diz_comi_esta(self):
        self.pessoa_completa()
        for rota in (reverse("plans:today"), reverse("plans:alimentacao"),
                     reverse("plans:history"), reverse("ajuda:index")):
            with self.subTest(rota=rota):
                texto = texto_visivel(apenas_o_main(self.client.get(rota).content.decode()))
                self.assertIsNone(COMI_ESTA.search(texto), texto[:400])
```
(o jeito de pegar `slot`/`opcao` é o mesmo de `plans/test_card_de_refeicao.py::AReceitaEUmaTelaTests` — copie a montagem de lá, não invente.)

E troque as asserções que pinam o rótulo velho: `plans/test_opcoes_tocaveis.py:69` e `plans/test_card_de_refeicao.py:91` passam a `self.assertIn(">Registrar<", …)` ancorado nos sinais de tag; `plans/test_card_de_refeicao.py:398` (`assertNotIn(">Comi esta<")`) vira `assertNotIn(">Registrar<", html)` — a refeição já registrada continua sem oferecer o botão.

- [ ] **Step 2: Vermelho.** **Step 3:** trocar o rótulo nos dois templates e no `.po`; reescrever os comentários que explicavam "Comi esta" (eles passam a explicar por que o rótulo é a AÇÃO). **Step 4:** verde em `config.test_linguagem plans.test_opcoes_tocaveis plans.test_card_de_refeicao config.test_i18n`. Sabotagem: devolva "Comi esta" ao `_receita.html` → a régua fica vermelha.

- [ ] **Step 5: Commit** — `"O botão diz a ação: Registrar"`

---

### Task 4: As duas opções com o mesmo peso, e a sugestão vira chip

**Files:**
- Modify: `templates/plans/alimentacao.html:488` (a classe do `<article>`) e `:583` (a classe do botão)
- Modify: `static/css/app.css` (`.receita__chip` novo, perto de `.receita` ~9562)
- Test: `plans/test_opcoes_tocaveis.py::AOpcaoAEASugestaoEABEAAlternativaTests`, `plans/test_card_de_refeicao.py`

**Decisão de qual botão (registrar no CLAUDE.md):** os dois ficam **`btn--ghost`** — dois primários lado a lado numa tela com cinco refeições seriam dez botões verdes inclinados, que é o oposto de "a tela sugere"; o contorno mantém os dois iguais e devolve o verde para quem ele identifica no app (a ação do dia na Home e o "Registrar" do formulário de fora do plano). O chip é quem diz a sugestão.

- [ ] **Step 1: Teste que falha** — em `AOpcaoAEASugestaoEABEAAlternativaTests`, `test_na_refeicao_atual_so_a_primeira_opcao_e_primaria` vira:

```python
    def test_as_duas_opcoes_tem_o_mesmo_peso(self):
        """Decisão do dono, 24/09/2026: o verde só na primeira lia como "faça
        esta". A sugestão do rodízio continua existindo — é ela que equilibra a
        lista de compras — e passa a ser dita por um chip, não pela cor."""
        acoes = self.acoes()
        self.assertGreaterEqual(len(acoes), 2, "a refeição atual precisa de duas opções")
        classes = [re.search(r'class="([^"]+)"', a).group(1) for a in acoes]
        self.assertEqual(classes[0], classes[1])
        for classe in classes:
            self.assertIn("btn--ghost", classe)
            self.assertNotIn("btn--primary", classe)

    def test_a_sugestao_do_dia_e_um_chip_no_card(self):
        cards = re.findall(r'<article class="receita.*?</article>', self.html, re.S)
        sugeridos = [c for c in cards if "receita__chip" in c]
        self.assertTrue(sugeridos, "nenhum card marca a sugestão do dia")
        self.assertIn("sugestão de hoje", sugeridos[0].lower())
        # Uma por refeição, e é a primeira: o rodízio ordena.
        self.assertEqual(len(sugeridos), len(re.findall(r'<article class="meal', self.html)) - <resolvidas>)
```
(meça o número esperado com o fixture da classe; se for mais simples, afirme `len(sugeridos) * 2 == len(cards)`.)

- [ ] **Step 2: Vermelho.** **Step 3:** no template, `class="receita{% if forloop.first %} receita--sugerida{% endif %}"` fica (a classe ainda é o gancho do chip) e o botão passa a `class="btn btn--ghost btn--block"` sempre; dentro do `<a class="receita__abrir">`, logo antes do `<h3>`, entra:

```
                    {% if forloop.first %}
                      {% comment %}
                        A SUGESTÃO DO DIA É UM CHIP (24/09/2026). Ela continua
                        sendo escolhida pelo `rodizio` — é o que equilibra a
                        lista de compras —, mas dizê-la pela COR do botão era
                        dizer "faça esta"; o dono pediu uma tela que sugere.
                      {% endcomment %}
                      <span class="receita__chip">sugestão de hoje</span>
                    {% endif %}
```

- [ ] **Step 4: CSS** — `.receita__chip` reusa a linguagem do `.chip` sem herdar o `text-transform: uppercase` da versão tocável:

```css
/* O chip da sugestão: contorno fino, minúsculas, sem peso de botão. Ele
   informa; quem age são os dois CTAs iguais abaixo. */
.receita__chip {
  align-self: start;
  padding: .15rem var(--espaco-3);
  border: 1px solid var(--fio-forte);
  border-radius: var(--quina-p);
  color: var(--text-dim);
  font-size: var(--texto-xs);
  font-weight: 600;
}
```
`.receita--sugerida` não pinta mais nada por si (confira se já pintava; se não tinha regra, continua sem).

- [ ] **Step 5:** verde nos dois módulos + `config.test_design_system` (os tetos não sobem) + `config.tests.TouchTargetTests`. Sabotagem: devolva `btn--primary` ao primeiro → o teste do mesmo peso fica vermelho.

- [ ] **Step 6: Commit** — `"As duas opções pesam igual; a sugestão do dia é um chip"`

---

### Task 5: "Não comi" e "Comi outra coisa" viram duas ações de verdade

**Files:**
- Modify: `templates/plans/alimentacao.html:605-662` (o bloco `.meal__secundarias`)
- Modify: `static/css/app.css:9644-9675` (`.meal__secundarias` e `.meal__secundarias .fora__abrir`)
- Test: `plans/test_opcoes_tocaveis.py::…test_as_acoes_secundarias_continuam_secundarias`, `plans/test_card_de_refeicao.py::test_pulei_nao_tem_porcao` (só o nome do rótulo), `config/tests.py::TouchTargetTests` (já cobre)

**Interfaces:**
- Produces: `<div class="meal__secundarias">` com dois filhos de mesmo peso: `<button class="btn btn--ghost">Não comi</button>` (form `status=skipped`) e `<summary class="fora__abrir btn btn--ghost">Comi outra coisa</summary>`; dentro do `<details class="fora">`, o campo com `placeholder="o que você comeu"` e o botão "Registrar" ao lado.

- [ ] **Step 1: Teste que falha**

```python
    def test_as_duas_saidas_sao_acoes_do_mesmo_tamanho(self):
        """Decisão do dono, 24/09/2026: eram um link de 15px de texto e um
        campo disfarçado de link. São as duas saídas honestas de quem não comeu
        o que estava no plano, e agora parecem o que são — secundárias, mas
        tocáveis."""
        rodape = re.search(r'<div class="meal__secundarias">.*?</div>\s*</details>', self.html, re.S).group(0)
        self.assertIn("Não comi", rodape)
        self.assertIn("Comi outra coisa", rodape)
        self.assertNotIn("Pulei", self.html)
        pulei = re.search(r'<button[^>]*value="skipped"[^>]*>', rodape).group(0)
        self.assertIn("btn--ghost", pulei)
        self.assertNotIn("btn-link", pulei)
        abrir = re.search(r'<summary class="([^"]+)"[^>]*>\s*Comi outra coisa', rodape).group(1)
        self.assertIn("btn--ghost", abrir)

    def test_comi_outra_coisa_abre_um_campo_de_verdade(self):
        rodape = ...  # o mesmo recorte
        self.assertIn('placeholder="o que você comeu"', rodape)
        self.assertIn('list="alimentos-do-catalogo"', self.html)
        self.assertIn(">Registrar<", rodape)
        # Fechado por padrão, e sem JS obrigatório.
        self.assertIn('<details class="fora"', rodape)
        self.assertNotIn('<details class="fora" open', rodape)
```

- [ ] **Step 2: Vermelho.** **Step 3: Template** — o bloco vira:

```
              <div class="meal__secundarias">
                <form method="post" action="{% url 'plans:mark_meal' slot.pk %}"
                      data-celebra="slot-{{ slot.pk }}" class="meal__pulei">
                  {% csrf_token %}
                  <button type="submit" name="status" value="skipped"
                          class="btn btn--ghost btn--block">
                    Não comi
                  </button>
                </form>

                <details class="fora" id="refeicao-{{ slot.pk }}">
                  <summary class="fora__abrir btn btn--ghost btn--block">Comi outra coisa</summary>
                  … (o formulário como está hoje, com o placeholder novo
                     "o que você comeu" e o `<label>` mantendo o rótulo
                     "O que você comeu?" para leitor de tela) …
                </details>
              </div>
```
O comentário acima do bloco é reescrito: as duas são secundárias pelo PESO (contorno, não preenchido), não pelo tamanho.

- [ ] **Step 4: CSS** — `.meal__secundarias` vira uma grade de duas colunas iguais que empilha no estreito, e a regra que fazia o `.fora__abrir` virar texto sai:

```css
.meal__secundarias {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--espaco-3);
  margin-top: var(--espaco-4);
  padding-top: var(--espaco-3);
  border-top: 1px solid var(--fio);
}
@media (max-width: 24rem) { .meal__secundarias { grid-template-columns: minmax(0, 1fr); } }
.meal__secundarias .fora { grid-column: auto; margin-top: 0; background: none; }
.meal__secundarias .fora[open] { background: var(--surface-2); grid-column: 1 / -1; }
```
(as regras de texto sublinhado do `.fora__abrir` dentro de `.meal__secundarias` saem; o `.fora__abrir` volta a ser o botão que `.btn--ghost` desenha — confira no navegador que `min-height` continua ≥ 2,75rem.)

- [ ] **Step 5:** verde em `plans.test_opcoes_tocaveis plans.test_card_de_refeicao config.tests.TouchTargetTests config.test_design_system push.test_toque_offline_na_tela`. Sabotagem: devolva `btn-link` ao "Não comi" → vermelho.

- [ ] **Step 6: Commit** — `"Não comi e Comi outra coisa viram duas ações do mesmo tamanho"`

---

### Task 6: Doutrina, CHANGELOG e a medida depois

**Files:** `CLAUDE.md`, `CHANGELOG.md`, `achados/missao-alimentacao-20260924.md`

- [ ] **Step 1: CLAUDE.md** — na seção da Alimentação, o bloco novo com DATA e MOTIVO, substituindo três frases que ficaram velhas (a de 20/09 sobre "só a da vez nasce aberta", e as de 23/09 sobre o verde da sugestão e o rótulo "Comi esta"). Diga o que vale hoje: nada nasce aberto; a da vez é MARCADA; os dois CTAs pesam igual e se chamam "Registrar"; a sugestão é chip; as duas saídas são `btn--ghost` de 44 px; o cartão AGORA é da Hoje.
- [ ] **Step 2: CHANGELOG.md** — uma linha no dia 24/09 com as cinco mudanças.
- [ ] **Step 3: QA no navegador** (agent-browser, 390 e 1280, claro e escuro, servidores congelados em 09:00/14:00/20:00): nenhuma refeição aberta, a da vez marcada, os dois CTAs iguais, "Comi outra coisa" abrindo e registrando, "Não comi" registrando, altura antes/depois.
- [ ] **Step 4: Relatório** em `achados/missao-alimentacao-20260924.md`.
- [ ] **Step 5: Commit** — `"Doutrina da Alimentação: a tela sugere, não impõe"`
