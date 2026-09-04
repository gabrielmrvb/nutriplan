# -*- coding: utf-8 -*-
"""As rotas da API, sob `/api/v1/`.

VERSÃO NO CAMINHO, E SÓ ISSO
============================

`v1` no caminho é a estratégia inteira, e é deliberadamente pequena. Um app
publicado na loja não atualiza junto com o servidor: existe gente com a versão
de três meses atrás no telefone, e um deploy não pode quebrá-la. O prefixo é o
que permite `v2` nascer ao lado sem tocar em `v1`.

Nada de negociação por cabeçalho, nada de versão por recurso: o custo aparece
na primeira dúvida ("qual versão esta rota está servindo?") e o ganho só
existiria se houvesse muitos clientes independentes. Há um, e ele nem nasceu.

Nomes em português, como o resto do produto — `/agua/`, `/conta/`, `/treino/`,
`/corridas/`. Uma API em inglês dentro de um app pt-BR seria a única parte que
fala outra língua.
"""
from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    # POST troca e-mail e senha por token; DELETE revoga o token usado.
    path("token/", views.token, name="token"),
    path("eu/", views.eu, name="eu"),
    # GET lista; POST cria ou reconhece uma já sincronizada (idempotente).
    path("corridas/", views.corridas, name="corridas"),
    # Por `op_id` e não por `pk`: identificador sequencial convida a varrer o
    # vizinho.
    path("corridas/<str:op_id>/", views.corrida, name="corrida"),
]
