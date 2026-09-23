# O que mudou no NutriPlan

Uma seção por dia, um item por mudança que dá para ver ou sentir no app.
Escrito para quem usa; a engenharia de cada decisão mora no `BACKLOG.md` e
no `CLAUDE.md`. A tela **Ajuda › O que mudou** lê este arquivo.

## 2026-09-22

- **Trocar um exercício não tira você da ficha.** O "trocar" abre as outras formas do movimento numa folha sobre a lista, com foto e um toque para aplicar. Na execução, a última carga aparece logo acima do campo, setas ‹ › levam ao exercício anterior e ao seguinte sem voltar à ficha, e cada série pode levar uma observação ("dor no ombro") e o marcador **falhei** — que segura a sugestão de subir a carga na próxima vez, sem baixar nada.
- **A ficha do treino virou tela de pré-treino.** Cada exercício agora é um card com a foto do movimento, séries × repetições, descanso, músculo, equipamento e — o que fazia abrir um por um — a sua última carga ("42,5 kg × 6", ou "primeira vez"). O estado aparece na lista (4/4, 2/4, "Fazer") com uma barra de progresso no topo, "outras formas" virou um botão **trocar**, e um único "Começar treino" fica preso ao rodapé. "Por que essa ficha" explica a montagem sem sair da tela, e no computador a lista fica ao lado do resumo em vez de uma coluna estreita no meio.
- **O treino agora tem fim, e o descanso tem cronômetro.** "Encerrar treino" fecha o dia e abre o placar — com menos da metade das séries ele pergunta antes, e "Retomar treino" desfaz sem apagar nada. O descanso virou um relógio grande em m:ss que fica grudado no topo, com "+30 s", "pular" e som opcional, e a tela do celular não apaga enquanto ele corre. Durante o treino a barra de abas sai da frente — e com ela sumiu o pulo que fazia o botão "Concluir série" escapar do dedo ao digitar a carga.
- **Uma trava a mais contra código injetado.** O app passou a dizer ao navegador exatamente de onde ele pode carregar script, imagem e vídeo — e a recusar qualquer outra origem. Nada muda na tela; é uma rede de segurança a mais para os seus dados.
- **Formulário aberto há horas não perde mais o envio.** Enviar depois de a página ficar muito tempo aberta, ou de você ter entrado de novo em outra aba, dava "Este envio não pôde ser confirmado" e obrigava a voltar; agora o envio passa direto.
- **A sua tela não fica legível para quem pegar o aparelho depois.** As telas com peso, e-mail e histórico deixam de poder ser redesenhadas do disco pelo botão Voltar depois que você sai da conta.
- **O treino em andamento não some mais.** Se o seu programa for remontado no meio do dia — por você, em outra aba, ou porque mudou alguma resposta —, a ficha que você estava usando continua abrindo (como histórico, dizendo quantas séries você registrou hoje) e o pedido de regenerar vale a partir de amanhã. Nenhuma série registrada se perde.
- **A política explica os dados de saúde do aparelho.** Uma seção nova diz o que o app lê do Apple Saúde e do Health Connect (só peso e corridas, só quando você pede), e o que ele nunca faz: escrever, ler em segundo plano ou compartilhar com alguém.
- **O app do celular tem lembretes e lê o aparelho.** No app instalado, os lembretes das refeições chegam como notificação do sistema, e um cartão novo traz as suas corridas e pesagens do Apple Saúde (iPhone) ou do Health Connect (Android) — só o que você autorizar, sem sobrescrever peso que você digitou.
- **Entrar no app do celular é com um toque.** Continuar com Google (e Continuar com Apple, no iPhone) pelo próprio aparelho, sem abrir o navegador.
- **Sem rede é "sem rede".** A tela que aparece sem conexão dizia "o servidor está acordando" quando o aparelho achava que estava conectado sem estar; agora ela percebe pela resposta e diz a verdade.
- **Um envio recusado mostra a página, não um código.** Quem enviava água, série, refeição ou corrida com a sessão renovada em outra aba via um texto técnico cru; agora vê "Este envio não pôde ser confirmado" com "Voltar ao formulário" — e o digitado volta.
- **Continuar sempre à vista.** Na etapa 2 do cadastro, com um ou dois dias de treino — ou nenhum — o botão de continuar não aparecia. Agora aparece sempre.
- **"Você faz musculação?"** Quem só corre, nada ou faz outro esporte responde "não" e não precisa inventar dias, experiência e equipamento de academia; a aba Treino deixa de cobrar os dias e mostra as corridas.
- **O erro aponta o campo.** Quando um envio é recusado, a tela rola até o campo, marca-o e escreve o motivo embaixo dele — o peso da Home e do Progresso incluídos.
- **Nada digitado se perde.** Os formulários longos (cadastro, corrida, reportar) guardam um rascunho no aparelho: se a página expirar ou a sessão cair no meio, o que você digitou volta sozinho.
- **O primeiro toque conta.** Um toque dado enquanto a tela ainda estava entrando era perdido; agora ele é entregue assim que a tela termina de entrar.
- **"Comi outra coisa" sugere de novo.** A lista de alimentos ao digitar voltou a mostrar os nomes do catálogo.
- **A ofensiva começa no dia em que a conta nasceu.** Nada de "3 dias" no primeiro dia nem "401 de 3" nas Conquistas; a Home e as Conquistas contam a mesma coisa. Quando a sequência zera, a Home diz o que faltou ontem.
- **Aderência sem nota de reprovação no primeiro dia.** Hoje só conta as refeições cujo horário já passou ("1/2 até agora"); a porcentagem é dos dias fechados. No dia do cadastro, as refeições de antes de você chegar não contam.
- **"Ficou para trás".** Uma refeição vencida há mais de uma hora e meia deixa de ser chamada de "agora" — continua sendo a próxima coisa a registrar.
- **Sua área principal age.** O cartão da área que você escolheu traz o botão do dia: começar o treino de hoje, registrar a corrida, registrar o peso.
- **O aviso de conquista não cobre o botão.** Na execução, "Conquista desbloqueada" aparece logo abaixo de "Concluir série", e não por cima dele.
- **Ficha de iniciante com o peso do corpo começa do começo.** Sem paralelas, parada de mão ou flexão arqueiro na primeira semana: cada movimento entra na versão que dá para fazer, e a escada mostra o caminho.
- **Placar para quem treina sem anilha.** O número grande do fim do treino é o de repetições quando não houve carga — e o kg ganhou ponto de milhar. A primeira série já vem com as repetições no piso da faixa.
- **Editar treinos diz o que valeu.** "A ficha foi remontada", "há série hoje, então a ficha muda amanhã" ou "ajustada à mão, não é remontada".
- **Corrida no Progresso e na Ajuda.** Quilômetros por semana para quem corre, "Corridas" na lista do que a exclusão apaga, e uma pergunta na Ajuda para quem só corre.
- **A sessão não cai no meio do uso.** Quem usa o app continua logado; só quem some por duas semanas precisa entrar de novo.
- **Página inicial mais leve.** As três imagens da vitrine pesam um quarto do que pesavam — no 3G a diferença é de segundos.
- **A divisão do treino em português simples.** "Peito e tríceps · Costas e bíceps · Pernas e ombros" no lugar de siglas, e o resumo do cadastro repete o que você escolheu com as mesmas palavras.
- **O e-mail de boas-vindas começa pelo cadastro.** O passo 1 é terminar as três etapas — a tela Hoje e a ficha vêm depois delas. E a ajuda dos avisos no aparelho diz onde o cartão Lembretes está (no fim da tela Hoje).

