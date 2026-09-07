from django.contrib import admin

from .models import (
    Exercise,
    SessionExercise,
    TrainingPlan,
    TrainingSession,
    WorkoutTemplate,
    WorkoutTemplateItem,
)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    """O catálogo se desativa; ele não se apaga.

    `WorkoutTemplateItem.exercise` e `SessionExercise.exercise` são PROTECT, e
    o comentário de lá diz por quê: "apagar um exercício que está em fichas
    quebraria o histórico. O caminho certo é marcar is_active=False."
    `ExerciseLog.exercise`, porém, é CASCADE — e é CASCADE de propósito, porque
    a carga é do EXERCÍCIO e não da sessão, para sobreviver quando a rotina é
    refeita.

    As duas decisões juntas abrem uma porta que nenhuma das duas abre sozinha:
    a proteção vem de linhas que o próprio app apaga ao remontar a ficha. Assim
    que um exercício sai de todas as fichas e de todas as sessões, o PROTECT
    para de existir e o CASCADE fica sozinho com o histórico.

    Medido em 07/09/2026, no banco de desenvolvimento, dentro de transação
    desfeita: "Cadeira extensora" tinha 300 cargas registradas e recusava o
    `delete()` com `ProtectedError` por 22 linhas. Removidos os 3 itens de
    ficha e as 19 sessões — exatamente o que a remontagem faz —, o mesmo
    `delete()` passou e levou as 300 cargas junto. Dois exercícios do catálogo
    JÁ estão nesse estado hoje ("Afundo com halteres", ativo, e "Remada
    curvada", o legado desativado); os dois estão com zero cargas, então nada
    está em risco agora, e é por isso que isto é uma trava e não um incidente.

    A trava fica AQUI e não no modelo: mudar `on_delete` para PROTECT exigiria
    migração e tiraria do dono a única saída legítima para um exercício criado
    por engano. Fechar a porta do admin resolve o caminho real sem mexer na
    relação.
    """

    list_display = ("name", "muscle_group", "is_compound", "is_active")
    list_filter = ("muscle_group", "is_compound", "is_active")
    search_fields = ("name",)

    def has_delete_permission(self, request, obj=None):
        """Fecha os DOIS caminhos, e o segundo de graça.

        Havia aqui um `get_actions` que removia `delete_selected` à mão, para
        cobrir a ação em massa da listagem. A bateria de sabotagem mostrou que
        ele era código morto: apaguei a linha do `pop` e NENHUM teste ficou
        vermelho. O motivo está em `ModelAdmin._filter_actions_by_permissions`
        — `delete_selected` declara `allowed_permissions = ("delete",)`, então
        o próprio Django já a descarta quando este método devolve False.

        O teste da ação em massa continua onde está. Ele não morde este
        método, morde o de cima — e é isso que se quer: se alguém devolver
        True aqui, os dois caminhos reabrem juntos e os dois testes acusam.
        """
        return False


class WorkoutTemplateItemInline(admin.TabularInline):
    model = WorkoutTemplateItem
    extra = 1
    autocomplete_fields = ("exercise",)


@admin.register(WorkoutTemplate)
class WorkoutTemplateAdmin(admin.ModelAdmin):
    list_display = ("split", "label", "name", "focus", "is_active")
    list_filter = ("split", "is_active")
    inlines = [WorkoutTemplateItemInline]


class SessionExerciseInline(admin.TabularInline):
    model = SessionExercise
    extra = 0
    autocomplete_fields = ("exercise",)


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ("plan", "weekday", "label", "name")
    inlines = [SessionExerciseInline]


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    # A rotina é um snapshot: editar à mão o que foi gerado é o caminho mais
    # curto para uma ficha que não corresponde a divisão nenhuma.
    list_display = ("user", "split", "days_per_week", "is_active", "created_at")
    list_filter = ("split", "is_active")
    readonly_fields = ("created_at",)
