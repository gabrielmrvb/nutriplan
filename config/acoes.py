# -*- coding: utf-8 -*-
"""Endpoint de ação que recebe um GET devolve a TELA, e não uma página em branco.

O caminho que motivou isto, medido de ponta a ponta:

  1. a sessão expira — que é o jeito mais comum de uma sessão acabar, porque
     ninguém sai do app de propósito;
  2. a pessoa toca em "+250 ml", "Comi esta" ou "Salvar peso";
  3. `login_required` manda para `/conta/entrar/?next=/agua/`;
  4. ela entra corretamente;
  5. o Django redireciona para o `next` — com um GET;
  6. `/agua/` só aceita POST, e responde **405 com zero byte**.

O fim da história é uma tela completamente em branco, sem mensagem e sem
navegação, logo depois de um login bem-sucedido. Quem fez tudo certo é quem
recebe o beco.

`TodaTelaTemPortaTests` existe justamente contra isso, mas ele olha destinos
que uma pessoa alcança de propósito — e ninguém digita `/agua/` na barra de
endereço. Este caminho chega lá pelo `next`, que o próprio Django preenche.

A resposta não é aceitar GET como ação: seria transformar um efeito colateral
em algo que um link consegue disparar. A resposta é o GET levar à tela a que a
ação pertence, que é onde a pessoa queria estar.
"""
from django.shortcuts import redirect


class AcaoDeTela:
    """Mixin para view que só existe para receber POST de um formulário.

    Quem usar declara `tela_da_acao` — a rota da tela onde o botão vive. O
    padrão é o dia de hoje porque é de lá que vem a maioria das ações, e
    porque é a porta de entrada do app: errar para lá é errar para o lugar
    menos ruim.
    """

    #: Nome da rota da tela a que a ação pertence.
    tela_da_acao = "plans:today"

    def get(self, request, *args, **kwargs):
        return redirect(self.tela_da_acao)
