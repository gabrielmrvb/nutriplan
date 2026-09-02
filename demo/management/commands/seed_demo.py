"""Cria (ou refaz) o Carlos Silva, o usuário fictício do modo demo.

Idempotente: pode rodar quantas vezes quiser. Roda no build do Render, junto
dos outros seeds, então o demo sobe pronto a cada deploy.

Por que um usuário DE VERDADE no banco, e não um objeto de mentira em memória:
as telas do app leem `request.user.profile`, `user.plans`, `user.training_days`
e uma dúzia de relações. Fingir tudo isso exigiria um dublê para cada modelo, e
o dublê é o que diverge do app real na primeira mudança de schema. Um usuário
comum, montado pelo MESMO motor que monta o seu, é o que garante que o demo
mostra o app que existe.

O que protege os dados reais não é este comando — é o middleware, que recusa
qualquer método que escreva antes de chegar na view.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import (
    ClassificacaoDeConta,
    ONBOARDING_DONE,
    ONBOARDING_LAST_STEP,
    ActivityLevel,
    Goal,
    MealStyle,
    Profile,
    Sex,
    SplitPreference,
    TrainingDay,
    WeightEntry,
)
from demo.middleware import DEMO_EMAIL, DEMO_ONBOARDING_EMAIL
from plans import rodizio as plan_rodizio
from plans import services as plan_services
from plans.models import HydrationLog, MealLog, MealStatus
from workouts import services as workout_services
from workouts.models import Equipment, ExerciseLog, MuscleGroup, TrainingPlan

IDADE = 28
PESO_KG = Decimal("78.0")
ALTURA_CM = 178

DIAS_DE_TREINO = ((0, time(19, 0)), (2, time(19, 0)), (4, time(19, 0)))
DURACAO_MIN = 60

SEMANAS_DE_PESO = 12
GANHO_POR_SEMANA = Decimal("0.25")

#: Quantas semanas de carga registrada, em cada exercicio de cada dia.
SEMANAS_DE_CARGA = 4

# ---------------------------------------------------------------- a Ana
#
# A persona da estreia. Os numeros sao deliberadamente diferentes dos do
# Carlos — outro sexo, outra altura, outro objetivo — porque e assim que se ve,
# olhando a tela, que o wizard esta lendo o perfil dela e nao o dele.
ANA_IDADE = 27
ANA_ALTURA_CM = 165
ANA_DIAS_DE_TREINO = ((1, time(7, 30)), (3, time(7, 30)))
ANA_DURACAO_MIN = 45

#: Quantos dias de historico de refeicao. A tela de metricas anuncia "os
#: ultimos 14 dias" — com menos que isso ela desenha um grafico de uma barra.
DIAS_DE_HISTORICO = 13

ZERO = Decimal("0")

#: A frase guardada quando a refeicao saiu do plano. E o campo que a tela de
#: "comi outra coisa" preenche, e aqui ele mostra que o campo existe.
NOTA_FORA_DO_PLANO = {"off_plan": "Jantei fora, comi um prato feito"}

#: Carga de partida por grupo muscular, em quilos, para um homem de 78 kg com
#: alguns meses de treino.
#:
#: A primeira versao derivava a carga so da faixa de repeticoes, e o resultado
#: foi remada curvada e puxada na polia com o MESMO numero em todos os nove
#: exercicios do dia. Numero repetido nao le como dado, le como preenchimento —
#: e o demo existe justamente para parecer usado.
#:
#: Nao sao recomendacoes: sao ordens de grandeza plausiveis, para a tela ter
#: numero em vez de traco.
CARGA_BASE = {
    MuscleGroup.QUADS: 80,
    MuscleGroup.HAMSTRINGS: 60,
    MuscleGroup.BACK: 55,
    MuscleGroup.CHEST: 52,
    MuscleGroup.CALVES: 45,
    MuscleGroup.TRAPS: 26,
    MuscleGroup.SHOULDERS: 22,
    MuscleGroup.TRICEPS: 18,
    MuscleGroup.BICEPS: 15,
    MuscleGroup.FOREARMS: 12,
    MuscleGroup.CORE: 0,
}

#: Isolado carrega menos que composto no mesmo musculo.
FATOR_ISOLADO = Decimal("0.45")

#: A menor carga que aparece. Halter de 3 kg existe, mas rosca alternada com
#: 3 kg num homem de 78 quilos le como erro, e nao como treino leve.
#:
#: Cinco e nao seis: o piso tambem precisa ser um peso que a academia monta, e
#: 6 kg nao e multiplo de 2,5. Foi o teste do degrau que pegou — o piso era
#: aplicado DEPOIS do arredondamento e desfazia o proprio arredondamento.
CARGA_MINIMA = Decimal("5")

#: Academia tem anilha de 2,5 em 2,5. "26,22 kg" nao e uma carga que alguem
#: consiga montar — e o tipo de numero que entrega que a tela foi semeada.
DEGRAU = Decimal("2.5")


def _arredondar(peso: Decimal) -> Decimal:
    """O peso no degrau mais proximo que a academia consegue montar."""
    return (peso / DEGRAU).quantize(Decimal("1")) * DEGRAU

#: O equipamento muda a ordem de grandeza, e ignorar isso produz numero
#: visivelmente errado: sem este fator o seed escrevia "Flexao de braco,
#: 51,60 kg" — flexao e peso do corpo, nao tem carga externa — e "Remada
#: unilateral com halter, 62,50 kg", que e um halter que nao existe na maioria
#: das academias.
#:
#: Halteres carregam por LADO, entao um movimento de halter registra perto de
#: metade do equivalente em barra. Peso do corpo nao registra carga nenhuma.
FATOR_EQUIPAMENTO = {
    Equipment.BARBELL: Decimal("1"),
    Equipment.MACHINE: Decimal("1"),
    Equipment.CABLE: Decimal("0.9"),
    Equipment.DUMBBELL: Decimal("0.45"),
    Equipment.BODYWEIGHT: Decimal("0"),
}


class Command(BaseCommand):
    help = "Cria o usuario ficticio do modo demo (Carlos Silva)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--somente-o-dia",
            action="store_true",
            dest="somente_o_dia",
            help=(
                "Refaz o DIA: refeicoes, agua e cargas. E o caminho que o "
                "middleware chama quando a data vira, e ele evita remontar "
                "plano e ficha, que e a parte cara."
            ),
        )
        parser.add_argument(
            "--refazer",
            action="store_true",
            help="Apaga o usuario de demonstracao e o cria de novo.",
        )

    def _log(self, mensagem):
        if self.verbosity:
            self.stdout.write(mensagem)

    @transaction.atomic
    def handle(self, *args, **options):
        self.verbosity = options.get("verbosity", 1)
        User = get_user_model()

        if options.get("somente_o_dia"):
            user = User.objects.filter(email=DEMO_EMAIL).first()
            plano = user.plans.filter(is_active=True).first() if user else None
            if plano is None:
                self._log("Nada a refazer: o demo ainda nao foi semeado.")
                return
            self._preencher_o_dia(user, plano)

            # As cargas tambem sao ancoradas em "hoje", e ficavam de fora.
            #
            # `_preencher_cargas` escreve a semana 0 na data de hoje e as tres
            # anteriores para tras. Rodando so no seed completo, um dia depois
            # do deploy a semana 0 virava ontem: a tela de treino perdia a
            # linha "ultimo treino" do dia, e `resumo_da_sessao` — que filtra
            # `ExerciseLog` por `date=hoje` — passava a devolver vazio, o que
            # deixava a exportacao TCX do demo sem sessao nenhuma para exportar.
            #
            # Nao ha regra nova aqui: e a MESMA funcao que o seed completo
            # chama, com a mesma progressao. O que muda e so quando ela roda.
            ficha = user.training_plans.filter(is_active=True).first()
            if ficha is not None:
                self._preencher_cargas(user, ficha)

            self._log(self.style.SUCCESS("Dia do demo refeito."))
            return

        if options["refazer"]:
            apagados, _ = User.objects.filter(
                email__in=(DEMO_EMAIL, DEMO_ONBOARDING_EMAIL)
            ).delete()
            if apagados:
                self._log("Usuarios de demonstracao removidos.")

        user, criado = User.objects.get_or_create(
            email=DEMO_EMAIL, defaults={"first_name": "Carlos"}
        )
        if criado:
            # Senha inutilizavel: a conta existe para ser LIDA pelo middleware,
            # e nao para alguem entrar nela pela tela de login.
            user.set_unusable_password()
            user.first_name = "Carlos"
            user.save()

        # A classificacao vai FORA do `if criado`: o seed e dono destas duas
        # contas, entao ele declara o que elas sao toda vez que roda — e uma
        # conta que ja existia antes do campo existir precisa ser marcada
        # tambem. Isto nao e adivinhacao: as demais contas continuam
        # `nao_classificada`, porque sobre elas o banco nao sabe nada.
        if user.classificacao != ClassificacaoDeConta.DEMO:
            user.classificacao = ClassificacaoDeConta.DEMO
            user.save(update_fields=["classificacao"])

        hoje = timezone.localdate()
        # A data de nascimento acompanha o ano corrente: fixa, o demo
        # envelheceria sozinho e a capa passaria a dizer 29, 30, 31 anos.
        nascimento = date(hoje.year - IDADE, 5, 14)

        Profile.objects.update_or_create(
            user=user,
            defaults={
                "sex": Sex.MALE,
                "birth_date": nascimento,
                "height_cm": ALTURA_CM,
                "activity_level": ActivityLevel.LIGHT,
                "goal": Goal.BULK,
                "split_preference": SplitPreference.DOIS,
                "meal_style": MealStyle.QUICK,
                "wake_time": time(6, 30),
                "sleep_time": time(23, 0),
                "onboarding_step": ONBOARDING_DONE,
                "onboarding_completed_at": timezone.now(),
            },
        )

        # Doze semanas subindo devagar, que e o que hipertrofia parece de
        # verdade. Sem isso o historico abre vazio e a tela mais visual do app
        # nao mostra nada.
        WeightEntry.objects.filter(user=user).delete()
        for semana in range(SEMANAS_DE_PESO, -1, -1):
            WeightEntry.objects.create(
                user=user,
                date=hoje - timedelta(weeks=semana),
                weight_kg=(PESO_KG - GANHO_POR_SEMANA * semana).quantize(
                    Decimal("0.01")
                ),
            )

        TrainingDay.objects.filter(user=user).delete()
        for dia, hora in DIAS_DE_TREINO:
            TrainingDay.objects.create(
                user=user, weekday=dia, start_time=hora, duration_min=DURACAO_MIN
            )

        # Daqui para baixo e o motor de verdade: as mesmas funcoes que montam
        # o plano de qualquer pessoa. E isso que faz o demo mostrar o app.
        #
        # `sync_active_routine` e nao `create_routine`, e a diferenca custou
        # caro: `create_routine` cria um TrainingPlan NOVO toda vez que roda, e
        # este comando roda em TODO deploy. O demo tinha acumulado dezenas de
        # planos — lixo que crescia sozinho e que poluia qualquer comparacao de
        # integridade do banco. O lado da nutricao ja usava `sync_active_plan`,
        # que so refaz quando a entrada muda; o do treino nao tinha o par.
        plano, _ = plan_services.sync_active_plan(user)
        ficha, _ = workout_services.sync_active_routine(user)
        self._limpar_fichas_orfas(user, ficha)

        self._preencher_o_dia(user, plano)
        self._preencher_cargas(user, ficha)
        self._semear_a_estreia()

        self._log(
            self.style.SUCCESS(
                "Demo pronto: Carlos Silva, "
                + str(ALTURA_CM)
                + " cm, "
                + str(plano.target_kcal)
                + " kcal, divisao "
                + ficha.get_split_display()
                + "."
            )
        )

    def _semear_a_estreia(self):
        """A persona que fica parada no onboarding, para o demo do primeiro uso.

        POR QUE UM SEGUNDO USUARIO
        O Carlos terminou o wizard, e quem terminou nao consegue ve-lo como
        quem chega: `OnboardingStepMixin` liga `is_editing`, e os passos passam
        a mostrar o fluxo de EDICAO — "Salvar" no lugar de "Continuar", sem a
        barra de progresso do jeito que ela aparece na estreia. Mostrar isso
        como se fosse o primeiro uso seria mostrar uma tela que o primeiro uso
        nao tem.

        POR QUE `onboarding_step` NO ULTIMO PASSO, E NAO NO PRIMEIRO
        A guarda de `OnboardingStepMixin` so abre o passo N se o progresso
        salvo ja chegou nele — e ela esta certa: sem isso o banco aceita perfil
        pela metade que o calculo de dieta nao sabe ler. Entao para os cinco
        passos serem VISITAVEIS por GET, o progresso precisa estar no ultimo.

        Ela continua incompleta: `ONBOARDING_DONE` e 6, e ela para em 5. E como
        o demo recusa todo POST, ela nunca avanca — o estado e estavel sem
        precisar de nenhuma trava propria.

        POR QUE UM PERFIL PREENCHIDO
        Campo vazio nao mostra componente: o seletor de objetivo sem escolha, o
        de divisao sem escolha e os dias de treino em branco deixariam tres dos
        cinco passos sem nada para avaliar. Os valores sao ficticios e
        diferentes dos do Carlos, de proposito.
        """
        User = get_user_model()
        hoje = timezone.localdate()

        user, criado = User.objects.get_or_create(
            email=DEMO_ONBOARDING_EMAIL, defaults={"first_name": "Ana"}
        )
        if criado:
            # Mesma razao da conta do Carlos: existe para ser LIDA pelo
            # middleware, nunca para alguem entrar nela pela tela de login.
            user.set_unusable_password()
            user.first_name = "Ana"
            user.save()

        # A classificacao vai FORA do `if criado`: o seed e dono destas duas
        # contas, entao ele declara o que elas sao toda vez que roda — e uma
        # conta que ja existia antes do campo existir precisa ser marcada
        # tambem. Isto nao e adivinhacao: as demais contas continuam
        # `nao_classificada`, porque sobre elas o banco nao sabe nada.
        if user.classificacao != ClassificacaoDeConta.DEMO:
            user.classificacao = ClassificacaoDeConta.DEMO
            user.save(update_fields=["classificacao"])

        Profile.objects.update_or_create(
            user=user,
            defaults={
                "sex": Sex.FEMALE,
                "birth_date": date(hoje.year - ANA_IDADE, 3, 22),
                "height_cm": ANA_ALTURA_CM,
                "activity_level": ActivityLevel.ACTIVE,
                "goal": Goal.CUT,
                "split_preference": SplitPreference.DOIS,
                "meal_style": MealStyle.QUICK,
                "wake_time": time(6, 0),
                "sleep_time": time(22, 30),
                # Ultimo passo, e nao ONBOARDING_DONE: incompleta de verdade.
                "onboarding_step": ONBOARDING_LAST_STEP,
                "onboarding_completed_at": None,
            },
        )

        # O passo 3 le os dias de treino do usuario. Sem eles o formulario abre
        # com todos os dias desmarcados, e o passo perde o que ele tem para
        # mostrar.
        TrainingDay.objects.filter(user=user).delete()
        for dia, hora in ANA_DIAS_DE_TREINO:
            TrainingDay.objects.create(
                user=user, weekday=dia, start_time=hora, duration_min=ANA_DURACAO_MIN
            )

        # E so. Nada de plano, ficha, peso ou refeicao: quem esta no meio do
        # wizard ainda nao tem nenhuma dessas coisas, e inventa-las aqui seria
        # justamente a "versao inventada do onboarding" que o demo nao quer.
        self._log("Estreia pronta: Ana, parada no passo " + str(ONBOARDING_LAST_STEP) + ".")

    def _limpar_fichas_orfas(self, user, ficha_ativa):
        """Apaga as fichas que os deploys anteriores deixaram para tras.

        Existe por causa do defeito que `sync_active_routine` acabou de fechar:
        cada deploy criava um TrainingPlan novo para o demo, e eles se
        acumularam. Sem esta limpeza, a correcao pararia o crescimento mas
        deixaria o lixo ja criado.

        A guarda do e-mail nao e decoracao. Este metodo apaga plano de treino,
        e a unica coisa que separa "limpar o demo" de "apagar o historico de
        alguem" e a linha abaixo. Ela fica aqui, e nao na chamada, porque quem
        chama pode mudar.
        """
        if user.email not in (DEMO_EMAIL, DEMO_ONBOARDING_EMAIL):
            raise CommandError(
                "_limpar_fichas_orfas so roda para os usuarios de demonstracao."
            )

        antigas = TrainingPlan.objects.filter(user=user).exclude(pk=ficha_ativa.pk)
        quantas = antigas.count()
        if quantas:
            antigas.delete()
            self._log("%d ficha(s) de deploys anteriores removida(s)." % quantas)

    def _preencher_o_dia(self, user, plano):
        """Duas semanas de historico, e o dia de hoje pela metade.

        HOJE pela metade e deliberado: dia em branco esconde a barra de
        progresso e o cartao de refeicao concluida; dia cheio esconde o botao
        de marcar. Metade mostra os dois estados.

        E os treze dias ANTERIORES existem por causa da tela de metricas. Ela
        anuncia "os ultimos 14 dias" e desenha uma barra por dia; com so o dia
        de hoje registrado ela mostrava uma barra e a media de 966 kcal/dia
        contra a meta de 2765 — numero verdadeiro e conclusao errada, que e o
        pior tipo de tela para alguem analisar.

        Nem todo dia sai perfeito, e isso tambem e proposital: 100% de
        aderencia em duas semanas nao e o que a tela precisa provar que sabe
        desenhar. Um dia com refeicao pulada e outro com "comi outra coisa"
        colocam os tres estados na tela.
        """
        hoje = timezone.localdate()
        horarios = list(plano.slots.order_by("time"))
        if not horarios:
            return

        MealLog.objects.filter(
            user=user, date__gte=hoje - timedelta(days=DIAS_DE_HISTORICO)
        ).delete()
        HydrationLog.objects.filter(
            user=user, date__gte=hoje - timedelta(days=DIAS_DE_HISTORICO)
        ).delete()

        registros = []
        for atraso in range(DIAS_DE_HISTORICO, -1, -1):
            dia = hoje - timedelta(days=atraso)

            # Hoje para na metade: e meia manha, e o resto do dia ainda vai
            # acontecer.
            do_dia = (
                horarios[: max(len(horarios) // 2, 1)] if atraso == 0 else horarios
            )

            for indice, slot in enumerate(do_dia):
                # A opção que o rodízio teria projetado NAQUELE dia, e não a
                # primeira do repertório. O histórico do demo passa a contar a
                # mesma história que a regra contaria — sem isso, a semeadura
                # mostraria a mesma receita em quinze dias seguidos e o demo
                # exibiria justamente o problema que o cardápio V2 resolve.
                projetadas = plan_rodizio.opcoes_do_dia(slot, user.pk, dia)
                opcao = projetadas[0] if projetadas else None
                if opcao is None:
                    continue

                # Um deslize por semana, sempre no mesmo lugar para a semeadura
                # ser reproduzivel: um lanche pulado e um jantar fora do plano.
                status = MealStatus.DONE
                if atraso and atraso % 7 == 3 and indice == 2:
                    status = MealStatus.SKIPPED
                elif atraso and atraso % 7 == 5 and indice == len(do_dia) - 1:
                    status = MealStatus.OFF_PLAN

                comeu = status == MealStatus.DONE
                registros.append(
                    MealLog(
                        user=user,
                        slot=slot,
                        chosen_option=opcao if comeu else None,
                        date=dia,
                        status=status,
                        marked_at=timezone.now(),
                        slot_name=slot.name,
                        scheduled_time=slot.time,
                        kcal=opcao.kcal if comeu else ZERO,
                        protein_g=opcao.protein_g if comeu else ZERO,
                        carb_g=opcao.carb_g if comeu else ZERO,
                        fat_g=opcao.fat_g if comeu else ZERO,
                        notes="" if comeu else NOTA_FORA_DO_PLANO.get(status, ""),
                    )
                )

            # A agua oscila como agua oscila: nem todo dia bate a meta.
            HydrationLog.objects.create(
                user=user,
                date=dia,
                ml=1600 if atraso == 0 else 2200 + (dia.day % 4) * 300,
            )

        MealLog.objects.bulk_create(registros)

    def _preencher_cargas(self, user, ficha):
        """Cargas plausiveis em TODOS os dias da ficha, e em quatro semanas.

        Duas coisas dependem disso, e as duas sao o que a tela de treino tem de
        mais proprio: a linha "ultimo treino" e a seta de progressao. Sem carga
        anterior as duas somem, e o cartao do exercicio fica com um traco.

        A primeira versao semeava so a sessao de segunda. Quem abrisse o demo
        numa quarta caia num dia sem historico nenhum — e o visitante nao
        escolhe o dia em que chega.
        """
        hoje = timezone.localdate()
        ExerciseLog.objects.filter(user=user).delete()

        registros = []
        for sessao in ficha.sessions.all():
            for item in sessao.exercises.select_related("exercise").all():
                fator_eq = FATOR_EQUIPAMENTO.get(
                    item.exercise.equipment, Decimal("1")
                )
                if fator_eq == 0:
                    # Peso do corpo: flexao, mergulho, prancha, abdominal.
                    # Registrar quilo aqui mentiria sobre o que foi feito, e o
                    # traco na tela e a informacao certa.
                    continue

                base = Decimal(CARGA_BASE.get(item.exercise.muscle_group, 20))
                if not item.exercise.is_compound:
                    base *= FATOR_ISOLADO
                # Faixa alta de repeticao pede carga menor — 12 a 15 nao se faz
                # com o peso de 6 a 10.
                if item.rep_max > 12:
                    base *= Decimal("0.8")
                # Um degrau estavel por exercicio, para dois movimentos do
                # mesmo musculo nao sairem com o numero identico. Vem do `pk`,
                # entao e o mesmo em toda semeadura. ANTES do fator de
                # equipamento: depois dele, peso do corpo saia com 10 kg.
                base += Decimal(item.exercise_id % 5) * Decimal("2.5")
                base *= fator_eq

                # Quatro semanas subindo 2,5 kg por semana: e a progressao que
                # a tela desenha com a seta verde.
                for semana in range(SEMANAS_DE_CARGA):
                    peso = base - Decimal("2.5") * semana
                    if peso <= 0:
                        continue
                    peso = max(_arredondar(peso), CARGA_MINIMA)
                    for serie in range(1, item.sets + 1):
                        registros.append(
                            ExerciseLog(
                                user=user,
                                exercise=item.exercise,
                                date=hoje - timedelta(weeks=semana),
                                set_number=serie,
                                weight_kg=peso.quantize(Decimal("0.01")),
                                reps=item.rep_min,
                            )
                        )

        # Em lote: sao centenas de linhas, e uma consulta por serie deixaria o
        # build do Render mais lento sem nenhum ganho.
        ExerciseLog.objects.bulk_create(registros)
