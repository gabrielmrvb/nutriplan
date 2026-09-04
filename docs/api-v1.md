# API v1 — o contrato do cliente que não é navegador

Fase 1 da frente mobile. Seis rotas: o mínimo que prova que um cliente de fora
autentica, se identifica, sincroniza uma corrida sem duplicar, consulta o que
salvou, e nunca alcança a corrida de outra pessoa.

Não cobre o NutriPlan inteiro, de propósito. O web continua exatamente como
estava — sessão, cookie, CSRF e template — e `workouts:salvar_corrida` continua
existindo porque a PWA em produção posta nela.

## Autenticação

`Authorization: Bearer <token>` em todas as rotas privadas.

**A API não olha a sessão.** É o que torna `csrf_exempt` correto em vez de
perigoso: CSRF existe porque o navegador anexa o cookie sozinho, e um endpoint
que não lê cookie não tem o que ser forjado. Um cookie de sessão válido recebe
**401** aqui — há teste e sabotagem exigindo isso.

O token é sorteado com 256 bits e guardado como `sha256`. O banco não sabe o
valor: um vazamento não entrega sessões vivas. Validade de **90 dias**;
revogação vale na requisição seguinte.

## Erros

Todo erro sai no mesmo formato, e a mensagem descreve o que o cliente fez —
nunca o que o servidor tem dentro.

```json
{ "erro": "é preciso um token válido" }
```

| status | quando |
|---|---|
| `400` | JSON inválido, campo faltando, número impossível, ponto malformado |
| `401` | sem token, token vencido, token revogado, senha errada |
| `404` | corrida que não existe **ou não é sua** |
| `405` | método que a rota não aceita |
| `413` | corpo acima de 1 MB |

`404` e não `403` no detalhe: `403` confirmaria que a corrida existe.

---

## `POST /api/v1/token/`

Troca e-mail e senha por um token. Não exige token.

```json
{ "email": "pessoa@exemplo.com", "senha": "..." }
```

**200**

```json
{
  "token": "...",
  "expira_em": "2026-12-03T10:00:00+00:00",
  "usuario": { "id": 1, "email": "...", "nome": "", "sexo": "M", "altura_cm": 178 }
}
```

**401** — `{"erro": "e-mail ou senha incorretos"}`. A recusa é **byte a byte
igual** exista o e-mail ou não: duas mensagens diferentes transformariam o
endpoint num oráculo de cadastro.

## `DELETE /api/v1/token/`

Revoga o token usado no cabeçalho. **204** sem corpo. Vale na requisição
seguinte.

## `GET /api/v1/eu/`

**200** — o mesmo objeto `usuario` de cima. Enumera o que SAI: campo novo no
model não vaza sozinho para a API.

---

## `POST /api/v1/corridas/`

Cria **ou reconhece** uma corrida já sincronizada. É a rota que sustenta o
offline.

Dois formatos, e o servidor prefere o primeiro:

**Com pontos — o servidor é a autoridade**

```json
{
  "op_id": "gerado-no-aparelho",
  "comecou_em": "2026-09-04T07:00:00+00:00",
  "terminou_em": "2026-09-04T07:30:00+00:00",
  "duracao_s": 1782,
  "pontos": [{ "lat": -23.55, "lon": -46.63, "t": 0, "accuracy": 5 }],
  "teve_lacuna": false
}
```

`distancia_m` enviado junto é **ignorado**. O servidor calcula com
`workouts/corrida.py` — haversine, corte de precisão acima de 30 m, corte de
teleporte acima de 12,5 m/s, corte de ruído abaixo de 1,5 m — e devolve
`distancia_do_cliente_m` para o app poder comparar.

**Os pontos NÃO são guardados.** Entram, viram número, e morrem na função que
calcula. É a decisão de privacidade que o model já tinha: guardar coordenada é
guardar onde a pessoa mora e a que horas ela sai de casa.

**Sem pontos — o resumo do cliente vale**

```json
{
  "op_id": "...", "comecou_em": "...", "terminou_em": "...",
  "distancia_m": 5030, "duracao_s": 1782,
  "parciais": [{ "km": 1, "segundos": 354.0 }]
}
```

É o contrato que a PWA já usa, e ele continua aceito.

**201** quando criou · **200** quando já existia.

## `GET /api/v1/corridas/`

**200** — `{"corridas": [...]}`, só as do dono, mais recentes primeiro.

## `GET /api/v1/corridas/<op_id>/`

Por `op_id` e não por `pk`: identificador sequencial convida a varrer o
vizinho.

---

## Idempotência

A chave é `(dono, op_id)`, com `UniqueConstraint` no banco. O aparelho gera o
`op_id` **antes** de enviar.

| situação | o que acontece |
|---|---|
| primeira sincronização | **201**, corrida criada |
| reenvio depois de resposta perdida | **200**, a mesma corrida de volta |
| reenvio depois de timeout | **200** |
| app fechado durante o envio | **200** no próximo envio |
| dois aparelhos, mesmo `op_id` sorteado | duas corridas — a chave é por PESSOA |
| conflito de conteúdo | **o primeiro envio vence**; o segundo devolve o que está gravado, sem sobrescrever |

O reenvio nunca devolve erro. Erro faria a fila insistir para sempre — a mesma
razão pela qual `config/csrf.py` desvia o replay offline em vez de responder
403.

**Limitação conhecida:** um reenvio com conteúdo diferente é aceito em silêncio
e o conteúdo novo é descartado. Não há campo que registre a divergência, e
acrescentar um exigiria migração sem caso de uso provado.

## Offline

A API foi desenhada para o app funcionar sem rede a corrida inteira e
sincronizar depois. Nada nesta fase é armazenamento no aparelho — isso é da
Fase 2.

O que o desenho garante: o `op_id` nasce no aparelho, o envio é uma operação
única no fim, o reenvio é seguro, e a resposta perdida é indistinguível do
envio perdido do ponto de vista do cliente — que por isso pode sempre reenviar.

## Versionamento

`v1` no caminho, e só isso. Um app publicado não atualiza junto com o servidor:
existe gente com a versão de três meses atrás no telefone. O prefixo permite
`v2` nascer ao lado sem tocar em `v1`. Sem negociação por cabeçalho, sem versão
por recurso — o custo apareceria na primeira dúvida e o ganho exigiria muitos
clientes independentes. Há um, e ele nem nasceu.
