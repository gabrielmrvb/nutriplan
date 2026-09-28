# A voz do NutriPlan

Uma página. Vale para todo texto que a pessoa lê: tela, botão, estado vazio,
erro, e-mail, notificação. A régua é `config/test_voz.py`: ela varre o texto
literal de `templates/` contra a lista de proibidos abaixo.

## Tom

- **Um colega que treina e cozinha, não um fiscal.** Diz o que fazer agora e
  por quê, em uma frase. Não comemora demais e não cobra.
- **Fato antes de adjetivo.** "3 de 5 refeições" em vez de "ótimo dia!".
- **O próximo passo sempre.** Estado vazio diz como gerar o dado ("Registre a
  primeira corrida"), nunca só que ele não existe.
- **Honesto sobre o que o app sabe.** Dia sem registro é "sem registro", não
  "sem água". Número estimado leva "~" ou "estimativa".

## Pessoa

- **Você**, sempre. Nunca "o usuário", "o cliente", "tu", "vc".
- **O app** fala de si na terceira pessoa ("o NutriPlan calcula"), sem "nós"
  que prometa gente do outro lado.
- Verbo no imperativo para ação: "Registrar corrida", "Ver o cardápio de hoje".

## Proibidos

| categoria | não use | use |
|---|---|---|
| punição | "você falhou", "o que faltou", "fracasso", "preguiça", "sem desculpa", "desistiu", "vergonha" | o que fecha o dia; "recomeça hoje" |
| contrato | "combinado" (dia combinado, o combinado) | "dia de treino", "o que você marcou" |
| jargão de software | "usuário", "login"/"logout", "view", "requisição", "endpoint", "middleware", "token" | "você"/"pessoa", "entrar"/"sair" |
| jargão de cálculo solto | "TDEE", "TMB", "RIR", "1RM" sozinhos | o termo em português primeiro, a sigla entre parênteses: "Gasto em repouso (TMB)" |
| alimentação como prescrição | "plano" e "dieta" para a comida (régua de `config/test_linguagem.py`) | "estimativa", "cardápio de exemplo" |

**Exceções declaradas.** `templates/legal/` (Termos e Privacidade citam lei e
fornecedores com o vocabulário deles), `templates/demo/sobre.html` (a página
que explica ao avaliador como o demo protege os dados, e por isso fala de
requisição e middleware) e o painel de gestão (`templates/analytics/`,
`templates/gestao/`, a ferramenta de quem opera). "Falha" continua livre no
treino: "até a falha" e "falhei nesta série" são o termo do movimento, não
um julgamento.

## Números

`tabular-nums`, vírgula decimal ("62,5"), ponto de milhar ("2.340"). Veja o
`CLAUDE.md` para a régua de formatação.
