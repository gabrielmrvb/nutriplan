"""Endpoint de saúde: um pedido barato que responde "a aplicação está inteira?".

Existe por uma lacuna concreta. O `scripts/build.sh` roda com `set -o errexit`,
então um build bem-sucedido prova que `migrate` e os seeds terminaram sem erro —
mas não prova que o catálogo ficou populado. E a diferença aparece no pior lugar
possível: a pessoa cria a conta, termina o onboarding e chega a uma tela sem
nenhum alimento e nenhum exercício, sem mensagem de erro em lugar nenhum.

No plano gratuito do Render não há shell nem job avulso para ir conferir por
dentro, então a conferência precisa caber numa URL. Esta.

Também serve de `healthCheckPath`: a plataforma passa a bater aqui em vez de
renderizar a tela de login inteira a cada poucos segundos, e passa a derrubar o
deploy quando o banco não responde — que é o que um health check deveria fazer.

O que é exposto são contagens de catálogo, os mesmos números que qualquer
visitante veria navegando. Nada de usuário, nada de dado pessoal.
"""
from django.db import OperationalError, ProgrammingError, connection
from django.http import JsonResponse
from django.views import View


class VivoView(View):
    """Liveness: o processo responde? Só isso.

    Separado do `/saude/` porque as duas perguntas têm consequências
    diferentes. "O processo está de pé?" se responde sem tocar no banco — e é o
    que decide REINICIAR. "A aplicação está pronta para atender?" precisa do
    banco e do catálogo, e é o que decide MANDAR TRÁFEGO.

    Misturar as duas tem um efeito ruim e não óbvio: uma indisponibilidade
    momentânea do banco derrubaria um processo que estava perfeitamente vivo, e
    reiniciar não conserta banco fora do ar — só piora, porque a subida custa
    mais um cold start.
    """

    def get(self, request, *args, **kwargs):
        return JsonResponse({"status": "vivo"})


class HealthView(View):
    """Readiness: subiu inteiro e pronto para receber gente?

    UMA consulta, e não cinco. A versão anterior fazia um `COUNT` por tabela —
    quatro viagens ao banco a cada batida do health check da plataforma, que
    acontece de poucos em poucos segundos. Agora as contagens vão juntas num
    único `SELECT` de subconsultas: a resposta é a mesma e o custo é uma ida.
    """

    def get(self, request, *args, **kwargs):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                      (select count(*) from catalog_food where is_active),
                      (select count(*) from catalog_mealtemplate where is_active),
                      (select count(*) from workouts_exercise),
                      (select count(*) from workouts_exercise where video_url <> '')
                    """
                )
                alimentos, modelos, exercicios, com_video = cursor.fetchone()
        except (OperationalError, ProgrammingError) as erro:
            # `ProgrammingError` cobre o instante entre o deploy e o `migrate`:
            # a tabela pode ainda não existir, e isso é "não pronto", não
            # "banco caiu".
            return JsonResponse(
                {"status": "sem banco", "erro": str(erro)[:200]}, status=503
            )

        # Só o que está ATIVO conta. Alimento aposentado continua na tabela
        # para o histórico de quem já comeu não virar buraco, mas não aparece
        # para ninguém — contá-lo aqui responderia sobre o banco, e a pergunta
        # é sobre o que o usuário encontra na tela.
        catalogo = {
            "alimentos": alimentos,
            "modelos_de_refeicao": modelos,
            "exercicios": exercicios,
            "exercicios_com_video": com_video,
        }

        # Catálogo vazio é app quebrado, não app saudável: o cadastro termina
        # numa tela sem nada. Responder 503 faz a plataforma tratar como falha
        # em vez de publicar um site que só decepciona quem entra.
        vazio = [nome for nome, quantidade in catalogo.items() if quantidade == 0]
        if vazio:
            return JsonResponse(
                {"status": "catalogo incompleto", "faltando": vazio, "catalogo": catalogo},
                status=503,
            )

        return JsonResponse({"status": "ok", "catalogo": catalogo})