## 2026-09-21

- **Glúteo é grupo próprio.** A elevação pélvica e as pontes de glúteo deixam de contar como "posterior": o glúteo aparece com o próprio nome na leitura do exercício e nas "outras formas", e a sua ficha continua a mesma.
- **Avisos por e-mail.** Boas-vindas ao criar a conta, um aviso quando você passa 5 dias sem registrar treino e o resumo da semana toda segunda-feira (treinos, séries, peso e água). Você escolhe quais recebe e a que horas em **Perfil › Avisos**, e todo e-mail tem link para parar de receber.
- **Lembrete de refeição respeita a preferência.** Em Perfil › Avisos dá para desligar só o push de refeição, sem desinscrever o aparelho.
- **Ajuda.** Perguntas frequentes escritas a partir do que o app faz, "Reportar um problema" com a tela e a versão já preenchidas, e esta lista.
- **Compartilhar o placar.** Ao fechar o treino, "Compartilhar" gera uma imagem com a sessão, as séries, o volume e o tempo — sem peso corporal — para enviar ou salvar.

## 2026-09-20

- **Página inicial para quem não tem conta.** A raiz mostra o que o app é, com a demonstração pública; entrar continua a um toque.
- **Treino só com o peso do corpo.** Quem escolhe "só o peso do corpo" recebe uma ficha completa: 34 exercícios novos, com progressão.
- **Home mais curta.** As refeições fora da vez ficam fechadas e abrem num toque; a refeição da vez continua aberta.
- **Teclado sem esconder botão.** Com o teclado aberto, a barra de baixo sai do caminho.
- **Ofensiva mais justa.** A sequência passa a contar 2 de 3 do dia (refeições, treino, água) e diz o que faltou.
- **Login mais rápido.** A senha continua tão segura, e o entrar deixou de pagar quase dois segundos.

## 2026-09-17

- **Ficha de academia de verdade.** 63 exercícios ativos com demonstração conferida; "Peito e tríceps" com 7 exercícios e 24–26 séries no Padrão.
- **A semana continua de onde parou.** O ciclo A·B·C não recomeça toda segunda: peito, costas e pernas passam a cair o mesmo número de vezes.
- **Carga que se adapta.** O app sugere subir, manter ou retomar a carga pelo que você registrou — e nunca baixa o número sozinho. Na última série do composto, "1 a 2 sobrando, mesmo passando de 10".
- **Uma ficha por letra, e "outras formas".** Você escolhe COMO fazer cada movimento (a máquina ocupada tem substituto do mesmo padrão) e o equipamento que tem no perfil.
- **Direção visual NERVURA.** Preto esverdeado de academia, verde-neon só para agir, laranja só para a carga, a régua diagonal e a ponta de folha.

## 2026-09-16

- **Lembrete de refeição no aparelho.** Ative em Perfil › Lembretes: 20 minutos antes de cada refeição do seu plano.
- **Conquista na hora.** A primeira série do dia já avalia as conquistas e avisa na mesma tela.
- **Onboarding em três etapas.** Sobre você · Seu objetivo e rotina · Sua personalização.
