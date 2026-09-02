from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from .models import (
    AcaoAdministrativa,
    Profile,
    RegistroAdministrativo,
    TrainingDay,
    User,
    WeightEntry,
)

#: Os campos que decidem AUTORIZAÇÃO, e não identidade.
#:
#: `UserAdmin` do Django traz os quatro no fieldset de permissões, e quem tem
#: `change_user` recebe todos. O papel Administradores NutriPlan tem
#: `change_user` porque precisa corrigir conta de gente — e ganhava junto a
#: capacidade de se promover a superuser.
#:
#: Comprovado por POST em ambiente controlado, olhando o banco depois:
#: `is_superuser` gravado como True na própria conta, grupo administrativo
#: concedido, e `delete_user` atribuído direto pelo `user_permissions` — sem
#: passar por grupo nenhum.
#:
#: A trava construída em outro lugar não valia nada: `/admin/auth/group/`
#: responde 403 e `/admin/auth/permission/` nem está registrado, mas o
#: formulário de usuário oferecia os MESMOS controles. Porta trancada, janela
#: aberta ao lado.
CAMPOS_DE_AUTORIZACAO = ("is_superuser", "is_staff", "groups", "user_permissions")


class ProfileInline(admin.StackedInline):
    """O perfil, com cada campo decidido — e não `__all__` por omissão.

    Sem `fields` nem `readonly_fields`, o Django mostra os vinte campos
    editáveis: data de nascimento, altura, objetivo, nível de atividade, ajuste
    calórico, janela de sono. Um operador podia mudar a altura de alguém sem
    que nada o impedisse, e sem que a pessoa soubesse.

    A pergunta que decidiu cada linha abaixo foi sempre a mesma: POR QUE um
    administrador precisaria mudar isto? Onde não houve resposta concreta, o
    campo é somente leitura. Ver resolve suporte — "o onboarding dela travou no
    passo 3?" —, alterar é outra coisa.

    Os três editáveis têm caso operacional real e nenhum deles é dado corporal:

      `split_preference` e `split_preference_confirmada` existem porque a
      pergunta de divisão não aparece até quatro dias de treino, e alguém pode
      precisar destravar isso para quem ficou preso no ABC que não escolheu.

      `kcal_adjustment` é o ajuste manual sobre a meta, que já é um controle
      de suporte por natureza — a pessoa pede "está muito apertado" e alguém
      mexe.

    O que fica de fora da edição, e por quê: `sex`, `birth_date` e `height_cm`
    são dados corporais que a própria pessoa informou; `goal`,
    `activity_level`, `meal_style` e `dietary_tags` mudam a prescrição inteira,
    e mudá-los pelo painel reescreveria o plano de alguém sem ela pedir;
    `onboarding_step` e as datas são estado do sistema, não opinião.
    """

    model = Profile
    can_delete = False
    fields = (
        # Identidade e corpo — leitura, para suporte entender o contexto.
        "sex",
        "birth_date",
        "height_cm",
        # Objetivo e rotina — leitura: mudam a prescrição inteira.
        "goal",
        "activity_level",
        "meal_style",
        "dietary_tags",
        "wake_time",
        "sleep_time",
        "timezone",
        # Operacionais — editáveis, com caso de suporte concreto.
        "split_preference",
        "split_preference_confirmada",
        "kcal_adjustment",
        # Estado do onboarding — leitura, é diagnóstico.
        "onboarding_step",
        "onboarding_completed_at",
        "recalibrated_at",
    )
    #: TODOS somente leitura.
    #:
    #: A versão anterior deixava `split_preference`, `split_preference_confirmada`
    #: e `kcal_adjustment` editáveis, e nenhum dos três sobreviveu à pergunta
    #: "qual é o caso operacional?".
    #:
    #: A divisão quem escolhe é a pessoa, no passo 4 — o caso de suporte é
    #: fazer o app PERGUNTAR de novo, e isso virou uma ação com permissão
    #: própria em `UserAdmin`. Marcar `confirmada` pelo painel afirmaria uma
    #: escolha que ninguém fez.
    #:
    #: `kcal_adjustment` é derivado: `weight_trend` o move sozinho conforme o
    #: peso responde. E ele é `SmallIntegerField` sem validador, enquanto o
    #: motor tem piso (a taxa basal) e nenhum teto — um POST com +30000 daria
    #: meta de 32 mil kcal. Editá-lo seria adicionar risco para atender um caso
    #: de uso que não existe.
    readonly_fields = fields


