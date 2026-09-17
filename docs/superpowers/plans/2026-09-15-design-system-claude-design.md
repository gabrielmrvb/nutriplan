# Design system pelo Claude Design — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task, sob o protocolo `nutriplan-missao`. Steps use checkbox (`- [ ]`) syntax for tracking. `static/css/app.css`, `config/tests.py` e `scripts/exportar_telas.py` são SERIALIZADOS — nunca dois subagentes ao mesmo tempo neles.

**Goal:** Dar forma visual à direção "Mesa & Ferro" no claude.ai/design a partir do código e das telas reais, e trazer de volta ao repositório só três coisas — valores de token no `:root`, referências em `docs/`, e uma vitrine interna sobre as parciais reais — com a onda 3 do plano mestre passando a ter alvo medido.

**Architecture:** Django 5.2 servido por templates, um `static/css/app.css` sem build; tokens no `:root` (Mesa) com o bloco Ferro definido UMA vez como `--ferro-*` e ligado por DOIS gatilhos (`@media (prefers-color-scheme: dark)` e `body.modo-foco`); QA por `scripts/qa/nav.py` (CDP num Chrome headless) porque o binário do `agent-browser` está bloqueado pelo Controle de Aplicativo do Windows desde 14/09; a semente e o export do Claude Design vivem em `artifacts/` (fora do git); a vitrine é uma view do app `gestao`, protegida por `PainelDeGestaoMixin`.

**Tech Stack:** Python 3.12, Django 5.2.17, PostgreSQL portátil (`pg_ctl start` antes de tudo), Chrome 153 em `~/.agent-browser/browsers/`, `websocket-client` no `.venv` (dependência de QA), claude.ai/design (conta do dono).

**Spec:** [`docs/superpowers/specs/2026-09-15-design-system-claude-design-design.md`](../specs/2026-09-15-design-system-claude-design-design.md) — o plano argumenta a partir dela; quem executa lê as duas.

## Global Constraints

- **Sem framework de CSS; um `static/css/app.css`; tokens no `:root`; catracas de valor cru só descem** (`config/test_design_system.py`: `TETO_FONT_SIZE_CRU = 119`, `TETO_ESPACO_CRU = 244` — o valor novo é ≤ o atual).
- **`:has()` proibido**; toda classe de estado é escrita pelo servidor. **Barra de QUATRO itens**; "Hoje" não é pilar; Perfil em Áreas — a navegação NÃO muda por este plano.
- **Movimento tem UMA linguagem** (`--mov-*`, `config/test_movimento.py` com teto ZERO de duração escrita à mão): nenhuma tarefa deste plano escreve `transition`/`animation` com número.
- **Alvo de toque 44×44; texto ≥ 11 px; número é `tabular-nums` e vírgula decimal.**
- **Nada do export vira código por cópia**: token entra no `:root` porque a direção C já o nomeia; HTML do Claude Design vai para `docs/` ou `artifacts/`, nunca para `templates/`.
- **`CLAUDE.md` não é tocado por prompt**: a seção "Design: o que já existe" é editada à mão na Task 15, com números medidos.
- **A spec de tokens é `docs/briefs/design/direcao-c-mesa-e-ferro.md` §2**; onde o Claude Design divergir, a spec ganha e a diferença vai para `proposto-nao-adotado.md`.
- **Nenhum `style=` estático em template** (`test_nenhum_template_do_app_carrega_estilo_estatico`); nenhum `<div role="dialog">`; comentário `{# #}` não atravessa linha; botão com só ícone leva classe ou medida (`config/test_a1_icone_de_botao.py`).
- **Teste ancora em classe ou texto visível, nunca em `data-*`** (o seletor do JS e o marcador do HTML são a mesma string).
- **Commits em português, uma frase que diz o que mudou e por quê**; nunca `--no-verify`; o `pre-commit` roda 18 testes de trava e o `pre-push` roda a suíte.
- Fora deste plano, de propósito: pasta `design-system/`, rota pública `/design-system`, `SKILL.md`, plugin `frontend-design`, aplicar `modo-foco` a `/treino/agora/` (é onda 4), fonte própria (T3.2, condicionada a medir).

---

## Mapa de arquivos

| arquivo | responsabilidade | tarefa |
|---|---|---|
| `scripts/exportar_telas.py` (modify) | as seis telas da spec, tela anônima, URL calculada | 1 |
| `config/test_exportar_telas.py` (create) | mecânica do exportador: anônimo, `url_fn`, lista | 1 |
| `scripts/qa/nav.py` (modify) | comando `tema claro\|escuro` (emulação de `prefers-color-scheme`) | 2 |
| `scripts/qa/sessao.py` (create) | imprime um `sessionid` de QA para o `nav.py cookie` | 2 |
| `config/test_nav_py.py` (create) | o comando `tema` existe na doc e no despacho | 2 |
| `docs/briefs/design/DESIGN.md` (create) | a Mesa & Ferro como contrato de tokens para o Claude Design | 3 |
| `config/test_design_md.py` (create) | todo token da direção C §2 está no `DESIGN.md` | 3 |
| `scripts/montar_semente.py` (create) | monta `artifacts/claude-design/seed/` | 4 |
| `config/test_montar_semente.py` (create) | a montagem em pasta temporária | 4 |
| `artifacts/claude-design/seed/**` (fora do git) | o pacote | 4, 5 |
| `docs/briefs/2026-09-15-chatgpt-claude-design/roteiro-claude-design.md` (create) | os nove passos do dono + seis prompts de mockup | 6 |
| `scripts/inventariar_export.py` (create) + `config/test_inventariar_export.py` (create) | inventário classificado do export | 8 |
| `config/tests.py` (modify: `_tokens`, `ContrastTests`, `DesignSystemTests`) + `config/test_tema_claro.py` (modify) + `config/test_ferro.py` (create) | leitor de token resolve `var()`; Ferro em um bloco e dois gatilhos; PWA acompanha o CSS | 9 |
| `static/css/app.css` §1 (modify) + `config/settings.py` (modify) | paleta Mesa/Ferro, renomeações, `--ferro-*`, `body.modo-foco` | 10 |
| `scripts/tokens_do_export.py` (create) + `docs/briefs/2026-09-15-chatgpt-claude-design/proposto-nao-adotado.md` (create) | comparação token a token com o export | 11 |
| `docs/briefs/design/referencias/claude-design/*.png` (create) + `docs/briefs/README.md` (modify) | os seis mockups a 390 px | 12 |
| `gestao/views.py`, `gestao/urls.py`, `gestao/forms_vitrine.py` (create), `gestao/test_vitrine.py` (create) | rota, permissão, formulário da vitrine | 13 |
| `templates/gestao/vitrine.html` (create) | toda parcial real em todos os estados, `?regime=ferro` | 14 |
| `CLAUDE.md`, `docs/sistema-visual.md`, `docs/superpowers/plans/2026-09-14-plano-mestre.md` (modify) | fechamento com números | 15 |

---

### Task 1: Exportador — as seis telas da spec

**Files:**
- Modify: `scripts/exportar_telas.py` (`TELAS` e o laço de `exportar()`)
- Test: `config/test_exportar_telas.py`

**Interfaces:**
- Produces: `TELAS` (lista de dicts com `nome`, `rotulo` e `url` OU `url_fn`, opcional `anonimo`, opcional `abrir_details`); `ficha_de_hoje(usuario) -> str | None`; `resposta_da_tela(tela, usuario) -> (resposta, url_final)`. A Task 4 lê os HTMLs em `.ui_snapshots/html/1*-*.html`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# config/test_exportar_telas.py
"""O exportador de telas serve à semente do Claude Design (spec de 15/09/2026).

Três mecânicas novas, e cada uma tem um motivo: a ENTRADA só existe para
quem não está logado (logado, `/conta/entrar/` redireciona para a Home — e a
semente ficaria sem a tela de entrada); a FICHA tem id na URL, que depende
da pessoa; e as seis telas da spec precisam estar na lista, com os nomes
que `scripts/montar_semente.py` procura.
"""
import importlib

from django.test import TestCase

from plans.tests import create_complete_user


def _modulo():
    # O módulo chama `django.setup()` no import; dentro da suíte isso é
    # inofensivo, e importar tarde evita custo em quem não roda este arquivo.
    return importlib.import_module("scripts.exportar_telas")


class ExportadorDeTelasTests(TestCase):
    SEIS = ("10-hoje", "11-treino-painel", "12-treino-ficha",
            "13-treino-execucao", "14-progresso", "15-entrada")

    def test_as_seis_telas_da_spec_estao_na_lista(self):
        nomes = [t["nome"] for t in _modulo().TELAS]
        for nome in self.SEIS:
            with self.subTest(nome=nome):
                self.assertIn(nome, nomes)

    def test_a_entrada_e_pedida_sem_sessao(self):
        """Logado, `/conta/entrar/` redireciona; a tela anônima não pode."""
        modulo = _modulo()
        usuario = create_complete_user("exporta@exemplo.com")
        entrada = next(t for t in modulo.TELAS if t["nome"] == "15-entrada")
        resposta, url_final = modulo.resposta_da_tela(entrada, usuario)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("/conta/entrar/", url_final)
        self.assertIn("Bom te ver de volta", resposta.content.decode())

    def test_uma_tela_logada_entra_com_a_pessoa(self):
        modulo = _modulo()
        usuario = create_complete_user("logada@exemplo.com")
        hoje = next(t for t in modulo.TELAS if t["nome"] == "10-hoje")
        resposta, url_final = modulo.resposta_da_tela(hoje, usuario)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("/conta/entrar/", url_final)

    def test_a_ficha_de_hoje_devolve_none_sem_plano_de_treino(self):
        """Sem sessão não há id; a tela é pulada com aviso, não estoura."""
        modulo = _modulo()
        usuario = create_complete_user("semficha@exemplo.com")
        self.assertIsNone(modulo.ficha_de_hoje(usuario))
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test config.test_exportar_telas -v 2`
Expected: FAIL — `AttributeError: module has no attribute 'resposta_da_tela'` (e `10-hoje` ausente).

- [ ] **Step 3: Implementar**

Em `scripts/exportar_telas.py`, logo depois de `EMAIL_DEMO`, acrescentar:

```python
from django.urls import reverse  # noqa: E402


def ficha_de_hoje(usuario):
    """URL da ficha da sessão de hoje — ou da primeira do plano ativo.

    A ficha tem id na URL e o id é da pessoa; `estado_do_treino` já sabe
    qual sessão é a de hoje. Sem plano de treino não há ficha, e a resposta
    é `None`: o exportador pula a tela com aviso em vez de inventar um id.
    """
    from workouts.services import estado_do_treino

    sessao = estado_do_treino(usuario).sessao
    if sessao is None:
        plano = usuario.training_plans.filter(is_active=True).first()
        sessao = plano.sessions.order_by("weekday", "id").first() if plano else None
    if sessao is None:
        return None
    return reverse("workouts:ficha", args=[sessao.id])
```

Acrescentar ao fim de `TELAS` (antes do `]`):

```python
    # As seis telas da spec de 15/09/2026 (design system pelo Claude Design):
    # é o que vai para `artifacts/claude-design/seed/telas/`. A ENTRADA é
    # anônima porque logado ela redireciona para a Home; a FICHA calcula o
    # id pela pessoa.
    {"nome": "10-hoje", "url": "/", "rotulo": "Hoje"},
    {"nome": "11-treino-painel", "url": "/treino/", "rotulo": "Treino · painel da semana"},
    {"nome": "12-treino-ficha", "url_fn": ficha_de_hoje, "rotulo": "Treino · ficha de hoje"},
    {"nome": "13-treino-execucao", "url": "/treino/agora/", "rotulo": "Treino · execução"},
    {"nome": "14-progresso", "url": "/historico/", "rotulo": "Progresso"},
    {"nome": "15-entrada", "url": "/conta/entrar/", "rotulo": "Entrada", "anonimo": True},
```

Substituir, em `exportar()`, o começo do laço (`for tela in TELAS:` até `destino_final = ...`) por uma chamada, e definir a função acima de `exportar()`:

```python
def resposta_da_tela(tela, usuario):
    """GET da tela como a semente precisa dela: logada, ou anônima se pedido.

    Devolve (resposta, url_final). `url_fn` recebe a pessoa e pode devolver
    `None` — aí a resposta é `None` e quem chama pula a tela.
    """
    url = tela["url_fn"](usuario) if "url_fn" in tela else tela["url"]
    if url is None:
        return None, None
    cliente = Client()
    if not tela.get("anonimo"):
        # `force_login` entra sem senha: este script não precisa saber a
        # senha de ninguém, e nada é gravado no banco.
        cliente.force_login(usuario)
    resposta = cliente.get(url, follow=True)
    url_final = resposta.redirect_chain[-1][0] if resposta.redirect_chain else url
    return resposta, url_final
```

e no laço:

```python
    for tela in TELAS:
        resposta, destino_final = resposta_da_tela(tela, usuario)
        if resposta is None:
            resultados.append((tela["nome"], "PULADA (sem URL para esta pessoa)", "", 0))
            continue
        if resposta.status_code != 200:
            resultados.append((tela["nome"], "ERRO {}".format(resposta.status_code), destino_final, 0))
            continue
