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
| `409` | `op_id` já usado com **outro conteúdo** — terminal, não reenvie |
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

**200** — `{"corridas": [...], "tem_mais": false}`, só as do dono, mais
recentes primeiro. **O traçado NÃO vem aqui** — ver a rota de detalhe.

| parâmetro | padrão | o quê |
|---|---|---|
| `limite` | 50 | quantas devolver. Teto de **200**; pedir mais devolve 200, não erro |
| `desde` | — | só corridas que começaram em ou depois desta data ISO 8601 |

`tem_mais` diz se existe página seguinte. Sem ele o cliente pediria para
sempre, ou pararia cedo demais.

Limite ilegível e data ilegível respondem **400**. Ignorar uma data errada
devolveria a lista inteira, e a sincronização incremental pareceria funcionar
enquanto baixa tudo toda vez — falha silenciosa é pior que recusa.

O teto entrou **antes de existir cliente publicado**, e é o único momento
barato: apertar depois um limite que não existia quebra a versão do app que
está no telefone de alguém, que é exatamente o que o prefixo `v1` existe para
impedir.

## `GET /api/v1/corridas/<op_id>/`

Por `op_id` e não por `pk`: identificador sequencial convida a varrer o
vizinho.

Devolve os mesmos campos da lista **mais o percurso**:

```json
{ "tem_traco": true, "pontos": [{"lat": -23.55, "lon": -46.63, "t": 0.0, "acumulado_m": 0.0}], "leituras_descartadas": 3 }
```

`tem_traco` é `false` e `pontos` é `[]` para corrida sincronizada sem pontos —
o que é o caso NORMAL, não erro: a PWA publicada manda só os números, por
decisão registrada em `docs/corrida-mobile-arquitetura.md` (seção 3-B).

O traçado sai só aqui, e só para o dono. Ele é o dado mais sensível do app:
diz por onde a pessoa passou e a que horas ela sai de casa.

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
| mesmo `op_id`, conteúdo **diferente** | **409** — o primeiro envio vence, nada é sobrescrito |

Reenvio **idêntico** nunca devolve erro: erro faria a fila insistir para
sempre, a mesma razão pela qual `config/csrf.py` desvia o replay offline em vez
de responder 403.

Reenvio **divergente** é outra coisa — ou o cliente tem bug, ou o
armazenamento local corrompeu, ou dois estados ganharam o mesmo identificador.
Aceitar em silêncio faria o app acreditar que sincronizou um número que o
servidor jogou fora.

```json
{
  "erro": "op_id já usado com outro conteúdo",
  "divergiram": ["distancia_m"],
  "guardado": { "op_id": "...", "distancia_m": 5030, "...": "..." }
}
```

A comparação é por VALOR, contra o registro gravado — sem coluna de
fingerprint, porque todo campo que importa já está no banco. Parcial escrita
com as chaves em outra ordem **não** é divergência.

### A regra da fila

| resposta | o que o cliente faz |
|---|---|
| `2xx` | apaga o item |
| `409` | apaga o item **e reporta** — reenviar não muda nada |
| `5xx`, falha de rede | mantém e tenta depois |

### Diferença deliberada em relação ao web

`workouts:salvar_corrida` — a rota que a PWA publicada usa — continua
respondendo **200** para reenvio divergente. Mudar um contrato já publicado sem
o cliente saber é pior que a divergência que ele esconde. A regra nova vale
para a API, que ainda não tem cliente algum.

## Tentativas de autenticação

`POST /api/v1/token/` e o login web compartilham a mesma política, em
`accounts/entrada.py`: cinco falhas por (origem + e-mail), vinte por origem,
trezentas globais, janela de quinze minutos, e o sucesso limpa o contador do
par.

**Não existe limite por e-mail sozinho**, e é de propósito: um limite assim
deixaria qualquer pessoa trancar a conta de outra só sabendo o endereço.

Quem está limitado recebe **exatamente a mesma resposta de senha errada** —
`401` com `{"erro": "e-mail ou senha incorretos"}`. Não é 429: um status
próprio diria ao atacante que ele achou o teto. O custo assumido é que um
cliente honesto não aprende a recuar sozinho.

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