class TrainingDayInline(admin.TabularInline):
    """Os dias de treino, como CONTEXTO da conta.

    Somente leitura: alterar um dia aqui remonta a ficha da pessoa pelo
    gerador, e isso é decisão dela na tela de configuração — onde ela vê o
    resultado. Pelo painel, a mudança aconteceria sem ninguém do outro lado
    entender por que o treino de terça virou outro.
    """

    model = TrainingDay
    extra = 0
    can_delete = False
    fields = ("weekday", "start_time", "duration_min")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class WeightEntryInline(admin.TabularInline):
    """As pesagens, somente leitura e sem acrescentar.

    Peso é o dado mais sensível do app, e a única pergunta de suporte que ele
    responde é "a pessoa está registrando?". Para isso basta ver. Editar
    reescreveria o histórico dela; acrescentar inventaria uma medição que
    ninguém fez.

    Continua como inline E como página própria: a página serve para procurar
    por conta quando alguém relata problema de registro, e o inline dá o
    contexto de quem já está aberto. Nenhuma das duas edita.
    """

    model = WeightEntry
    extra = 0
    can_delete = False
    fields = ("date", "weight_kg", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline, TrainingDayInline, WeightEntryInline]
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "entra_por_google",
        "classificacao",
        "date_joined",
    )
    list_filter = ("classificacao", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name")}),
        (
            "Para que serve esta conta",
            {
                "fields": ("classificacao",),
                "description": (
                    "Classificar é decisão de gente. Nenhuma conta foi "
                    "classificada automaticamente, e o painel de gestão mostra "
                    "quantas continuam sem classificação."
                ),
            },
        ),
        (
            "Permissões",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )

    #: A rota da ação, no DETALHE de uma conta e não na lista.
    #:
    #: O caso de suporte é sobre UMA pessoa — "estou preso num ABC que não
    #: escolhi". Ação em lote resolveria um problema que ninguém tem e criaria
    #: um botão capaz de reperguntar a divisão de cinquenta contas por engano.
    def user_change_password(self, request, id, form_url=""):
        """Ninguém troca a senha de outra pessoa por aqui. Nem superuser.

        O `UserAdmin` do Django expõe `<pk>/password/` como rota SEPARADA do
        formulário de detalhe, e ela não passa por `fieldsets` nem por
        `readonly_fields` — foi assim que sobreviveu à rodada inteira de
        hardening: a auditoria olhou os campos do formulário e a rota nunca
        apareceu.

        Medido em ambiente controlado antes do conserto: um staff não-superuser
        com apenas `change_user` postava ali e a senha da outra pessoa mudava —
        302, hash novo, `check_password` da senha do invasor devolvendo True.
        Tomada de conta com carimbo oficial.

        Não existe caso operacional. Quem esqueceu a senha usa a recuperação,
        que manda o link para o e-mail DELA — o único caminho em que a pessoa
        continua sendo quem decide. E o primeiro operador administrativo entra
        por Google, sem senha utilizável: um botão que CRIA senha para uma conta
        que não tinha é o oposto do que "Google-only" significa.
        """
        raise PermissionDenied(
            "A senha de uma conta não se troca pelo painel. "
            "Quem esqueceu a senha usa a recuperação, que vai para o e-mail dela."
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Leva à tela o que decide se a ação da divisão aparece.

        O template não pode decidir sozinho: `has_perm` no template esconderia
        o botão sem provar nada, e o estado do perfil — já aguardando ou não —
        é o que separa "operação disponível" de "já pedida". Quem autoriza de
        verdade continua sendo a checagem dentro da própria ação; isto aqui só
        evita oferecer um botão que vai recusar.
        """
        alvo = self.get_object(request, object_id)
        perfil = getattr(alvo, "profile", None) if alvo is not None else None
        extra_context = {
            **(extra_context or {}),
            "pode_pedir_nova_divisao": (
                perfil is not None
                and request.user.has_perm("accounts.pedir_nova_escolha_de_divisao")
            ),
            "divisao_aguardando": (
                perfil is not None and not perfil.split_preference_confirmada
            ),
        }
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        return [
            path(
                "<int:user_id>/pedir-nova-divisao/",
                self.admin_site.admin_view(self.pedir_nova_escolha_de_divisao),
                name="accounts_user_pedir_nova_divisao",
            ),
            *super().get_urls(),
        ]

    @method_decorator(require_POST)
    @transaction.atomic
    def pedir_nova_escolha_de_divisao(self, request, user_id):
        """Faz o app perguntar a divisão de novo. Só isso.

        O que ela NÃO faz é o desenho inteiro: não escolhe a divisão pela
        pessoa. `split_preference` fica onde está — atribuir uma escolha nova
        seria afirmar que alguém decidiu quando ninguém decidiu, que é a mesma
        mentira que o campo `confirmada` nasceu para impedir quando o padrão
        TRES era tratado como resposta.

        POST apenas, com CSRF, porque isto ESCREVE. Um GET que altera estado é
        acionável por qualquer imagem numa página de terceiro.

        A permissão é de propósito — `pedir_nova_escolha_de_divisao` — e não
        `change_profile`: a segunda autorizaria mexer em vinte campos para
        liberar um.
        """
        alvo = get_object_or_404(User, pk=user_id)

        if not request.user.has_perm("accounts.pedir_nova_escolha_de_divisao"):
            raise PermissionDenied(
                "Esta conta não pode pedir nova escolha de divisão."
            )

        perfil = getattr(alvo, "profile", None)
        if perfil is None:
            self.message_user(
                request, "Esta conta ainda não tem perfil.", level=messages.WARNING
            )
        elif not perfil.split_preference_confirmada:
            # Já está aguardando. Escrever de novo produziria um evento de
            # auditoria dizendo que algo mudou quando nada mudou — e trilha com
            # evento falso é pior que trilha curta.
            self.message_user(
                request,
                "Esta conta já está aguardando nova confirmação de divisão.",
                level=messages.INFO,
            )
        else:
            Profile.objects.filter(pk=perfil.pk).update(
                split_preference_confirmada=False
            )
            RegistroAdministrativo.objects.create(
                ator=request.user,
                acao=AcaoAdministrativa.PEDIU_NOVA_DIVISAO,
                alvo=alvo,
                alvo_email=alvo.email,
                detalhe={"origem": "ação do Admin"},
            )
            self.message_user(
                request,
                "Pronto: o app vai perguntar a divisão de treino de novo.",
                level=messages.SUCCESS,
            )

        return redirect(
            reverse("admin:accounts_user_change", args=[alvo.pk])
        )

    @admin.display(boolean=True, description="Google", ordering="entra_por_google")
    def entra_por_google(self, obj):
        """Responde a pergunta de suporte sem abrir o perfil do provedor.

        `SocialAccount` saiu do Admin: o `extra_data` dele é o perfil que o
        Google devolve — nome, foto, locale, o `sub` — e "não contém access
        token" não o torna inofensivo. O que suporte precisa saber é se a conta
        entra por Google, e isso é um booleano.

        `Exists` numa subconsulta anotada, e não `obj.socialaccount_set.exists()`
        por linha: a segunda forma custa uma consulta por conta na listagem.
        """
        return getattr(obj, "entra_por_google", False)

    def get_queryset(self, request):
        from allauth.socialaccount.models import SocialAccount

        return super().get_queryset(request).annotate(
            entra_por_google=Exists(
                SocialAccount.objects.filter(user_id=OuterRef("pk"))
            )
        )

    def get_readonly_fields(self, request, obj=None):
        """Quem não é superuser vê a autorização, mas não mexe nela.

        A regra é `is_superuser`, e NÃO o nome do grupo. Amanhã outro grupo
        recebe `change_user` — o papel Suporte, por exemplo, se alguém decidir
        que ele precisa corrigir um e-mail — e a proteção precisa valer para
        ele sem ninguém lembrar de acrescentá-lo a uma lista.

        `readonly_fields` não é enfeite visual: o Django REMOVE o campo do
        formulário, então um POST forjado com `is_superuser=on` não encontra
        onde gravar. É a diferença entre esconder o controle e desligá-lo — e
        os testes provam pelo estado do banco, não pelo HTML.

        Continuam visíveis porque suporte precisa responder "esta conta é
        staff?" sem abrir o banco. Ver é diagnóstico; alterar é autorização.
        """
        somente_leitura = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            somente_leitura += [
                campo
                for campo in CAMPOS_DE_AUTORIZACAO
                if campo not in somente_leitura
            ]
        return tuple(somente_leitura)


# O `Group` do Django vem registrado com formulário completo. Trocamos por
# uma tela de conferência.
admin.site.unregister(Group)


@admin.register(Group)
class GrupoAdmin(admin.ModelAdmin):
    """Os papéis, somente para CONFERIR o que cada um concede.

    Existe por uma pergunta que hoje só o console do banco respondia: "o que o
    papel Administradores concede AGORA, em produção?". `accounts/papeis.py`
    diz o que DEVERIA conceder; esta tela diz o que o banco tem. As duas
    coincidirem é o que a reconciliação garante — e quando não coincidem, é
    esta tela que mostra.

    Somente leitura, e por um motivo específico deste projeto: `PAPEIS` é a
    fonte autoritativa e a sincronização roda em todo deploy com `set()`. Uma
    tela editável aqui seria armadilha — a pessoa concede uma permissão, vê
    "salvo com sucesso", e o próximo deploy a remove sem avisar ninguém. Papel
    se muda no código, com revisão e histórico.

    Django registra `Group` sozinho, com formulário completo: nome editável e
    o seletor de permissões inteiro. Esse formulário é a mesma escalada que o
    `UserAdmin` já teve fechada, por outra porta — quem edita o grupo edita o
    que o grupo concede a si mesmo.
    """

    list_display = ("name", "quantas_permissoes")
    fields = ("name", "permissoes")
    readonly_fields = fields
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "permissions__content_type"
        )

    @admin.display(description="permissões")
    def quantas_permissoes(self, obj):
        return obj.permissions.count()

    @admin.display(description="o que concede")
    def permissoes(self, obj):
        nomes = sorted(
            f"{p.content_type.app_label}.{p.codename}"
            for p in obj.permissions.all()
        )
        return "\n".join(nomes) or "—"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# `WeightEntry` NÃO tem página própria, e a decisão é do mesmo tipo das outras
# desta rodada: qual é o caso operacional?
#
# A pergunta de suporte é "esta pessoa está registrando o peso?", e ela se
# responde no inline, dentro da conta dela. O que a página avulsa acrescentava
# era outra coisa — navegar a série de peso de TODAS as contas, com filtro por
# data. Isso não responde nenhum atendimento, e peso é o dado mais sensível do
# app.
#
# O que se perde: o diagnóstico agregado ("o registro de peso parou para todo
# mundo depois do dia X?"). É pergunta legítima e é de painel de negócio, não
# de tela que lista o peso de cada pessoa uma por uma.

@admin.register(RegistroAdministrativo)
class RegistroAdministrativoAdmin(admin.ModelAdmin):
    """A trilha administrativa, imutável pela interface.

    Uma trilha que se pode editar não é trilha — é um documento que diz o que o
    último editor quis. As três permissões estão negadas no método, e não só
    ausentes do grupo: `has_*_permission` é o que o Django consulta antes de
    montar formulário E antes de aceitar POST, então um pedido forjado para
    `/add/` ou `/change/` bate na mesma porta que o botão escondido.

    `detalhe` aparece porque é onde está o antes/depois de cada ação, e ele já
    nasce sem segredo: o comando que grava põe ali papel, origem e flags, nunca
    senha, hash ou token.
    """

    list_display = ("criado_em", "acao", "alvo_email", "ator")
    list_filter = ("acao", "criado_em")
    search_fields = ("alvo_email", "ator__email")
    date_hierarchy = "criado_em"
    fields = ("criado_em", "acao", "ator", "alvo", "alvo_email", "detalhe")
    readonly_fields = fields

    def get_queryset(self, request):
        # Duas linhas na lista com FK para User seriam duas consultas por
        # linha sem isto.
        return super().get_queryset(request).select_related("ator", "alvo")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