```

(o `cliente = Client()` / `cliente.force_login(usuario)` que ficava antes do laço sai — cada tela abre o seu). No rodapé, a linha que compara `destino` com a URL da lista precisa tolerar `url_fn`: trocar `next((t["url"] for t in TELAS ...` por `next((t.get("url", "") for t in TELAS ...`.

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `.venv/Scripts/python.exe manage.py test config.test_exportar_telas -v 2`
Expected: 4 testes OK.

- [ ] **Step 5: Rodar o exportador de verdade (banco de pé, seeds feitos)**

Run: `.venv/Scripts/python.exe scripts/exportar_telas.py`
Expected: as seis linhas `1x-…` com `ok` e tamanho em KB (a `12-treino-ficha` pode sair `PULADA` se o demo não tiver plano de treino — nesse caso rode `manage.py seed_demo` e repita). Conferir que `.ui_snapshots/html/15-entrada.html` contém "Bom te ver de volta" e não "Sua sessão venceu".

- [ ] **Step 6: Commit**

```bash
git add scripts/exportar_telas.py config/test_exportar_telas.py
git commit -m "Exportador de telas: as seis telas da semente do Claude Design, com entrada anônima e ficha por pessoa"
```

---

### Task 2: `nav.py tema` e a sessão de QA

**Files:**
- Modify: `scripts/qa/nav.py` (docstring, classe `Sessao`, `main()`)
- Create: `scripts/qa/sessao.py`
- Test: `config/test_nav_py.py`

**Interfaces:**
- Produces: `nav.py <sessao> tema claro|escuro` (emula `prefers-color-scheme`); `sessao.py <email>` imprime um `sessionid` válido para `nav.py <sessao> cookie sessionid <valor>`.

- [ ] **Step 1: Teste que falha**

```python
# config/test_nav_py.py
"""`nav.py` é a régua de QA de navegador deste repositório; o comando `tema`
é o que permite capturar o tema escuro sem mexer no sistema operacional.
O teste lê a fonte porque o módulo abre um Chrome ao ser usado."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

NAV = Path(settings.BASE_DIR) / "scripts" / "qa" / "nav.py"


class ComandoTemaTests(SimpleTestCase):
    def test_o_comando_esta_documentado_e_despachado(self):
        fonte = NAV.read_text(encoding="utf-8")
        self.assertIn("nav.py <sessao> tema claro|escuro", fonte)
        self.assertIn('elif cmd == "tema": out = s.tema(args[0])', fonte)
        self.assertIn("Emulation.setEmulatedMedia", fonte)
        self.assertIn('"prefers-color-scheme"', fonte)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test config.test_nav_py -v 2`
Expected: FAIL (`tema` ausente).

- [ ] **Step 3: Implementar**

No docstring de `nav.py`, depois da linha `nav.py <sessao> offline on|off`:

```
  nav.py <sessao> tema claro|escuro         -> emula prefers-color-scheme (vale até `close`)
```

Na classe `Sessao`, depois de `viewport`:

```python
    def tema(self, qual):
        """Emula `prefers-color-scheme` sem mexer no Windows.

        É o que a T3.0 do plano mestre precisava e nunca teve: o escuro nunca
        foi capturado nesta campanha. Vale para a sessão inteira, então a
        captura clara e a escura saem do MESMO Chrome, com o mesmo perfil.
        """
        if qual not in ("claro", "escuro"):
            raise SystemExit("tema: claro|escuro")
        valor = "dark" if qual == "escuro" else "light"
        self.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": valor}])
        return {"tema": qual, "prefers-color-scheme": valor}
```

Em `main()`, depois de `elif cmd == "offline": ...`:

```python
        elif cmd == "tema": out = s.tema(args[0])
```

Criar `scripts/qa/sessao.py`:

```python
# -*- coding: utf-8 -*-
"""Imprime um `sessionid` para o `nav.py cookie` — login de QA sem senha.

    .venv/Scripts/python.exe scripts/qa/sessao.py joao@demo.local

Cria uma sessão do Django para a pessoa e escreve a chave. A sessão vale o
`SESSION_COOKIE_AGE` do settings; nada mais é gravado. Só para uso local:
o servidor de QA é o `runserver` desta máquina.
"""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model  # noqa: E402
from django.contrib.sessions.backends.db import SessionStore  # noqa: E402


def sessao_para(email):
    usuario = get_user_model().objects.get(email=email)
    sessao = SessionStore()
    sessao[SESSION_KEY] = str(usuario.pk)
    sessao[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    sessao[HASH_SESSION_KEY] = usuario.get_session_auth_hash()
    sessao.create()
    return sessao.session_key


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(sessao_para(sys.argv[1]))
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `.venv/Scripts/python.exe manage.py test config.test_nav_py -v 2`
Expected: OK.

- [ ] **Step 5: Prova manual do tema (servidor de pé em 8000)**

```bash
.venv/Scripts/python.exe scripts/qa/nav.py semente viewport 390 844
.venv/Scripts/python.exe scripts/qa/nav.py semente cookie sessionid "$(.venv/Scripts/python.exe scripts/qa/sessao.py joao@demo.local)"
.venv/Scripts/python.exe scripts/qa/nav.py semente open http://127.0.0.1:8000/
.venv/Scripts/python.exe scripts/qa/nav.py semente tema escuro
.venv/Scripts/python.exe scripts/qa/nav.py semente eval "getComputedStyle(document.body).backgroundColor"
```
Expected: a última linha devolve o `--bg` do escuro (`rgb(7, 12, 11)` antes da Task 10). Com `tema claro`, `rgb(244, 246, 245)`.

- [ ] **Step 6: Commit**

```bash
git add scripts/qa/nav.py scripts/qa/sessao.py config/test_nav_py.py
git commit -m "QA de navegador: tema claro/escuro emulado e sessão de QA sem senha"
```

---

### Task 3: `DESIGN.md` — a Mesa & Ferro como contrato para o Claude Design

**Files:**
- Create: `docs/briefs/design/DESIGN.md`
- Test: `config/test_design_md.py`

**Interfaces:**
- Produces: o arquivo que a Task 4 copia para `seed/DESIGN.md`. Fonte: `docs/briefs/design/direcao-c-mesa-e-ferro.md` §2 (tokens) e `static/css/app.css` §1 (escalas que já existem).

- [ ] **Step 1: Teste que falha**

```python
# config/test_design_md.py
"""O DESIGN.md é derivado da direção C; se um token entrar na direção e não
no contrato, o Claude Design desenha sem ele — e inventa."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

DESIGN_DIR = Path(settings.BASE_DIR) / "docs" / "briefs" / "design"


class DesignMdTests(SimpleTestCase):
    def test_todo_token_da_direcao_c_esta_no_contrato(self):
        direcao = (DESIGN_DIR / "direcao-c-mesa-e-ferro.md").read_text(encoding="utf-8")
        contrato = (DESIGN_DIR / "DESIGN.md").read_text(encoding="utf-8")
        tabela = direcao.split("## 2. Cor", 1)[1].split("**A regra de três.**", 1)[0]
        tokens = re.findall(r"^\| `(--[\w-]+)` \|", tabela, re.M)
        self.assertGreaterEqual(len(tokens), 20, "a tabela da direção C não foi lida")
        faltando = [t for t in tokens if f"`{t}`" not in contrato]
        self.assertEqual(faltando, [], f"tokens da direção C fora do DESIGN.md: {faltando}")

    def test_o_contrato_diz_o_que_nunca_muda_e_o_que_o_app_nao_faz(self):
        contrato = (DESIGN_DIR / "DESIGN.md").read_text(encoding="utf-8")
        for secao in ("## O que NUNCA muda entre Mesa e Ferro", "## O que este app não faz", "## Componentes que já existem"):
            self.assertIn(secao, contrato)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test config.test_design_md -v 2`
Expected: FAIL — `FileNotFoundError` para `DESIGN.md`.

- [ ] **Step 3: Escrever o contrato**

`docs/briefs/design/DESIGN.md`, com este conteúdo (os valores vêm da direção C §2; onde o plano mestre corrigiu um valor com medição, vale o corrigido — `--text-mute` de Ferro é `#96a29c`):

````markdown
# NutriPlan — DESIGN.md (contrato visual para o Claude Design)

Este arquivo é a fonte da verdade dos tokens e das regras. O que está aqui
não é sugestão: é decisão tomada e medida (contrastes recalculados por
teste em `config/tests.py`). Se algo faltar, pergunte; não invente.

## Identidade

- **O que é:** PWA mobile-first, em português do Brasil, de alimentação,
  treino, corrida, hidratação e progresso — cinco pilares no mesmo nível.
  "Hoje" é o orquestrador do dia, não um pilar; Perfil é utilitário.
- **Navegação:** barra inferior de QUATRO itens (Alimentação · Treino ·
  Progresso · Áreas) — medida a 320 px; cinco não cabem. Um mapa de áreas
  na barra de cima lista os cinco pilares. **A navegação não muda.**
- **Tom:** direto, adulto, sem promessa. Número grande é o protagonista da
  tela (calorias, série, litros, peso). Nada de texto motivacional genérico.
- **Marca:** verde-floresta + branco + verde-folha, cores próprias que NÃO
  mudam com o tema (é a `icon-192.png` em `marca/`).

## Princípio: um material, dois regimes de luz

A comida acontece numa MESA — luz de cozinha, linho, branco. O treino
acontece no FERRO — luz baixa de academia, grafite, número grande. O que faz
os dois serem um app só é que TUDO fora da luz é idêntico. O regime é uma
classe escrita pelo servidor no `<body>` (`modo-foco`): a execução do treino
e a corrida em andamento nascem em Ferro; todo o resto é Mesa. O tema escuro
por preferência do sistema É o mesmo bloco de valores do Ferro.

## O que NUNCA muda entre Mesa e Ferro

Família tipográfica e eixo óptico; a escala de texto; os raios; a grade de
4 px; o sprite de ícones; o anel de progresso; a receita do botão; alvo de
toque; espaçamento entre cartões. **Só muda cor e densidade.** Nenhum
componente pode ter raio, tamanho de texto ou ícone diferente entre os
regimes.

## Tokens de cor (Mesa = padrão; Ferro = `body.modo-foco` e tema escuro)

| token | Mesa | Ferro | papel |
|---|---|---|---|
| `--bg` | `#f5f3ee` (linho) | `#0e1412` | chão |
| `--surface` | `#ffffff` | `#161d1a` | prato / cartão |
| `--surface-2` | `#efece4` | `#1d2622` | agrupamento dentro do cartão, trilho do anel |
| `--surface-3` | `#ebe8de` | `#26312b` | célula vazia de gráfico, silhueta de vazio |
| `--surface-focus` | `#e3f1e8` | `#123024` | UMA por tela: a próxima refeição, a série da vez |
| `--text` | `#141f1a` | `#f4f7f5` | texto |
| `--text-dim` | `#485550` | `#b6c1bb` | texto de apoio |
| `--text-mute` | `#55625c` | `#96a29c` | rótulo, legenda (≥ 4,5:1 no pior fundo) |
| `--brand` | `#0c6b40` | `#22c98a` | AGIR: CTA, link, aba ativa, foco |
| `--brand-strong` | `#08512f` | `#4ddb9f` | só `:active`/hover |
| `--brand-soft` | `#dff0e6` | `#0f2a20` | botão tonal, chip |
| `--folha` | `#3f9718` | `#6fcf4a` | FEITO (série registrada, arco do anel) + pilar Treino |
| `--agua` | `#1e6e96` | `#5fbdf0` | pilar Hidratação |
| `--agua-texto` | `#175877` | `#5fbdf0` | água como texto pequeno |
| `--brasa` | `#a63f18` | `#ff9a7a` | pilar Corrida |
| `--terra` | `#8a5109` | `#f2b04e` | pilar Progresso/peso |
| `--chama` | `#c8620a` | `#ffa53a` | ofensiva, só objeto gráfico |
| `--carb` | `#ad6d16` | `#e6b35d` | macro carboidrato |
| `--fat` | `#5568a6` | `#93a8de` | macro gordura |
| `--danger` | `#b3261e` | `#ff8a80` | erro, ação destrutiva |
| `--fio` | `rgba(20,31,26,.10)` | `rgba(255,255,255,.08)` | hairline de separação |
| `--fio-forte` | `rgba(20,31,26,.22)` | `rgba(255,255,255,.16)` | borda de campo |
| `--on-brand` | `#ffffff` | `#04140e` | texto sobre `--brand` |
| `--dia-a` … `--dia-e` | verde, azul, âmbar, violeta, coral | idem, claros | cor de sessão no painel de treino |

**A regra de três:** cor de pilar aparece em pelo menos TRÊS lugares da área
(fio do prato, arco/coluna do gráfico, ponto do ícone) e em NENHUM botão.
Foco é `--brand` em todo controle. Nenhum gradiente com o violeta.

## Tipografia

- Hoje: `system-ui` (Segoe/SF/Roboto). Uma fonte própria (DM Sans Variable)
  está CONDICIONADA a medição de tamanho e será decidida no repositório —
  **não escolha fonte.**
- Quatro pesos apenas: 400 (corpo), 500 (rótulo), 600 (título), 700 (número).
- Escala (rem): xs .7 (11,2 px, o piso) · sm .8 · md .9 · base 1 · lg 1.15 ·
  xl 1.4 · 2xl 1.75 · 3xl 2.15 · display 3.1. Texto de interface nunca
  abaixo de 11 px. Número é `font-variant-numeric: tabular-nums` e usa
  vírgula decimal ("62,50").

## Espaço, raio, sombra, camadas, movimento

- Grade de 4 px; espaçamentos `--espaco-1…8` (4 … 32 px).
- Raios: `--radius-xl` 28 · `--radius-lg` 22 · `--radius` 18 · `--radius-sm` 14 · `--pill` 999.
- Sombras: `--shadow-rest` e `--shadow-lift` (uma de repouso, uma de
  elevação); `--edge` é o fio interno de luz. Nada além disso.
- Camadas (z-index), de baixo para cima: conteúdo → barra de cima →
  flutuante → navegação → aviso → bloqueio. Nada cobre a barra de baixo.
- Movimento: toque .1 s, estado .18 s, expansão .25 s, tela .2 s, modal
  .28 s, sucesso .5 s; passo 6 px; `prefers-reduced-motion` desliga tudo.
  Movimento confirma ação; não decora.

## Regras de interface

- Alvo de toque **44 × 44 px** (altura E largura). Texto ≥ 11 px.
- Nada rola na horizontal; todo contêiner de texto tem `min-width: 0`.
- Uma superfície de foco por tela. Um botão primário por tela.
- Estado vazio é convite (o que fazer a seguir), não constatação.
- Ações destrutivas ("zerar", "excluir conta") são secundárias, separadas e
  pedem confirmação.

## Componentes que já existem (não recriar; refinar)

`card` (com `card__head`, `card--conta`, `card--metas`, `card--prosa`) ·
`btn` (`--primary`, `--ghost`, `--quiet`, `--perigo`, `--sm`, `--block`; uma
escala de toque, `.96`) · `chip` / `chip-row` · `pill` (`--brand`, `--mute`,
`--warm`) · `tile` / `tiles` (número grande + rótulo + meta) · `data-list`
(`dt`/`dd`) · `empty-state` · `hint` · `field` (rótulo, ajuda, erro; rádios e
caixas viram cartões) · `choice_cards` (rádio como cartão com ícone) ·
`marca` e `marca_de_entrada` · `_conquista` (aviso ancorado embaixo, não
modal) · anel de progresso (calorias, água, treino) · `tabbar` (quatro itens)
· `app-bar` com mapa de áreas (`<details>`).

## O que este app não faz

Gradiente roxo; vidro (`backdrop-filter`) além dos quatro cartões do topo;
ícone-emoji na interface; Material Symbols; `:has()`; animação decorativa;
cinco abas; tela de login com só logo, campos e botão; "painel
administrativo" de números iguais ao texto.
````

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `.venv/Scripts/python.exe manage.py test config.test_design_md -v 2`
Expected: OK (se falhar por um token da tabela da direção C que não está aqui — `--surface-focus`, `--dia-*` etc. —, acrescente a linha; a tabela da direção é a lista).

- [ ] **Step 5: Commit**

```bash
git add docs/briefs/design/DESIGN.md config/test_design_md.py
git commit -m "DESIGN.md: a Mesa & Ferro como contrato de tokens e regras para o Claude Design"
```

---

### Task 4: `montar_semente.py` — o pacote em `artifacts/claude-design/seed/`

**Files:**
- Create: `scripts/montar_semente.py`
- Test: `config/test_montar_semente.py`
- Produz (fora do git): `artifacts/claude-design/seed/{DESIGN.md,nota.txt,codigo/,telas/,marca/,capturas/}`

**Interfaces:**
- Consumes: `.ui_snapshots/html/1*-*.html` (Task 1), `docs/briefs/design/DESIGN.md` (Task 3).
- Produces: `montar(raiz: Path, destino: Path) -> dict[str, int]` (contagem por pasta); `NOTA` (str).

- [ ] **Step 1: Teste que falha**

```python
# config/test_montar_semente.py
"""A semente do Claude Design é montada por script para ser reproduzível —
o roteiro do dono aponta para pastas com nomes fixos."""
import importlib
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MontarSementeTests(SimpleTestCase):
    def test_monta_as_seis_pastas_e_a_nota(self):
        modulo = importlib.import_module("scripts.montar_semente")
        raiz = Path(settings.BASE_DIR)
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "seed"
            contagem = modulo.montar(raiz, destino, telas=[])
            for pasta in ("codigo", "telas", "marca", "capturas"):
                self.assertTrue((destino / pasta).is_dir(), pasta)
            self.assertTrue((destino / "DESIGN.md").is_file())
            self.assertEqual((destino / "nota.txt").read_text(encoding="utf-8"), modulo.NOTA)
            self.assertTrue((destino / "codigo" / "app.css").is_file())
            self.assertTrue((destino / "codigo" / "base.html").is_file())
            self.assertTrue((destino / "codigo" / "partials" / "field.html").is_file())
            self.assertTrue((destino / "marca" / "icon-192.png").is_file())
            self.assertTrue((destino / "marca" / "icones.svg").is_file())
            self.assertGreaterEqual(contagem["codigo"], 10)

    def test_o_sprite_vira_svg_puro(self):
        modulo = importlib.import_module("scripts.montar_semente")
        svg = modulo.sprite_como_svg(Path(settings.BASE_DIR))
        self.assertTrue(svg.lstrip().startswith("<svg"))
        self.assertNotIn("{%", svg)
        self.assertIn("<symbol", svg)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test config.test_montar_semente -v 2`
Expected: FAIL — `ModuleNotFoundError: scripts.montar_semente`.

- [ ] **Step 3: Implementar**

```python
# scripts/montar_semente.py
# -*- coding: utf-8 -*-
"""Monta a semente do Claude Design em `artifacts/claude-design/seed/`.

    .venv/Scripts/python.exe scripts/exportar_telas.py      # antes: as telas
    .venv/Scripts/python.exe scripts/montar_semente.py

O que entra, e por quê (spec de 15/09/2026, §4):
  DESIGN.md   o contrato de tokens e regras (docs/briefs/design/DESIGN.md)
  codigo/     app.css, base.html, partials/ — o Claude Design parte da
              linguagem que já existe em vez de inventar
  telas/      os seis HTMLs autocontidos do exportador
  marca/      icon-192.png (a marca) e icones.svg (o sprite, sem Django)
  capturas/   vazia aqui; a Task 5 enche com nav.py (6 telas × 2 temas)
  nota.txt    a frase para "Any other notes?"
"""
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "artifacts" / "claude-design" / "seed"
TELAS = ("10-hoje", "11-treino-painel", "12-treino-ficha", "13-treino-execucao", "14-progresso", "15-entrada")

NOTA = (
    "PWA mobile-first de alimentação, treino, corrida, hidratação e progresso, "
    "em português do Brasil. Um material, dois regimes de luz: Mesa (clara, "
    "alimentação e o app em geral) e Ferro (escura, execução do treino e tema "
    "escuro). Tokens, regras e componentes estão no DESIGN.md — não inventar "
    "cor, raio nem tipografia fora dele; o que faltar, perguntar.\n"
)


def sprite_como_svg(raiz):
    """O sprite mora num template Django; o Claude Design lê SVG puro."""
    texto = (raiz / "templates" / "partials" / "icones.html").read_text(encoding="utf-8")
    texto = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", texto, flags=re.S)
    texto = re.sub(r"{%.*?%}|{{.*?}}", "", texto, flags=re.S)
    inicio = texto.find("<svg")
    fim = texto.rfind("</svg>") + len("</svg>")
    if inicio < 0 or fim < len("</svg>"):
        raise SystemExit("icones.html não tem um <svg>…</svg> reconhecível")
    return texto[inicio:fim].strip() + "\n"


def montar(raiz, destino, telas=TELAS):
    if destino.exists():
        shutil.rmtree(destino)
    for pasta in ("codigo", "telas", "marca", "capturas"):
        (destino / pasta).mkdir(parents=True)
    contagem = {"codigo": 0, "telas": 0, "marca": 0}

    shutil.copy(raiz / "docs" / "briefs" / "design" / "DESIGN.md", destino / "DESIGN.md")
    (destino / "nota.txt").write_text(NOTA, encoding="utf-8")

    shutil.copy(raiz / "static" / "css" / "app.css", destino / "codigo" / "app.css")
    shutil.copy(raiz / "templates" / "base.html", destino / "codigo" / "base.html")
    contagem["codigo"] += 2
    (destino / "codigo" / "partials").mkdir()
    for parcial in sorted((raiz / "templates" / "partials").glob("*.html")):
        shutil.copy(parcial, destino / "codigo" / "partials" / parcial.name)
        contagem["codigo"] += 1

    shutil.copy(raiz / "static" / "icons" / "icon-192.png", destino / "marca" / "icon-192.png")
    (destino / "marca" / "icones.svg").write_text(sprite_como_svg(raiz), encoding="utf-8")
    contagem["marca"] = 2

    for nome in telas:
        origem = raiz / ".ui_snapshots" / "html" / (nome + ".html")
        if origem.is_file():
            shutil.copy(origem, destino / "telas" / origem.name)
            contagem["telas"] += 1
        else:
            print("  aviso: tela ausente, rode scripts/exportar_telas.py antes:", origem.name)
    return contagem


if __name__ == "__main__":
    contagem = montar(RAIZ, DESTINO)
    print("Semente em", DESTINO)
    for pasta, n in contagem.items():
        print("  {:<8} {} arquivo(s)".format(pasta, n))
    if contagem["telas"] < len(TELAS):
        sys.exit("faltam telas em telas/ — exporte primeiro")
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `.venv/Scripts/python.exe manage.py test config.test_montar_semente -v 2`
Expected: OK.

- [ ] **Step 5: Montar de verdade**

Run: `.venv/Scripts/python.exe scripts/montar_semente.py`
Expected: `telas 6 arquivo(s)`, `codigo ≥ 10`, `marca 2`. Abrir `artifacts/claude-design/seed/marca/icones.svg` no navegador e ver os 14 símbolos (é SVG puro; `<symbol>` não desenha sozinho — conferir pelo `grep -c "<symbol"` = 14).

- [ ] **Step 6: Commit (só o script e o teste; `artifacts/` fica fora)**

```bash
git add scripts/montar_semente.py config/test_montar_semente.py
git commit -m "Semente do Claude Design montada por script: contrato, código, telas, marca e nota"
```

---

### Task 5: Capturas — a T3.0 do plano mestre (6 telas × 2 temas a 390 px)

**Files:**
- Produz (fora do git): `artifacts/claude-design/seed/capturas/<tela>-<tema>.png` (12) e `artifacts/claude-design/antes/<tela>-<tema>.json` (12, `medir.js`).

**Interfaces:**
- Consumes: `nav.py tema` (Task 2), `sessao.py` (Task 2), servidor em `http://127.0.0.1:8000`.
- Produces: as 12 capturas que vão no formulário do Claude Design e o "antes" de `medir.js`.

- [ ] **Step 1: Subir o servidor e restaurar a conta demo**

`pg_ctl start` se necessário; `manage.py seed_demo` se a conta demo não tiver plano de treino; servidor pelo painel do app (`launch.json` → `nutriplan`) ou `.venv/Scripts/python.exe manage.py runserver 8000` em outro terminal.

- [ ] **Step 2: Rodar o roteiro de captura**

Criar `artifacts/claude-design/capturar.sh` (fora do git) com:

```bash
#!/usr/bin/env bash
set -euo pipefail
PY=.venv/Scripts/python.exe; NAV="$PY scripts/qa/nav.py semente"; SEED=artifacts/claude-design/seed/capturas; ANTES=artifacts/claude-design/antes
mkdir -p "$SEED" "$ANTES"
FICHA=$($PY manage.py shell -c "from django.contrib.auth import get_user_model; from scripts.exportar_telas import ficha_de_hoje; print(ficha_de_hoje(get_user_model().objects.get(email='joao@demo.local')))")
$NAV viewport 390 844
$NAV cookie sessionid "$($PY scripts/qa/sessao.py joao@demo.local)"
for tema in claro escuro; do
  $NAV tema $tema
  for par in "hoje|/" "treino-painel|/treino/" "treino-ficha|$FICHA" "treino-execucao|/treino/agora/" "progresso|/historico/"; do
    nome="${par%%|*}"; url="${par#*|}"
    $NAV open "http://127.0.0.1:8000$url"
    $NAV screenshot "$SEED/$nome-$tema.png"
    $NAV eval "$(cat scripts/qa/medir.js)" > "$ANTES/$nome-$tema.json"
  done
done
# A entrada é anônima: outra sessão, sem cookie.
for tema in claro escuro; do
  $PY scripts/qa/nav.py entrada viewport 390 844
  $PY scripts/qa/nav.py entrada tema $tema
  $PY scripts/qa/nav.py entrada open http://127.0.0.1:8000/conta/entrar/
  $PY scripts/qa/nav.py entrada screenshot "$SEED/entrada-$tema.png"
done
$NAV close; $PY scripts/qa/nav.py entrada close
ls -la "$SEED"
```

Run: `bash artifacts/claude-design/capturar.sh`
Expected: 12 PNGs em `seed/capturas/`, cada um > 20 KB; 10 JSONs em `antes/`. Abrir `hoje-escuro.png` e conferir que é ESCURO de verdade (fundo grafite) — se sair claro, o `tema` não pegou: rode `tema` DEPOIS do `open` e capture de novo.

- [ ] **Step 3: Registrar o que foi medido**

Acrescentar em `artifacts/claude-design/antes/LEIA-ME.txt`: data/hora, commit (`git rev-parse --short HEAD`), conta (`joao@demo.local`), largura 390, os dois temas. Sem commit (é `artifacts/`).

---

### Task 6: O roteiro do dono no claude.ai/design

**Files:**
- Create: `docs/briefs/2026-09-15-chatgpt-claude-design/roteiro-claude-design.md`
- Modify: `docs/briefs/2026-09-15-chatgpt-claude-design/README.md` (tabela de arquivos: uma linha)

- [ ] **Step 1: Escrever o roteiro**

````markdown
# Roteiro — criar o design system do NutriPlan no claude.ai/design

Traduz o Reel "Parte 1/2" do @matheusgomes para a semente deste repositório.
O formulário pode ter mudado desde o vídeo (setembro de 2026); adapte e anote
aqui o que mudou. Tempo: ~15 min, dos quais ~5 são a geração.

A semente está em `artifacts/claude-design/seed/` (montada por
`scripts/montar_semente.py`; capturas por `artifacts/claude-design/capturar.sh`).

## Criar o sistema

1. `claude.ai/design` → modelo **Opus 5**, esforço **Extra**.
2. "+" → **Design system → Create**. Nome: **NutriPlan**.
3. *Link code from your computer* → arraste `seed/codigo/` (é a subpasta de
   frontend: `app.css`, `base.html`, `partials/`).
4. *Add fonts, logos and assets* → arraste tudo de `seed/marca/`,
   `seed/capturas/` (12 PNGs) e `seed/telas/` (6 HTMLs autocontidos).
   Se o formulário recusar HTML, deixe as telas de fora — as capturas cobrem.
5. *Any other notes?* → cole `seed/nota.txt`.
6. Continuar. Nas perguntas:
   - grafia da marca: **NutriPlan**;
   - domínio/produto: *"alimentação, treino, corrida, hidratação e
     progresso — os cinco pilares do DESIGN.md"*;
   - qualquer pergunta sobre cor, raio, fonte ou componente: *"está no
     DESIGN.md; não inventar fora dele"*;
   - o resto: **decida por mim**.
7. Revisar. O que não bater com o `DESIGN.md`, pedir em texto na lateral
   ("o fundo Mesa é `#f5f3ee`, não branco puro"; "só quatro pesos de
   fonte"). Não aceite fonte nova: a fonte é decisão do repositório.

## Gerar os seis mockups

No mesmo projeto, com o design system NutriPlan selecionado e template
**blank**, um prompt por tela (Opus 5 · Extra). Cole cada bloco inteiro:

**Hoje (Mesa)**
> Tela "Hoje" do NutriPlan, 390 px, regime Mesa. Responde "o que eu faço
> agora": cartão AGORA no topo (a próxima refeição com hora, ou o treino em
> andamento), resumo do dia (anel de calorias com número grande, três macros
> em faixa e legenda), refeições do plano como lista — a da vez aberta, as
> outras colapsadas —, minicard de água com título "Água", anel, litros e
> "+250 ml", cartão de treino de hoje com a letra e a duração, aderência do
> dia. Barra inferior de QUATRO itens: Alimentação · Treino · Progresso ·
> Áreas. Estados: refeição vencida, refeição feita, água zerada. Use os
> componentes e tokens do DESIGN.md; nada além deles.

**Painel de treino (Mesa)**
> Tela "Treino" (`/treino/`), 390 px, Mesa. Responde "como é a minha
> semana": o treino de HOJE em destaque com uma ação primária "Abrir treino
> de hoje", e um cartão por sessão da semana (letra A/B/C, nome dos grupos,
> duração estimada, cor de sessão `--dia-*`), cada cartão é um link. NÃO
> lista exercícios. Estados: dia sem treino, semana completa.

**Ficha (Mesa)**
> Tela "Ficha" (`/treino/ficha/<id>/`), 390 px, Mesa. Responde "o que eu
> vou fazer hoje": lista numerada de exercícios — nome, séries × repetições,
> músculo, marcador do movimento principal —, seção "Complementares desta
> sessão", nota de tempo quando a ficha foi ajustada, e "Começar pelo
> primeiro". Cada linha é uma porta para a execução. Sem vídeo, sem campo de
> carga, sem cronômetro (isso mora na execução).

**Execução (FERRO)**
> Tela "Execução" (`/treino/agora/`), 390 px, regime FERRO (tokens da coluna
> Ferro). Responde "estou fazendo, e agora": UM exercício — vídeo curto no
> topo, "Exercício 3/7", carga atual com −2,5/+2,5 discretos, repetições,
> "Concluir série" como único primário, descanso com contagem, desfazer, e
> "carga da última vez". Número grande manda. Estados: descanso correndo,
> última série, exercício concluído.

**Progresso (Mesa)**
> Tela "Progresso" (`/historico/`), 390 px, Mesa. Responde "como estou
> indo": tiles de número grande (aderência %, kcal/dia, água média, treinos
> na semana), curva de peso com os últimos registros, barras de treino e
> água da semana, filtros Semana/Mês, conquistas como ícones do sprite (sem
> emoji). Estados vazios como convite, com uma ação.

**Entrada (Mesa)**
> Tela "Entrar" (`/conta/entrar/`), 390 px, Mesa, sem barra de navegação.
> Marca + wordmark + "Disciplina hoje. Resultados amanhã.", benefício em uma
> linha, campos e-mail e senha com rótulo e ajuda, "Entrar" primário,
> "Continuar com Google" secundário, links "Criar conta" e "Esqueci a senha",
> rodapé com Privacidade · Termos. Estados: erro no campo, sessão vencida
> ("O que você tocou não foi salvo — entre e refaça").

Revise cada mockup contra o `DESIGN.md`; peça ajuste do que não bater.

## Exportar

**Share → Project HTML → Export** (a opção "Standalone HTML" não é usada).
O zip cai em Downloads. Avise o Claude Code: "zip pronto em `<caminho>`".
Não renomeie nada e não copie para a raiz do projeto — a triagem é feita
em `artifacts/claude-design/export/`.

## O que mudou no formulário em relação ao vídeo

(anote aqui)
````

- [ ] **Step 2: Linkar no README do handoff**

Na tabela de arquivos do README, acrescentar a linha:
`| [`roteiro-claude-design.md`](roteiro-claude-design.md) | os nove passos do dono no claude.ai/design, com os seis prompts de mockup |`

- [ ] **Step 3: Commit**

```bash
git add docs/briefs/2026-09-15-chatgpt-claude-design/roteiro-claude-design.md docs/briefs/2026-09-15-chatgpt-claude-design/README.md
git commit -m "Roteiro do dono no claude.ai/design: setup com a semente e os seis prompts de mockup"
```

---

### Task 7: CHECKPOINT HUMANO — F2 e F3 no claude.ai/design

**Não é tarefa de código.** Entregar ao dono: o caminho da semente, o roteiro, e a mensagem "monte o sistema, gere os seis mockups, exporte e me diga onde está o zip". Enquanto isso, as Tasks 9, 13 e 14 (que não dependem do export) podem andar. As Tasks 8, 10 (passo 6 em diante), 11 e 12 esperam o zip.

- [ ] Zip recebido em `<caminho>`; descompactado em `artifacts/claude-design/export/` (nada apagado, nada movido).

---

### Task 8: `inventariar_export.py` — triagem com inventário

**Files:**
- Create: `scripts/inventariar_export.py`
- Test: `config/test_inventariar_export.py`
- Produz: `docs/briefs/2026-09-15-chatgpt-claude-design/inventario-export.md`

**Interfaces:**
- Produces: `classificar(caminho_relativo: str) -> str` ∈ {`tokens`, `referencia`, `interno`, `incerto`}; `inventariar(raiz_export: Path) -> list[dict]` (caminho, bytes, sha256, classe); `escrever_md(itens, destino: Path)`. Falha (`SystemExit`) se algum item ficar `incerto` E `--estrito` for passado — o padrão é listar.

- [ ] **Step 1: Teste que falha**

```python
# config/test_inventariar_export.py
"""O export do Claude Design vem com dump aninhado, artefato interno e uploads
(visto no Reel "Parte 2/2"). A triagem classifica por padrão de nome e
extensão — não por uma lista fixa que envelhece —, e nenhum arquivo fica
sem classe."""
import importlib
import tempfile
from pathlib import Path

from django.test import SimpleTestCase


def _arvore(tmp):
    raiz = Path(tmp) / "design-system-export"
    for rel in (
        "_adherence.oxlintrc.json", "_ds_bundle.js", "_ds_manifest.json", ".thumbnail",
        "readme.md", "SKILL.md", "styles.css", "thumbnail.html",
        "tokens/colors.json", "guidelines/typography.md",
        "components/button/index.html", "ui_kits/admin/preview.html",
        "NutriPlan - Hoje (standalone).html",
        "design-system-export/tokens/colors.json",
        "uploads/hoje-claro.png", "assets/icon-192.png", "misterio.xyz",
    ):
        alvo = raiz / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(b"x" * 10)
    return raiz


class InventarioTests(SimpleTestCase):
    def setUp(self):
        self.m = importlib.import_module("scripts.inventariar_export")

    def test_classifica_por_padrao(self):
        c = self.m.classificar
        self.assertEqual(c("_ds_bundle.js"), "interno")
        self.assertEqual(c(".thumbnail"), "interno")
        self.assertEqual(c("uploads/hoje-claro.png"), "interno")
        self.assertEqual(c("design-system-export/tokens/colors.json"), "interno")
        self.assertEqual(c("_adherence.oxlintrc.json"), "tokens")
        self.assertEqual(c("tokens/colors.json"), "tokens")
        self.assertEqual(c("guidelines/typography.md"), "tokens")
        self.assertEqual(c("readme.md"), "tokens")
        self.assertEqual(c("styles.css"), "tokens")
        self.assertEqual(c("components/button/index.html"), "referencia")
        self.assertEqual(c("NutriPlan - Hoje (standalone).html"), "referencia")
        self.assertEqual(c("assets/icon-192.png"), "referencia")
        self.assertEqual(c("misterio.xyz"), "incerto")

    def test_inventaria_tudo_e_escreve_o_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _arvore(tmp)
            itens = self.m.inventariar(raiz)
            self.assertEqual(len(itens), 17)
            self.assertTrue(all(len(i["sha256"]) == 64 for i in itens))
            destino = Path(tmp) / "inventario.md"
            self.m.escrever_md(itens, destino, origem="teste")
            md = destino.read_text(encoding="utf-8")
            self.assertIn("| `misterio.xyz` |", md)
            self.assertIn("incerto", md)
            self.assertIn("**17** arquivos", md)

    def test_estrito_recusa_incerto(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _arvore(tmp)
            with self.assertRaises(SystemExit):
                self.m.exigir_tudo_classificado(self.m.inventariar(raiz))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test config.test_inventariar_export -v 2`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

```python
# scripts/inventariar_export.py
# -*- coding: utf-8 -*-
"""Inventário classificado do export do Claude Design (spec 15/09/2026, §6).

    .venv/Scripts/python.exe scripts/inventariar_export.py artifacts/claude-design/export [--estrito]

Escreve docs/briefs/2026-09-15-chatgpt-claude-design/inventario-export.md.
Nada é apagado nem movido: a pasta é o registro. Classes:
  tokens      lidos e comparados com a direção C (tokens/, guidelines/, readme,
              styles.css, config de lint de aderência)
  referencia  HTML de tela ou de componente, imagens de assets — referência visual
  interno     bundle, manifesto, thumbnail, uploads, export aninhado
  incerto     precisa de leitura humana; `--estrito` recusa terminar com um
"""
import hashlib
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "briefs" / "2026-09-15-chatgpt-claude-design" / "inventario-export.md"


def classificar(rel):
    rel = rel.replace("\\", "/")
    nome = rel.rsplit("/", 1)[-1]
    partes = rel.split("/")
    if len(partes) > 1 and partes[0] == "design-system-export":
        return "interno"  # export aninhado: duplicata do que já está na raiz
    if partes[0] in ("uploads", ".thumbnail") or nome.startswith("_ds_") or nome in (".thumbnail", "thumbnail.html"):
        return "interno"
    if nome.startswith("_adherence") or partes[0] in ("tokens", "guidelines") or nome.lower() in ("readme.md", "skill.md", "styles.css", "design.md"):
        return "tokens"
    if nome.lower().endswith((".html", ".png", ".svg", ".jpg", ".jpeg", ".webp", ".woff2", ".woff")) or partes[0] in ("components", "ui_kits", "templates", "assets", "export"):
        return "referencia"
    return "incerto"


def inventariar(raiz):
    itens = []
    for caminho in sorted(p for p in raiz.rglob("*") if p.is_file()):
        rel = caminho.relative_to(raiz).as_posix()
        itens.append({
            "caminho": rel,
            "bytes": caminho.stat().st_size,
            "sha256": hashlib.sha256(caminho.read_bytes()).hexdigest(),
            "classe": classificar(rel),
        })
    return itens


def exigir_tudo_classificado(itens):
    incertos = [i["caminho"] for i in itens if i["classe"] == "incerto"]
    if incertos:
        raise SystemExit("sem classe: " + ", ".join(incertos))


def escrever_md(itens, destino, origem):
    por_classe = {}
    for i in itens:
        por_classe.setdefault(i["classe"], []).append(i)
    linhas = [
        "# Inventário do export do Claude Design",
        "",
        "Gerado por `scripts/inventariar_export.py` em {} a partir de `{}`. **{}** arquivos, {:.1f} MB.".format(
            datetime.now().strftime("%d/%m/%Y %H:%M"), origem, len(itens), sum(i["bytes"] for i in itens) / 1e6),
        "",
        "| classe | arquivos |", "|---|---:|",
    ] + ["| {} | {} |".format(c, len(por_classe.get(c, []))) for c in ("tokens", "referencia", "interno", "incerto")] + [
        "", "| caminho | bytes | sha256 (8) | classe |", "|---|---:|---|---|",
    ] + ["| `{}` | {} | `{}` | {} |".format(i["caminho"], i["bytes"], i["sha256"][:8], i["classe"]) for i in itens]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    raiz = Path(sys.argv[1])
    itens = inventariar(raiz)
    escrever_md(itens, DESTINO, origem=raiz.as_posix())
    print("{} arquivos → {}".format(len(itens), DESTINO))
    if "--estrito" in sys.argv:
        exigir_tudo_classificado(itens)
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `.venv/Scripts/python.exe manage.py test config.test_inventariar_export -v 2`
Expected: 3 OK.

- [ ] **Step 5: Rodar no export real**

Run: `.venv/Scripts/python.exe scripts/inventariar_export.py artifacts/claude-design/export --estrito`
Expected: o `.md` escrito; se acusar `incerto`, ler o arquivo, decidir a classe e ampliar `classificar` (com teste) — não editar o `.md` à mão.

- [ ] **Step 6: Commit**

```bash
git add scripts/inventariar_export.py config/test_inventariar_export.py docs/briefs/2026-09-15-chatgpt-claude-design/inventario-export.md
git commit -m "Triagem do export do Claude Design: inventário classificado, nada apagado"
```

---

### Task 9: O leitor de token resolve `var()`; Ferro em um bloco e dois gatilhos; PWA acompanha o CSS

**Files:**
- Modify: `config/tests.py` (`_tokens`), `config/test_tema_claro.py` (`test_a_moldura_do_navegador_acompanha_a_base`)
- Create: `config/test_ferro.py`

**Interfaces:**
- Produces: `_tokens(css, escopo)` resolve `var(--x)` contra o `:root`; `config.test_ferro.ler_bloco(css, escopo) -> dict[str, str]` (nome → valor cru); a estrutura que a Task 10 tem de satisfazer.

- [ ] **Step 1: Escrever os testes que falham**

```python
# config/test_ferro.py
"""Ferro é UM bloco de valores com DOIS gatilhos (direção C §1).

Os valores moram uma vez em `:root`, como `--ferro-*`; o bloco do tema
escuro e o `body.modo-foco` só ligam `--bg: var(--ferro-bg)` e companhia.
Duplicar a lista de valores é como uma segunda paleta nasce sem ninguém
decidir — e este teste é a trava."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
ESCURO = "prefers-color-scheme: dark) {" + chr(10) + "  :root {"
FOCO = "body.modo-foco {"


def ler_bloco(css, escopo):
    trecho = css.split(escopo, 1)[1].split(chr(10) + "}", 1)[0] if escopo == ":root {" else css.split(escopo, 1)[1].split("}", 1)[0]
    return dict(re.findall(r"^\s*(--[\w-]+):\s*([^;]+);", trecho, re.M))


class FerroTests(SimpleTestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")
        self.raiz = ler_bloco(self.css, ":root {")
        self.escuro = ler_bloco(self.css, ESCURO)
        self.foco = ler_bloco(self.css, FOCO)

    def test_os_valores_de_ferro_existem_uma_vez_no_root(self):
        ferro = {k for k in self.raiz if k.startswith("--ferro-")}
        self.assertGreaterEqual(len(ferro), 20)
        for nome in ("--ferro-bg", "--ferro-surface", "--ferro-text", "--ferro-brand", "--ferro-folha"):
            self.assertIn(nome, ferro)

    def test_os_dois_gatilhos_ligam_os_mesmos_tokens_e_so_por_var(self):
        self.assertEqual(set(self.escuro) - {"color-scheme"}, set(self.foco) - {"color-scheme"})
        for bloco, rotulo in ((self.escuro, "escuro"), (self.foco, "modo-foco")):
            for nome, valor in bloco.items():
                if nome == "color-scheme":
                    continue
                with self.subTest(gatilho=rotulo, token=nome):
                    self.assertEqual(valor.strip(), "var(--ferro-" + nome[2:] + ")")
                    self.assertIn("--ferro-" + nome[2:], self.raiz)

    def test_nenhum_ferro_sem_dono(self):
        """Todo `--ferro-x` liga um `--x` que existe em Mesa."""
        for nome in (k for k in self.raiz if k.startswith("--ferro-")):
            with self.subTest(token=nome):
                self.assertIn("--" + nome[len("--ferro-"):], self.raiz)

    def test_o_modo_foco_declara_o_esquema_escuro(self):
        """Sem `color-scheme: dark`, campo e rolagem nativos ficam claros no Ferro."""
        trecho = self.css.split(FOCO, 1)[1].split("}", 1)[0]
        self.assertIn("color-scheme: dark;", trecho)
```

Em `config/test_tema_claro.py`, substituir o corpo de `test_a_moldura_do_navegador_acompanha_a_base` por leitura do CSS (a razão nova vai na docstring: "a moldura acompanha o `--bg` de cada tema, e a trava lê o CSS em vez de repetir o hex"):

```python
    def test_a_moldura_do_navegador_acompanha_a_base(self):
        """`theme-color` e manifesto pintam a barra de status e a tela de
        abertura ANTES da página. Divergir do fundo real produz uma emenda
        visível de meio segundo toda vez que o app abre — e já aconteceu.
        A trava lê o `--bg` de cada tema no CSS em vez de repetir o hex:
        assim a Mesa & Ferro (15/09/2026) troca a paleta sem que este teste
        vire uma segunda cópia dela."""
        from config.tests import _tokens
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
        claro = _tokens(css, ":root {")
        escuro = _tokens(css, "prefers-color-scheme: dark) {" + chr(10) + "  :root {")
        self.assertEqual(settings.PWA_THEME_COLOR, claro["--bg"])
        self.assertEqual(settings.PWA_BACKGROUND_COLOR, claro["--bg"])
        self.assertEqual(settings.PWA_DARK_COLOR, escuro["--bg"])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe manage.py test config.test_ferro config.test_tema_claro -v 2`
Expected: `test_ferro` FAIL (`--ferro-*` inexistentes; `body.modo-foco {` não encontrado → `IndexError`); `test_tema_claro` passa por enquanto (os valores atuais batem) — ele vai continuar verde na Task 10 se `settings.py` for atualizado junto.

- [ ] **Step 3: `_tokens` resolve `var()` (config/tests.py)**

Substituir `_tokens`:

```python
def _tokens(css, escopo):
    """Lê as variáveis de cor de um bloco (`:root`, tema escuro, `body.modo-foco`).

    Desde a Mesa & Ferro (15/09/2026) os blocos-gatilho não carregam hex:
    escrevem `--bg: var(--ferro-bg)`, e o valor mora UMA vez no `:root`.
    Este leitor resolve o `var()` contra o `:root` para que todo teste de
    contraste continue medindo cor de verdade — sabotar um hex de
    `--ferro-*` deixa os testes do escuro vermelhos, que é o controle.
    """
    trecho = css.split(escopo, 1)[1].split("}", 1)[0]
    raiz = None
    valores = {}
    for linha in trecho.splitlines():
        linha = linha.strip()
        if linha.startswith("--") and ":" in linha:
            nome, valor = linha.split(":", 1)
            valor = valor.split(";")[0].strip()
            if valor.startswith("var(--") and valor.endswith(")"):
                if raiz is None:
                    raiz = _tokens(css, ":root {") if escopo != ":root {" else {}
                valor = raiz.get(valor[4:-1], valor)
            if valor.startswith("#") and len(valor) == 7:
                valores[nome.strip()] = valor
    return valores
```

- [ ] **Step 4: Rodar a suíte de tokens e ver que nada mudou de veredito**

Run: `.venv/Scripts/python.exe manage.py test config.tests.ContrastTests config.tests.DesignSystemTests config.tests.DayColourContrastTests config.tests.PillContrastTests config.test_tema_claro -v 2`
Expected: todos OK (o CSS ainda é o antigo, com hex literal; o leitor é compatível).

- [ ] **Step 5: Commit (o `test_ferro` fica vermelho até a Task 10 — commit só do leitor e do teste da moldura; `test_ferro.py` entra no commit da Task 10)**

```bash
git add config/tests.py config/test_tema_claro.py
git commit -m "Leitor de tokens resolve var(): o Ferro vai morar uma vez no :root; a moldura do PWA passa a ler o CSS"
```

---

### Task 10: A paleta Mesa & Ferro no `app.css` (T3.1 do plano mestre)

**Files:**
- Modify: `static/css/app.css` §1 (`:root` linhas 27–380; bloco `@media (prefers-color-scheme: dark)` linhas 390–427), usos de `--accent`/`--warm`/`--warm-soft`/`--border`/`--border-strong`/`--grad-brand`
- Modify: `config/settings.py` (`PWA_THEME_COLOR`, `PWA_BACKGROUND_COLOR`, `PWA_DARK_COLOR`), `config/tests.py` (`DesignSystemTests.test_the_dark_palette_is_the_one_the_design_system_names`, `ContrastTests.TINGIDOS`, `ContrastTests.PARES_MEDIDOS` novo), `config/test_tema_claro.py` (nomes renomeados), demais testes que citam os nomes antigos
- Test: `config/test_ferro.py` (Task 9), `config/tests.py`, `config/test_tema_claro.py`, `config/test_design_system.py`

**Interfaces:**
- Consumes: `_tokens` com `var()` (Task 9).
- Produces: tokens Mesa no `:root`; `--ferro-*` no `:root`; `@media (prefers-color-scheme: dark) { :root { … var(--ferro-*) } }`; `body.modo-foco { color-scheme: dark; … var(--ferro-*) }`. Nomes novos: `--agua`, `--agua-texto`, `--brasa`, `--terra`, `--terra-soft`, `--chama`, `--fio`, `--fio-forte`. Nomes que saem: `--accent`, `--warm`, `--warm-soft`, `--border`, `--border-strong`, `--grad-brand`. **Decisões de nome que divergem do plano mestre T3.1, com razão:** `data-theme` não entra (o app não tem alternador de tema; dois gatilhos bastam e são os que a direção C cita); `--glow` fica (quatro usos em cartão, é assunto da T3.3); hex literal nos gatilhos NÃO — o leitor resolve `var()` (Task 9), e é o que faz o valor existir uma vez.

- [ ] **Step 1: Ver o vermelho de partida**

Run: `.venv/Scripts/python.exe manage.py test config.test_ferro -v 2`
Expected: FAIL (é o "teste que falha" desta task).

- [ ] **Step 2: Renomear, com `perl` e sem tocar em classe**

```bash
FILES=$(grep -rl -- "--accent\|--warm\|--border\|--grad-brand" --include=*.css --include=*.html --include=*.js --include=*.py static templates config plans workouts accounts achievements push gestao demo scripts 2>/dev/null)
perl -pi -e 's/(?<![\w-])--warm-soft(?![\w-])/--terra-soft/g; s/(?<![\w-])--warm(?![\w-])/--terra/g; s/(?<![\w-])--accent-soft(?![\w-])/--agua-soft/g; s/(?<![\w-])--accent(?![\w-])/--agua/g; s/(?<![\w-])--border-strong(?![\w-])/--fio-forte/g; s/(?<![\w-])--border(?![\w-])/--fio/g' $FILES
grep -rn -- "--accent\b\|--warm\b\|--border\b\|--border-strong" static templates config --include=*.css --include=*.html --include=*.py | grep -v "border-radius\|border-color" | head
```
Expected: o último `grep` devolve ZERO linhas. `--grad-brand`: apagar a declaração no `:root` e o único uso (`grep -n "grad-brand" static/css/app.css`) — o uso vira `background: var(--brand)` (é o que a direção C pede: o gradiente verde→azul sai).

O `(?<![\w-])` protege os modificadores BEM: `.pill--warm` continua `.pill--warm` (classe, não token — só o `var(--warm)` dentro dela vira `var(--terra)`), e `entrada__accent`/`app-bar__accent` nem casam. Conferir com `git diff --stat templates/` = 0 arquivos.

- [ ] **Step 3: Escrever a paleta Mesa no `:root`**

Trocar os valores, mantendo cada token na linha em que está (os comentários explicam a história e continuam valendo; onde o comentário cita o hex antigo como "medido", acrescentar uma linha `MESA & FERRO (15/09/2026): <novo> — <contraste medido>`):

```css
  --bg: #f5f3ee;            /* linho */
  --surface: #ffffff;
  --surface-2: #efece4;
  --surface-3: #ebe8de;
  --surface-focus: #e3f1e8;
  --canvas-topo: #ffffff;
  --fio: rgba(20, 31, 26, .10);
  --fio-forte: rgba(20, 31, 26, .22);
  --text: #141f1a;
  --text-dim: #485550;
  --text-mute: #55625c;
  --brand: #0c6b40;
  --brand-strong: #08512f;
  --brand-soft: #dff0e6;
  --folha: #3f9718;
  --on-brand: #ffffff;
  --agua: #1e6e96;
  --agua-texto: #175877;
  --brasa: #a63f18;
  --terra: #8a5109;
  --terra-soft: #fbf0e0;
  --chama: #c8620a;
  --carb: #ad6d16;
  --fat: #5568a6;
  --danger: #b3261e;
  --danger-soft: #fdecea;
```

(`--dia-a…e`, raios, texto, sombras, `--veu`, `--edge`, `--mov-*` ficam como estão.)

- [ ] **Step 4: O bloco Ferro, UMA vez, no fim do `:root`**

Antes do `}` que fecha o `:root` (linha ~380), acrescentar:

```css
  /* FERRO — o segundo regime de luz, escrito UMA vez.
     Dois gatilhos ligam estes valores: `prefers-color-scheme: dark` (quem
     prefere escuro vê o app inteiro em Ferro) e `body.modo-foco` (a
     execução e a corrida em andamento nascem em Ferro por decisão de
     produto). Nenhum dos dois repete hex — `config/test_ferro.py` é a
     trava. Direção C, docs/briefs/design/direcao-c-mesa-e-ferro.md §2;
     `--ferro-text-mute` é #96a29c e não o #8f9b95 da direção: medido,
     5,10:1 sobre surface-3 contra 4,68. */
  --ferro-bg: #0e1412;
  --ferro-surface: #161d1a;
  --ferro-surface-2: #1d2622;
  --ferro-surface-3: #26312b;
  --ferro-surface-focus: #123024;
  --ferro-canvas-topo: #0a1210;
  --ferro-fio: rgba(255, 255, 255, .08);
  --ferro-fio-forte: rgba(255, 255, 255, .16);
  --ferro-text: #f4f7f5;
  --ferro-text-dim: #b6c1bb;
  --ferro-text-mute: #96a29c;
  --ferro-brand: #22c98a;
  --ferro-brand-strong: #4ddb9f;
  --ferro-brand-soft: #0f2a20;
  --ferro-folha: #6fcf4a;
  --ferro-on-brand: #04140e;
  --ferro-agua: #5fbdf0;
  --ferro-agua-texto: #5fbdf0;
  --ferro-brasa: #ff9a7a;
  --ferro-terra: #f2b04e;
  --ferro-terra-soft: #33260f;
  --ferro-chama: #ffa53a;
  --ferro-carb: #e6b35d;
  --ferro-fat: #93a8de;
  --ferro-danger: #ff8a80;
  --ferro-danger-soft: #33191a;
  --ferro-dia-a: #4ade9b;
  --ferro-dia-b: #6cc7ff;
  --ferro-dia-c: #f6c453;
  --ferro-dia-d: #cbb0ff;
  --ferro-dia-e: #ff9d8a;
  --ferro-veu: rgba(4, 8, 7, .72);
  --ferro-edge: inset 0 1px 0 rgba(255, 255, 255, .05);
  --ferro-shadow-rest: 0 1px 2px rgba(0, 0, 0, .38), 0 10px 26px -20px rgba(0, 0, 0, .85);
  --ferro-shadow-lift: 0 2px 6px rgba(0, 0, 0, .45), 0 20px 44px -22px rgba(0, 0, 0, .95);
  --ferro-glow: 0 0 0 1px rgba(34, 201, 138, .3), 0 10px 30px -14px rgba(34, 201, 138, .45);
```

- [ ] **Step 5: Os dois gatilhos**

Substituir o bloco `@media (prefers-color-scheme: dark) { :root { … } }` inteiro por (mantendo EXATAMENTE `prefers-color-scheme: dark) {` + quebra + `  :root {`, que é a âncora dos testes):

```css
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: var(--ferro-bg);
    --surface: var(--ferro-surface);
    --surface-2: var(--ferro-surface-2);
    --surface-3: var(--ferro-surface-3);
    --surface-focus: var(--ferro-surface-focus);
    --canvas-topo: var(--ferro-canvas-topo);
    --fio: var(--ferro-fio);
    --fio-forte: var(--ferro-fio-forte);
    --text: var(--ferro-text);
    --text-dim: var(--ferro-text-dim);
    --text-mute: var(--ferro-text-mute);
    --brand: var(--ferro-brand);
    --brand-strong: var(--ferro-brand-strong);
    --brand-soft: var(--ferro-brand-soft);
    --folha: var(--ferro-folha);
    --on-brand: var(--ferro-on-brand);
    --agua: var(--ferro-agua);
    --agua-texto: var(--ferro-agua-texto);
    --brasa: var(--ferro-brasa);
    --terra: var(--ferro-terra);
    --terra-soft: var(--ferro-terra-soft);
    --chama: var(--ferro-chama);
    --carb: var(--ferro-carb);
    --fat: var(--ferro-fat);
    --danger: var(--ferro-danger);
    --danger-soft: var(--ferro-danger-soft);
    --dia-a: var(--ferro-dia-a);
    --dia-b: var(--ferro-dia-b);
    --dia-c: var(--ferro-dia-c);
    --dia-d: var(--ferro-dia-d);
    --dia-e: var(--ferro-dia-e);
    --veu: var(--ferro-veu);
    --edge: var(--ferro-edge);
    --shadow-rest: var(--ferro-shadow-rest);
    --shadow-lift: var(--ferro-shadow-lift);
    --glow: var(--ferro-glow);
  }
}

/* O SEGUNDO GATILHO do Ferro: a classe que o servidor escreve no <body>.
   Mesma lista, mesmos `var()` — `config/test_ferro.py` compara os dois. */
body.modo-foco {
  color-scheme: dark;
  --bg: var(--ferro-bg);
  --surface: var(--ferro-surface);
  --surface-2: var(--ferro-surface-2);
  --surface-3: var(--ferro-surface-3);
  --surface-focus: var(--ferro-surface-focus);
  --canvas-topo: var(--ferro-canvas-topo);
  --fio: var(--ferro-fio);
  --fio-forte: var(--ferro-fio-forte);
  --text: var(--ferro-text);
  --text-dim: var(--ferro-text-dim);
  --text-mute: var(--ferro-text-mute);
  --brand: var(--ferro-brand);
  --brand-strong: var(--ferro-brand-strong);
  --brand-soft: var(--ferro-brand-soft);
  --folha: var(--ferro-folha);
  --on-brand: var(--ferro-on-brand);
  --agua: var(--ferro-agua);
  --agua-texto: var(--ferro-agua-texto);
  --brasa: var(--ferro-brasa);
  --terra: var(--ferro-terra);
  --terra-soft: var(--ferro-terra-soft);
  --chama: var(--ferro-chama);
  --carb: var(--ferro-carb);
  --fat: var(--ferro-fat);
  --danger: var(--ferro-danger);
  --danger-soft: var(--ferro-danger-soft);
  --dia-a: var(--ferro-dia-a);
  --dia-b: var(--ferro-dia-b);
  --dia-c: var(--ferro-dia-c);
  --dia-d: var(--ferro-dia-d);
  --dia-e: var(--ferro-dia-e);
  --veu: var(--ferro-veu);
  --edge: var(--ferro-edge);
  --shadow-rest: var(--ferro-shadow-rest);
  --shadow-lift: var(--ferro-shadow-lift);
  --glow: var(--ferro-glow);
}
```

Nota: `--edge`, `--shadow-rest`, `--shadow-lift`, `--glow` e `--veu` do tema claro continuam declarados no `:root` onde já estão (o teste `test_nenhum_ferro_sem_dono` cobra que todo `--ferro-x` tenha um `--x` em Mesa).

- [ ] **Step 6: `settings.py` e os testes de identidade**

`config/settings.py`: `PWA_THEME_COLOR = "#f5f3ee"`, `PWA_BACKGROUND_COLOR = "#f5f3ee"`, `PWA_DARK_COLOR = "#0e1412"`.

`config/tests.py`, `DesignSystemTests.test_the_dark_palette_is_the_one_the_design_system_names`: os oito `assertEqual` passam a ser os valores de Ferro (`--bg` `#0e1412`, `--surface` `#161d1a`, `--surface-2` `#1d2622`, `--surface-3` `#26312b`, `--surface-focus` `#123024`, `--brand` `#22c98a`, `--text` `#f4f7f5`, `--text-mute` `#96a29c`), e a docstring ganha o parágrafo: "MESA & FERRO (15/09/2026): a identidade passou a ser a da direção C — linho e grafite esverdeado; os valores foram medidos na direção e no plano mestre, e `ContrastTests` continua provando a legibilidade."

`ContrastTests.TINGIDOS` passa a `("--brand-soft", "--terra-soft", "--agua-soft", "--danger-soft")`. Acrescentar à classe os pares que a direção C mede:

```python
    #: Pares que a direção C mediu à mão e que a trava geral não cobre:
    #: verde de ação como texto sobre o chip tonal, texto quieto sobre a
    #: superfície mais escura do claro, e a folha como OBJETO GRÁFICO
    #: (1.4.11: 3,0) sobre o trilho do anel. Nos dois temas.
    PARES_MEDIDOS = (("--brand", "--brand-soft", 4.5), ("--text-mute", "--surface-3", 4.5), ("--folha", "--surface-2", 3.0), ("--agua", "--surface-2", 3.0), ("--brasa", "--surface-2", 3.0), ("--terra", "--surface-2", 3.0))

    def _conferir_pares(self, escopo, rotulo):
        tokens = _tokens(self.css, escopo)
        for cor, fundo, minimo in self.PARES_MEDIDOS:
            if cor not in tokens or fundo not in tokens:
                continue
            with self.subTest(tema=rotulo, cor=cor, fundo=fundo):
                razao = _contraste(tokens[cor], tokens[fundo])
                self.assertGreaterEqual(razao, minimo, f"{cor} sobre {fundo} dá {razao:.2f}:1")

    def test_light_theme_measured_pairs(self):
        self._conferir_pares(":root {", "claro")

    def test_dark_theme_measured_pairs(self):
        self._conferir_pares("prefers-color-scheme: dark) {" + chr(10) + "  :root {", "escuro")

    def test_modo_foco_is_the_dark_palette(self):
        """O segundo gatilho resolve para a MESMA paleta do escuro."""
        escuro = _tokens(self.css, "prefers-color-scheme: dark) {" + chr(10) + "  :root {")
        foco = _tokens(self.css, "body.modo-foco {")
        self.assertEqual(foco, escuro)
```

- [ ] **Step 7: Rodar os testes dirigidos**

Run: `.venv/Scripts/python.exe manage.py test config.test_ferro config.tests.ContrastTests config.tests.DesignSystemTests config.tests.DayColourContrastTests config.tests.PillContrastTests config.tests.GymReadyTests config.test_tema_claro config.test_design_system -v 2`
Expected: tudo OK. Se um par medido falhar por centésimos, o valor que muda é o da direção C **com a razão escrita no comentário do token** — nunca o mínimo do teste.

- [ ] **Step 8: Controle positivo (sabotagem)**

Trocar `--ferro-text-mute: #96a29c` por `#7a8681` e rodar `config.tests.ContrastTests`: deve ficar VERMELHO no escuro. Reverter. Trocar um `var(--ferro-bg)` do `body.modo-foco` por `#000000` e rodar `config.test_ferro`: VERMELHO. Reverter.

- [ ] **Step 9: QA no navegador, os dois temas, 320 e 390**

Com o servidor de pé, usando a sessão `semente` da Task 5: `open` em `/`, `/treino/`, `/treino/agora/`, `/historico/`, `/conta/entrar/`; `viewport 320 700` e `390 844`; `tema claro` e `tema escuro`; `screenshot` em `artifacts/claude-design/depois/<tela>-<largura>-<tema>.png`; `eval "$(cat scripts/qa/medir.js)"` em `depois/<tela>-<tema>.json`. Conferir a olho: linho no claro, grafite esverdeado no escuro, nenhum texto sumido, nenhum elemento em cor antiga (azul `#196288` da água antiga é o suspeito — `grep -c 196288 static/css/app.css` deve ser 0).

- [ ] **Step 10: Suíte completa e commit**

Run: `.venv/Scripts/python.exe manage.py test` (≈ 20 min)
Expected: verde; as catracas `TETO_FONT_SIZE_CRU`/`TETO_ESPACO_CRU` iguais ou menores (`test_o_teto_registrado_nao_esta_folgado` diz se dá para descer — se disser, desça).

```bash
git add static/css/app.css config/settings.py config/tests.py config/test_ferro.py config/test_tema_claro.py config/test_design_system.py $(git diff --name-only)
git commit -m "Mesa & Ferro nos tokens: linho e grafite, Ferro escrito uma vez com dois gatilhos, água/brasa/terra/chama nomeados"
```

Na mensagem, incluir a tabela `medir.js` antes/depois (`sizes`, `weights`, `radii`, `shadowed`, `bgs`, `btnKinds`) para a Home a 390 nos dois temas.

---

### Task 11: Comparar o export com a spec — `proposto-nao-adotado.md`

**Files:**
- Create: `scripts/tokens_do_export.py`
- Create: `docs/briefs/2026-09-15-chatgpt-claude-design/proposto-nao-adotado.md`
- Test: `config/test_tokens_do_export.py`

**Interfaces:**
- Produces: `extrair(raiz_export: Path) -> dict[str, set[str]]` (nome de custom property → valores encontrados, em `.css/.json/.md/.html` de classe `tokens` e `referencia`); `comparar(encontrados, spec: dict[str, str]) -> list[tuple[str, str, str]]` (token, proposto, spec) só para os que diferem.

- [ ] **Step 1: Teste que falha**

```python
# config/test_tokens_do_export.py
"""A spec ganha; a comparação existe para que a diferença fique escrita."""
import importlib
import tempfile
from pathlib import Path

from django.test import SimpleTestCase


class TokensDoExportTests(SimpleTestCase):
    def test_extrai_custom_properties_de_css_json_e_md(self):
        m = importlib.import_module("scripts.tokens_do_export")
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "tokens").mkdir()
            (raiz / "styles.css").write_text(":root{--bg:#f5f3ee;--brand:#0d6d42}", encoding="utf-8")
            (raiz / "tokens" / "colors.json").write_text('{"--brand": "#0d6d42", "--novo": "#123456"}', encoding="utf-8")
            (raiz / "uploads").mkdir()
            (raiz / "uploads" / "x.css").write_text(":root{--bg:#000000}", encoding="utf-8")  # interno: ignorado
            achados = m.extrair(raiz)
        self.assertEqual(achados["--bg"], {"#f5f3ee"})
        self.assertEqual(achados["--brand"], {"#0d6d42"})
        self.assertIn("--novo", achados)

    def test_compara_e_lista_so_as_diferencas(self):
        m = importlib.import_module("scripts.tokens_do_export")
        difs = m.comparar({"--bg": {"#f5f3ee"}, "--brand": {"#0d6d42"}, "--novo": {"#123456"}}, {"--bg": "#f5f3ee", "--brand": "#0c6b40"})
        self.assertEqual(difs, [("--brand", "#0d6d42", "#0c6b40"), ("--novo", "#123456", "(não existe na spec)")])
```

- [ ] **Step 2: Rodar e ver falhar** — `manage.py test config.test_tokens_do_export` → módulo inexistente.

- [ ] **Step 3: Implementar**

```python
# scripts/tokens_do_export.py
# -*- coding: utf-8 -*-
"""Compara os tokens que o Claude Design exportou com a direção C.

    .venv/Scripts/python.exe scripts/tokens_do_export.py artifacts/claude-design/export

Imprime uma tabela `token | proposto | spec` só com as diferenças. A spec
ganha (spec 15/09/2026, §7); a tabela vai para `proposto-nao-adotado.md`
com uma linha de motivo por item — escrita à mão, porque a razão é humana.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventariar_export import classificar  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;\"'}]+)")


def _spec():
    """Os valores Mesa da direção C, lidos do `:root` do app.css (Task 10)."""
    from config.tests import _tokens
    css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
    return _tokens(css, ":root {")


def extrair(raiz):
    achados = {}
    for caminho in sorted(p for p in raiz.rglob("*") if p.is_file()):
        rel = caminho.relative_to(raiz).as_posix()
        if classificar(rel) not in ("tokens", "referencia") or caminho.suffix.lower() not in (".css", ".json", ".md", ".html"):
            continue
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        pares = []
        if caminho.suffix.lower() == ".json":
            try:
                dados = json.loads(texto)
                if isinstance(dados, dict):
                    pares = [(k, str(v)) for k, v in dados.items() if str(k).startswith("--")]
            except ValueError:
                pass
        pares += DECL.findall(texto)
        for nome, valor in pares:
            valor = valor.strip()
            if valor.startswith("#") or valor.startswith("rgb"):
                achados.setdefault(nome, set()).add(valor.lower())
    return achados


def comparar(encontrados, spec):
    difs = []
    for nome in sorted(encontrados):
        propostos = sorted(encontrados[nome])
        if nome.startswith("--ferro-"):
            continue
        esperado = spec.get(nome)
        if esperado is None:
            difs.append((nome, " / ".join(propostos), "(não existe na spec)"))
        elif esperado.lower() not in encontrados[nome]:
            difs.append((nome, " / ".join(propostos), esperado))
    return difs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    difs = comparar(extrair(Path(sys.argv[1])), _spec())
    print("| token | proposto pelo Claude Design | spec (direção C) | motivo |")
    print("|---|---|---|---|")
    for nome, proposto, esperado in difs:
        print("| `{}` | `{}` | `{}` | |".format(nome, proposto, esperado))
```

- [ ] **Step 4: Rodar o teste e ver passar** — 2 OK.

- [ ] **Step 5: Gerar a tabela e escrever os motivos**

Run: `.venv/Scripts/python.exe scripts/tokens_do_export.py artifacts/claude-design/export > /tmp/difs.md`
Criar `docs/briefs/2026-09-15-chatgpt-claude-design/proposto-nao-adotado.md` com um cabeçalho ("A spec ganha. O que o Claude Design propôs e por que não entrou — ou entrou como item para o dono.") e a tabela, preenchendo a coluna **motivo** linha a linha. Quando a proposta for melhor mas mudar uma decisão fechada, o motivo é "→ decisão do dono" e a linha entra também na seção "Para o dono decidir" no fim do arquivo.

- [ ] **Step 6: Commit**

```bash
git add scripts/tokens_do_export.py config/test_tokens_do_export.py docs/briefs/2026-09-15-chatgpt-claude-design/proposto-nao-adotado.md
git commit -m "O que o Claude Design propôs e não entrou: tabela token a token, com o motivo"
```

---

### Task 12: Referências — os seis mockups a 390 px em `docs/`

**Files:**
- Create: `docs/briefs/design/referencias/claude-design/{hoje-mesa,treino-painel-mesa,treino-ficha-mesa,treino-execucao-ferro,progresso-mesa,entrada-mesa}.png`
- Modify: `docs/briefs/README.md` (uma linha)
- Test: `config/test_referencias.py`

- [ ] **Step 1: Teste que falha**

```python
# config/test_referencias.py
"""Imagem no repositório tem teto: as 14 MB de shots de 14/09 ficaram fora,
e estas seis só entram porque cabem (≤ 250 KB cada, spec §8)."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

PASTA = Path(settings.BASE_DIR) / "docs" / "briefs" / "design" / "referencias" / "claude-design"
ESPERADAS = ("hoje-mesa", "treino-painel-mesa", "treino-ficha-mesa", "treino-execucao-ferro", "progresso-mesa", "entrada-mesa")


class ReferenciasTests(SimpleTestCase):
    def test_as_seis_existem_e_cabem(self):
        for nome in ESPERADAS:
            arquivo = PASTA / (nome + ".png")
            with self.subTest(nome=nome):
                self.assertTrue(arquivo.is_file(), arquivo)
                self.assertLessEqual(arquivo.stat().st_size, 250 * 1024, f"{nome}: {arquivo.stat().st_size} bytes")
```

- [ ] **Step 2: Rodar e ver falhar** — FAIL, arquivos inexistentes.

- [ ] **Step 3: Capturar os mockups**

Localizar no `inventario-export.md` os HTMLs de classe `referencia` que correspondem às seis telas (nome do arquivo). Para cada um, com `nav.py`:

```bash
NAV=".venv/Scripts/python.exe scripts/qa/nav.py mock"
$NAV viewport 390 844
$NAV open "file:///C:/Users/biel-/nutriplan-infra/artifacts/claude-design/export/<caminho do html>"
$NAV screenshot docs/briefs/design/referencias/claude-design/hoje-mesa.png
```
Se um PNG passar de 250 KB: `.venv/Scripts/python.exe -c "from PIL import Image; im=Image.open('x.png'); im.convert('P', palette=Image.ADAPTIVE, colors=128).save('x.png', optimize=True)"` (Pillow já está no venv por `make_icons.py`). Se ainda passar, fica em `artifacts/` e a linha do README aponta para lá.

- [ ] **Step 4: Rodar o teste e ver passar.**

- [ ] **Step 5: README dos briefs**

Em `docs/briefs/README.md`, depois do parágrafo dos anexos do brief de design, acrescentar:
"Referências geradas no Claude Design em 15/09/2026 a partir da direção C: [`design/referencias/claude-design/`](design/referencias/claude-design/) (seis telas a 390 px; o export inteiro fica em `artifacts/claude-design/`, fora do git). Spec e handoff: [`2026-09-15-chatgpt-claude-design/`](2026-09-15-chatgpt-claude-design/README.md)."

- [ ] **Step 6: Commit**

```bash
git add docs/briefs/design/referencias/claude-design/*.png docs/briefs/README.md config/test_referencias.py
git commit -m "Referências do Claude Design: as seis telas a 390 px, com teto de tamanho testado"
```

---

### Task 13: A vitrine — rota, permissão e formulário

**Files:**
- Create: `gestao/forms_vitrine.py`
- Modify: `gestao/views.py` (`VitrineView`), `gestao/urls.py` (`vitrine/`)
- Create: `templates/gestao/vitrine.html` (versão mínima; a Task 14 completa)
- Test: `gestao/test_vitrine.py`

**Interfaces:**
- Produces: rota `gestao:vitrine` (`/gestao/vitrine/`); contexto `form_limpo`, `form_com_erro` (`FormularioDaVitrine`), `regime` (`"mesa"|"ferro"`), `aba="vitrine"`, `sem_tabbar=True`, `google_login_enabled=True`, `legal_publicado=True`, `conquistas_novas` (lista de `SimpleNamespace`); `body_class` no template = `modo-foco` quando `regime == "ferro"`.

- [ ] **Step 1: Teste que falha**

```python
# gestao/test_vitrine.py
"""A vitrine é ferramenta de quem mantém: mesma permissão do painel, fora
da navegação, e a MESMA página nos dois regimes — a classe do regime vem do
servidor, nunca de `:has()` nem de JavaScript."""
from django.contrib.auth.models import Permission

from .tests import BaseDoPainel


class AcessoAVitrineTests(BaseDoPainel):
    def test_anonimo_vai_para_o_login(self):
        resposta = self.client.get("/gestao/vitrine/")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/entrar/", resposta["Location"])

    def test_usuario_comum_leva_403(self):
        self.client.force_login(self.pessoa("comum@exemplo.com"))
        self.assertEqual(self.client.get("/gestao/vitrine/").status_code, 403)

    def test_quem_tem_a_permissao_entra_mesmo_sem_ser_staff(self):
        pessoa = self.pessoa("curadora@exemplo.com")
        pessoa.user_permissions.add(Permission.objects.get(codename="ver_painel_de_gestao", content_type__app_label="accounts"))
        self.client.force_login(pessoa)
        self.assertEqual(self.client.get("/gestao/vitrine/").status_code, 200)


class RegimeDaVitrineTests(BaseDoPainel):
    def setUp(self):
        self.client.force_login(self.operador())

    def test_sem_parametro_e_mesa(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertNotIn('class="modo-foco', html)
        self.assertNotIn(' modo-foco"', html)
        self.assertIn("Vitrine · Mesa", html)

    def test_regime_ferro_escreve_a_classe_no_body(self):
        html = self.client.get("/gestao/vitrine/?regime=ferro").content.decode()
        self.assertIn("<body class=\"modo-foco", html)
        self.assertIn("Vitrine · Ferro", html)

    def test_regime_desconhecido_cai_em_mesa(self):
        html = self.client.get("/gestao/vitrine/?regime=roxo").content.decode()
        self.assertNotIn("modo-foco", html.split("<main", 1)[0])
        self.assertIn("Vitrine · Mesa", html)

    def test_a_vitrine_esta_fora_da_navegacao_e_do_cache(self):
        resposta = self.client.get("/gestao/vitrine/")
        html = resposta.content.decode()
        self.assertNotIn('class="tabbar"', html)
        self.assertIn("no-store", resposta["Cache-Control"])

    def test_o_formulario_com_erro_mostra_o_erro_junto_do_campo(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertIn("Informe um endereço de email válido", html)
```

- [ ] **Step 2: Rodar e ver falhar** — `manage.py test gestao.test_vitrine` → 404 em todos.

- [ ] **Step 3: `base.html` aceita a classe do regime**

Em `templates/base.html`, na tag `<body class="…">` (linha 88), acrescentar `{% if body_class %}{{ body_class }} {% endif %}` NO INÍCIO do atributo `class`, ficando:
`<body class="{% if body_class %}{{ body_class }} {% endif %}{% if user.is_authenticated and not sem_tabbar and not shell_offline %}tem-tabbar{% endif %}"`.
(É a costura que a onda 4 vai usar para `/treino/agora/`; aqui só a vitrine a escreve.)

- [ ] **Step 4: Formulário, view e rota**

```python
# gestao/forms_vitrine.py
"""O formulário da vitrine: um campo de cada tipo que `partials/field.html`
e `partials/choice_cards.html` sabem desenhar. Não grava nada."""
from django import forms

from accounts.models import Goal

DIAS = [("0", "Segunda"), ("1", "Terça"), ("2", "Quarta"), ("3", "Quinta"), ("4", "Sexta")]


class FormularioDaVitrine(forms.Form):
    nome = forms.CharField(label="Nome", help_text="Como aparece no cabeçalho.")
    email = forms.EmailField(label="E-mail")
    peso = forms.DecimalField(label="Peso (kg)", initial="82,4", disabled=True, help_text="Campo desabilitado.")
    objetivo = forms.ChoiceField(label="Objetivo", choices=Goal.choices, widget=forms.RadioSelect)
    dias = forms.MultipleChoiceField(label="Dias de treino", choices=DIAS, widget=forms.CheckboxSelectMultiple, required=False)
    lado = forms.ChoiceField(label="Unidade", choices=[("kg", "kg"), ("lb", "lb")], widget=forms.RadioSelect)


def formulario_limpo():
    return FormularioDaVitrine(initial={"nome": "Joana", "objetivo": Goal.CUT, "lado": "kg"})


def formulario_com_erro():
    return FormularioDaVitrine(data={"nome": "", "email": "sem-arroba", "objetivo": "", "lado": "kg"})
```

Em `gestao/views.py`:

```python
from types import SimpleNamespace

from .forms_vitrine import formulario_com_erro, formulario_limpo

REGIMES = ("mesa", "ferro")


class VitrineView(PainelDeGestaoMixin, TemplateView):
    """Toda parcial real, em todos os estados, nos dois regimes.

    A vitrine é a única página que escreve `modo-foco` por parâmetro:
    `?regime=ferro`, lista fechada, decidido aqui — nunca por `:has()` nem
    por JavaScript. Fora da barra de abas, fora do shell offline, `no-store`
    como o resto do painel.
    """

    template_name = "gestao/vitrine.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        regime = self.request.GET.get("regime", "mesa")
        if regime not in REGIMES:
            regime = "mesa"
        contexto.update(
            aba="vitrine",
            sem_tabbar=True,
            regime=regime,
            body_class="modo-foco" if regime == "ferro" else "",
            form_limpo=formulario_limpo(),
            form_com_erro=formulario_com_erro(),
            google_login_enabled=True,
            legal_publicado=True,
            conquistas_novas=[
                SimpleNamespace(pk=0, emoji="", titulo="Primeira semana completa", frase="Sete dias seguidos com o plano.",
                                rotulo="Sequência", valor="7", destaque="7 dias", tipo_de_card="sequencia"),
            ],
        )
        return contexto
```

Em `gestao/urls.py`: `path("vitrine/", views.VitrineView.as_view(), name="vitrine"),`.

Template mínimo `templates/gestao/vitrine.html` (a Task 14 preenche):

```django
{% extends "gestao/base.html" %}
{% block title %}Vitrine · {{ regime|capfirst }} · NutriPlan{% endblock %}
{% block content %}
  <h1>Vitrine · {{ regime|capfirst }}</h1>
  <p class="hint">A mesma página nos dois regimes:
    <a href="{% url 'gestao:vitrine' %}">Mesa</a> ·
    <a href="{% url 'gestao:vitrine' %}?regime=ferro">Ferro</a></p>
  <section class="card">
    <div class="card__head"><h2>Campo com erro</h2></div>
    <form>{% include "partials/field.html" with field=form_com_erro.email %}</form>
  </section>
{% endblock %}
```

- [ ] **Step 5: Rodar o teste e ver passar** — `manage.py test gestao.test_vitrine gestao.tests` → OK (o `test_a_vitrine_esta_fora_da_navegacao…` prova o `never_cache` herdado do mixin).

- [ ] **Step 6: Commit**

```bash
git add gestao/forms_vitrine.py gestao/views.py gestao/urls.py gestao/test_vitrine.py templates/gestao/vitrine.html templates/base.html
git commit -m "Vitrine em gestao/vitrine/: mesma permissão do painel, regime escrito pelo servidor"
```

---

### Task 14: A vitrine completa — toda parcial, todos os estados

**Files:**
- Modify: `templates/gestao/vitrine.html`
- Modify: `gestao/test_vitrine.py` (cobertura de parciais)

**Interfaces:**
- Consumes: contexto da Task 13.
- Produces: a página que a Task 15 captura nos dois regimes.

- [ ] **Step 1: Teste que falha**

Acrescentar em `gestao/test_vitrine.py`:

```python
import os
from pathlib import Path

from django.conf import settings


class CoberturaDaVitrineTests(BaseDoPainel):
    """Toda parcial de `templates/partials/` aparece na vitrine — lido do
    disco, para a nona parcial não nascer fora dela."""

    def setUp(self):
        self.client.force_login(self.operador())
        self.template = (Path(settings.BASE_DIR) / "templates" / "gestao" / "vitrine.html").read_text(encoding="utf-8")

    def test_toda_parcial_e_incluida(self):
        pasta = Path(settings.BASE_DIR) / "templates" / "partials"
        faltando = [n for n in sorted(os.listdir(pasta)) if n.endswith(".html") and f'"partials/{n}"' not in self.template]
        self.assertEqual(faltando, [], f"parciais fora da vitrine: {faltando}")

    def test_os_componentes_de_css_estao_na_pagina(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        for classe in ('class="btn btn--primary"', "btn--ghost", "btn--quiet", "btn--perigo", "btn--sm", "btn--block",
                       'class="chip"', "chip--brand", "pill--brand", "pill--mute", 'class="tiles"', 'class="data-list"',
                       'class="empty-state"', 'class="hint"', "choice-cards", "conquista__titulo", "entrada__marca"):
            with self.subTest(classe=classe):
                self.assertIn(classe, html)

    def test_estados_do_campo(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertIn("Campo desabilitado.", html)
        self.assertIn("Informe um endereço de email válido", html)
        self.assertIn("Este campo é obrigatório", html)

    def test_conteudo_longo_e_quebrado_esta_previsto(self):
        html = self.client.get("/gestao/vitrine/").content.decode()
        self.assertIn("Supercalifragilisticexpialidocious", html)

    def test_nenhum_estilo_inline(self):
        self.assertNotIn('style="', self.template)
```

- [ ] **Step 2: Rodar e ver falhar** — parciais e classes ausentes.

- [ ] **Step 3: Escrever a vitrine**

`templates/gestao/vitrine.html`:

```django
{% extends "gestao/base.html" %}
{% comment %}
  A VITRINE: toda parcial real, em todos os estados, nos dois regimes.

  É o "/design-system" do fluxo do Claude Design (spec 15/09/2026, §9) sem
  uma segunda biblioteca: o que se vê aqui é `partials/` e as classes de
  `app.css`, as mesmas que o app usa. `gestao/test_vitrine.py` lê a pasta
  de parciais do disco e cobra que cada uma apareça — a nona parcial nasce
  dentro da vitrine ou o teste avisa. Sem `style=`, sem `:has()`; o regime
  vem do servidor (`?regime=ferro` → `body.modo-foco`).
{% endcomment %}
{% block title %}Vitrine · {{ regime|capfirst }} · NutriPlan{% endblock %}
{% block content %}
  {% include "partials/icones.html" %}
  <h1>Vitrine · {{ regime|capfirst }}</h1>
  <p class="hint">A mesma página nos dois regimes:
    <a href="{% url 'gestao:vitrine' %}">Mesa</a> ·
    <a href="{% url 'gestao:vitrine' %}?regime=ferro">Ferro</a></p>

  <section class="card">
    <div class="card__head"><h2>Marca</h2></div>
    {% include "partials/marca_de_entrada.html" %}
    <div class="chip-row chip-row--conteudo">
      <span class="chip">Sem restrições</span>
      <span class="chip chip--brand">Vegetariana</span>
      <span class="pill pill--brand">Plano ativo</span>
      <span class="pill pill--mute">Rascunho</span>
      <span class="pill pill--warm">Pesar hoje</span>
    </div>
  </section>

  <section class="card">
    <div class="card__head"><h2>Botões</h2><span class="card__subtitulo">um primário por tela; aqui é catálogo</span></div>
    <div class="acoes-empilhadas">
      <button type="button" class="btn btn--primary">Concluir série</button>
      <button type="button" class="btn btn--ghost">Cancelar</button>
      <button type="button" class="btn btn--quiet">Pulei</button>
      <button type="button" class="btn btn--perigo">Zerar a água de hoje</button>
      <button type="button" class="btn btn--ghost btn--sm">Editar</button>
      <button type="button" class="btn btn--primary btn--block">Abrir treino de hoje</button>
      <button type="button" class="btn btn--primary" disabled>Desabilitado</button>
    </div>
    {% include "partials/botao_google.html" %}
  </section>

  <section class="card">
    <div class="card__head"><h2>Campos</h2></div>
    <form method="post" action="{% url 'gestao:vitrine' %}">
      {% csrf_token %}
      {% include "partials/field.html" with field=form_limpo.nome %}
      {% include "partials/field.html" with field=form_limpo.peso %}
      {% include "partials/field.html" with field=form_limpo.lado %}
      {% include "partials/field.html" with field=form_limpo.dias %}
      {% include "partials/choice_cards.html" with field=form_limpo.objetivo colunas=2 %}
    </form>
    <h3>Com erro</h3>
    <form>
      {% include "partials/field.html" with field=form_com_erro.nome %}
      {% include "partials/field.html" with field=form_com_erro.email %}
      {% include "partials/field.html" with field=form_com_erro.objetivo %}
    </form>
  </section>

  <section class="card">
    <div class="card__head"><h2>Números</h2></div>
    <div class="tiles">
      <div class="tile"><strong class="tile__value" data-conta>87%</strong><span class="tile__label">Aderência</span><span class="tile__meta">refeições do plano</span></div>
      <div class="tile"><strong class="tile__value" data-conta>2.140</strong><span class="tile__label">kcal/dia</span><span class="tile__meta">meta: 2.200</span></div>
      <div class="tile"><strong class="tile__value" data-conta>2,6 L</strong><span class="tile__label">Água</span><span class="tile__meta">média da semana</span></div>
      <div class="tile"><strong class="tile__value" data-conta>1.234.567,89</strong><span class="tile__label">Número longo</span><span class="tile__meta">não quebra no meio</span></div>
    </div>
    <dl class="data-list">
      <div><dt>Meta</dt><dd>Emagrecer</dd></div>
      <div><dt>Rotina</dt><dd>Moderadamente ativo</dd></div>
      <div><dt>Texto comprido que precisa quebrar bonito</dt><dd>Supercalifragilisticexpialidocious — e uma frase longa o bastante para passar da linha e mostrar como o valor se comporta quando não cabe.</dd></div>
    </dl>
  </section>

  <section class="card">
    <div class="card__head"><h2>Vazio e dica</h2></div>
    <div class="empty-state">
      <p>Nenhum dia de treino cadastrado ainda.</p>
      <a class="btn btn--ghost btn--sm" href="{% url 'gestao:vitrine' %}">Cadastrar dias de treino</a>
    </div>
    <p class="hint">Uma dica curta, abaixo do bloco a que se refere.</p>
    {% include "partials/links_legais.html" %}
  </section>

  {% include "partials/_conquista.html" %}
{% endblock %}
```

Conferir se `.acoes-empilhadas` existe em `app.css` (é uma das intenções nomeadas do CLAUDE.md); se o nome for outro, usar o que existe — `grep -n "acoes-empilhadas" static/css/app.css`.

- [ ] **Step 4: Rodar os testes** — `manage.py test gestao.test_vitrine config.test_design_system config.tests.HasSelectorTests` → OK. Se `test_a1_icone_de_botao` reclamar de um botão, o botão tem texto — não deveria; ler a mensagem.

- [ ] **Step 5: Abrir nos dois regimes e fotografar**

Sessão de QA: o `sessao.py` para um usuário com a permissão (`gestor@exemplo.com` só existe em teste — criar localmente: `manage.py shell -c "from django.contrib.auth import get_user_model as g; from django.contrib.auth.models import Permission as P; u=g().objects.get(email='joao@demo.local'); u.user_permissions.add(P.objects.get(codename='ver_painel_de_gestao')); u.save()"`). Então `nav.py vitrine open http://127.0.0.1:8000/gestao/vitrine/` e `…?regime=ferro`, `screenshot` em `artifacts/claude-design/depois/vitrine-{mesa,ferro}-{320,390}.png` (quatro). Conferir: no Ferro o fundo é grafite e os campos nativos são escuros (`color-scheme`); nada rola na horizontal (`eval "document.documentElement.scrollWidth <= innerWidth"` → `true`).

- [ ] **Step 6: Commit**

```bash
git add templates/gestao/vitrine.html gestao/test_vitrine.py
git commit -m "Vitrine completa: toda parcial em todos os estados, coberta por teste que lê a pasta"
```

---

### Task 15: Fechamento — QA final, documentação à mão, plano mestre

**Files:**
- Modify: `CLAUDE.md` (seção "Design: o que já existe"), `docs/sistema-visual.md`, `docs/superpowers/plans/2026-09-14-plano-mestre.md` (T3.0/T3.1 e desvios), `docs/briefs/2026-09-15-chatgpt-claude-design/README.md` (estado final)

- [ ] **Step 1: QA final com `nav.py`**

As seis telas + a vitrine, 320 e 390, claro e escuro (26 capturas em `artifacts/claude-design/depois/`), `medir.js` para a Home nos dois temas. Nenhum console error: `nav.py <s> eval "window.__erros||0"` não existe — usar `Runtime.exceptionThrown` não está exposto; conferir a olho e por `text` que nenhuma tela mostra traceback.

- [ ] **Step 2: Suíte completa** — `manage.py test`, verde; anotar o total.

- [ ] **Step 3: `CLAUDE.md`, à mão**

Na seção "Design: o que já existe", acrescentar um parágrafo em negrito no estilo do arquivo:

"**O Ferro é escrito UMA vez e ligado por DOIS gatilhos (15/09/2026).** Os valores moram no `:root` como `--ferro-*`; `@media (prefers-color-scheme: dark)` e `body.modo-foco` só fazem `--bg: var(--ferro-bg)`. `config/test_ferro.py` compara os dois gatilhos e recusa hex neles — foi assim que a segunda paleta deixou de poder nascer. Os pilares têm nome (`--agua`, `--brasa`, `--terra`, `--chama`) e cor de pilar não entra em botão. A direção veio de `docs/briefs/design/direcao-c-mesa-e-ferro.md`, ganhou forma no claude.ai/design (semente e export em `artifacts/claude-design/`, referências em `docs/briefs/design/referencias/claude-design/`), e o que o Claude Design propôs e não entrou está em `proposto-nao-adotado.md`. A vitrine (`/gestao/vitrine/`, permissão do painel, `?regime=ferro`) renderiza toda parcial; o teste lê a pasta."

Mais os números: contagem de tokens no `:root` (antes 70 → depois N), `medir.js` `bgs`/`sizes` antes/depois na Home.

- [ ] **Step 4: `docs/sistema-visual.md`** — atualizar a tabela dos quatro eixos (cor: tokens N, valores crus) e acrescentar "Regimes" com o parágrafo do Ferro. `docs/superpowers/plans/2026-09-14-plano-mestre.md`: marcar T3.0 e T3.1 como feitas por este plano (com link), e registrar na seção de desvios: `data-theme` não entrou; hex literal nos gatilhos não; `--glow` fica para T3.3.

- [ ] **Step 5: README do handoff** — seção "Estado em <data>": o que foi feito, o que ficou (T3.2–T3.7, onda 4, aplicar `modo-foco` na execução), e o lembrete da conta de QA em produção.

- [ ] **Step 6: Commit e publicação pelo `nutriplan-missao`**

```bash
git add CLAUDE.md docs/sistema-visual.md docs/superpowers/plans/2026-09-14-plano-mestre.md docs/briefs/2026-09-15-chatgpt-claude-design/README.md
git commit -m "Registra a Mesa & Ferro: Ferro uma vez com dois gatilhos, pilares nomeados, vitrine — com os números"
```
Push (o `pre-push` roda a suíte) → deploy no Render → `/saude/` → smoke em produção nas seis telas a 390 (só GET), claro e escuro.

---

## Auto-revisão (feita ao escrever)

- **Cobertura da spec:** §4 → Tasks 1–5; §5 → Task 6; F2/F3 → Task 7; §6 → Task 8; §7 → Tasks 9–11; §8 → Task 12; §9 → Tasks 13–14; §12 gate → Task 15. §10 (fora) respeitado: nenhuma task cria `design-system/`, rota pública, `SKILL.md`, nem edita `CLAUDE.md` por prompt.
- **Nomes consistentes entre tarefas:** `resposta_da_tela`/`ficha_de_hoje` (1→4,5); `nav.py tema`/`sessao.py` (2→5,10,14,15); `montar`/`NOTA`/`sprite_como_svg` (4); `classificar`/`inventariar`/`escrever_md`/`exigir_tudo_classificado` (8→11); `_tokens` com `var()` (9→10,11); `--ferro-*`, `--agua/--brasa/--terra/--chama/--fio/--fio-forte` (10→3 DESIGN.md, 11, 15); `body_class`/`regime`/`FormularioDaVitrine` (13→14).
- **Placeholders:** nenhum "TBD"; o único conteúdo escrito à mão em execução é a coluna "motivo" de `proposto-nao-adotado.md` (Task 11) e os números do fechamento (Task 15), que só existem depois de medir.
