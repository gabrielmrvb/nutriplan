# A listagem nas duas lojas — textos prontos

Escrito em 22/09/2026 (Fase 3 da missão Capacitor). **Tudo aqui obedece à
mesma régua do app**: o NutriPlan não prescreve dieta — aplica fórmula
pública, calcula uma ESTIMATIVA e monta um CARDÁPIO DE EXEMPLO
(`config/test_linguagem.py` cobra isso nas telas; aqui é a mesma promessa,
para a loja não dizer o que o produto não faz). Nada de "plano alimentar",
nada de "dieta personalizada", nenhuma promessa de resultado.

---

## Nome e subtítulo

| campo | valor | limite |
|---|---|---|
| Nome (App Store e Play) | `NutriPlan` | 30 |
| Subtítulo (App Store) | `Alimentação e treino num app` | 30 |
| Descrição curta (Play) | `Estimativa de calorias, cardápio de exemplo e ficha de treino montada para a sua rotina.` | 80 |

## Descrição longa (as duas lojas; a Play aceita 4 000, a Apple 4 000)

```
Pare de adivinhar o que comer e como treinar.

O NutriPlan calcula uma estimativa de calorias e macros a partir dos seus
dados (idade, altura, peso, rotina e objetivo), monta um cardápio de exemplo
para o seu dia e uma ficha de treino para os dias em que você treina. Tudo
numa tela só, em português, sem assinatura e sem anúncio.

O DIA INTEIRO NUMA TELA
• A refeição da vez, com duas opções que fecham a mesma caloria
• Água, com um toque para cada copo
• O treino de hoje, com a próxima série já pronta para registrar
• O quanto você andou na semana: peso, treinos, corridas e aderência

TREINO QUE CABE NA SUA SEMANA
• Ficha montada pelos dias que você marcou e pelo tempo que você tem
• Academia completa, academia básica, halteres em casa ou só o peso do corpo
• Cargas e repetições anotadas série a série, com a sugestão da próxima
• "Outras formas" de cada exercício, quando o aparelho está ocupado

CORRIDA
• Registre à mão, importe um GPX/TCX do seu relógio ou traga do aparelho
• Quilômetros por semana no seu Progresso

FUNCIONA SEM INTERNET
O que você registrar sem sinal — água, refeição, série — fica guardado no
aparelho e sobe sozinho quando a rede volta.

DO SEU APARELHO (opcional)
Com a sua permissão, o app importa peso e treinos de corrida do Apple Saúde
(iPhone) ou do Health Connect (Android). Só quando você tocar em importar, e
nunca sobrescrevendo um peso que você digitou.

O QUE O NUTRIPLAN NÃO É
Não é prescrição dietética nem consulta: é uma estimativa calculada por
fórmula pública e um cardápio de exemplo. Não substitui nutricionista nem
médico. Não conta caloria gasta no treino, não promete resultado e não vende
suplemento.

Privacidade: seus dados são seus. Nada é vendido, não há rastreador de
publicidade, e dá para exportar ou apagar tudo pela própria tela.
```

## Novidades desta versão (release notes, 1.0)

```
Primeira versão do NutriPlan para celular. O mesmo app que já roda no
navegador, agora com lembretes que chegam como notificação e importação de
peso e corridas do aparelho.
```

## Palavras-chave (App Store, 100 caracteres com vírgulas)

```
dieta,calorias,macros,treino,academia,ficha,corrida,peso,água,hipertrofia,emagrecer,nutrição
```

## Categoria e classificação

| campo | App Store | Play |
|---|---|---|
| Categoria | Saúde e fitness (secundária: Alimentação e bebidas) | Saúde e fitness |
| Classificação etária | 17+ (uso: "Informações médicas/de tratamento — frequente") — o app pede idade mínima de 18 no cadastro | Classificação Indicativa: Livre; no questionário, marcar "o app trata dados de saúde" |
| Público-alvo (Play) | — | 18+ (o cadastro recusa menores de 18) |

## URLs obrigatórias

| campo | valor |
|---|---|
| Política de privacidade | `https://nutriplan-xxfn.onrender.com/privacidade/` |
| Termos de uso (EULA) | `https://nutriplan-xxfn.onrender.com/termos/` |
| Suporte | `https://nutriplan-xxfn.onrender.com/ajuda/` |
| Marketing | `https://nutriplan-xxfn.onrender.com/` |
| E-mail de contato | o de `LEGAL_CONTATO` (painel do Render) |

## Conta de demonstração para a revisão (App Store exige)

O app exige login. Na App Store Connect, em "Informações de login", entregue
uma conta de demonstração criada pelo cadastro público **com dados
fictícios** — nunca a sua conta pessoal. O demo do site
(`https://nutriplan-xxfn.onrender.com/demo/`) serve como link de apoio no
campo "Notas", mas não substitui a conta: a Apple testa o fluxo real.

Nota sugerida para a revisão:

```
O app é um único aplicativo web em WebView (Capacitor) sobre
https://nutriplan-xxfn.onrender.com. Tudo funciona com a conta de teste
acima. Os dados de saúde lidos do HealthKit (peso e treinos de corrida) são
opcionais: a tela "Hoje" tem o cartão "Apple Saúde" com o botão "Importar do
aparelho", e nada é lido antes de o usuário tocar nele e autorizar. O app não
escreve no HealthKit. Uma demonstração sem login está em
https://nutriplan-xxfn.onrender.com/demo/.
```

## Capturas

Geradas por `nativo/scripts/capturas_de_loja.py` a partir das TELAS REAIS
(conta do demo, servidor local, sem a faixa "Ambiente de demonstração"), nos
tamanhos exatos de cada loja:

| aparelho | tamanho | obrigatório? |
|---|---|---|
| iPhone 6.9" | 1290×2796 | App Store, sim |
| iPhone 6.5" | 1242×2688 | App Store, sim (compatibilidade) |
| iPad 13" | 2048×2732 | App Store, sim (o app aceita iPad) |
| Telefone Android | 1080×1920 | Play, sim (2 a 8 imagens) |
| Tablet 7" | 1200×1920 | Play, opcional |
| Tablet 10" | 1600×2560 | Play, opcional |

Cinco telas por aparelho, na ordem: **Hoje · Treino · Execução · Progresso ·
Água**. O ícone da loja (1024×1024, sem alfa e sem cantos arredondados) é
`nativo/assets/icon-only.png`. O gráfico de destaque do Play (1024×500) é o
único que não existe ainda — ver "O que falta" no relatório da missão.
