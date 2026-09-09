from django.urls import path

from . import corrida_views, views

app_name = "workouts"

urlpatterns = [
    path("", views.WorkoutView.as_view(), name="routine"),
    # O modo treino é uma tela própria, e não uma âncora dentro da lista: a
    # pessoa precisa poder voltar para ele, recarregar e compartilhar o
    # endereço sem cair no meio de uma página de cinco mil pixels.
    path("agora/", views.ModoTreinoView.as_view(), name="now"),
    # A FICHA DE UMA SESSÃO É UMA PÁGINA, e não uma sanfona da tela principal.
    #
    # A tela de treino desenhava o cartão completo de todo exercício de toda
    # sessão da semana — 259 kB e 141 botões no perfil de seis dias, quase
    # todos fora da área visível. O detalhe continua inteiro; ele mudou de
    # página, e agora só é montado por quem pede.
    path("ficha/<int:sessao_id>/", views.FichaDaSessaoView.as_view(), name="ficha"),
    path("agora/serie/", views.ConcluirSerieView.as_view(), name="record_set"),
    path(
        "exercicio/<int:exercise_id>/carga/",
        views.RecordLoadView.as_view(),
        name="record_load",
    ),
    path("exportar/saude.tcx", views.HealthExportView.as_view(), name="health_export"),
    # Corrida. As telas vivem sob `treino/` porque é a mesma aba do app — a
    # visão aprovada tem Corrida como destino próprio, e movê-la para lá é
    # troca de rota, não de código.
    path("corridas/", corrida_views.HistoricoDeCorridasView.as_view(), name="corridas"),
    path("corridas/salvar/", corrida_views.SalvarCorridaView.as_view(), name="salvar_corrida"),
]
