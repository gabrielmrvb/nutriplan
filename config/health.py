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
from django.db import OperationalError, connection
from django.http import JsonResponse
from django.views import View


class HealthView(View):
    def get(self, request, *args, **kwargs):
        # Importados aqui dentro, e não no topo, porque este módulo é lido
        # durante o carregamento das URLs — antes de os apps estarem prontos.
        from catalog.models import Food, MealTemplate
        from workouts.models import Exercise

        try:
            connection.ensure_connection()
        except OperationalError as erro:
            return JsonResponse(
                {"status": "sem banco", "erro": str(erro)},
                status=503,
            )

        # Só o que está ATIVO conta. Alimento aposentado continua na tabela
        # para o histórico de quem já comeu não virar buraco, mas não aparece
        # para ninguém — contá-lo aqui responderia sobre o banco, e a pergunta
        # é sobre o que o usuário encontra na tela.
        catalogo = {
            "alimentos": Food.objects.filter(is_active=True).count(),
            "modelos_de_refeicao": MealTemplate.objects.filter(is_active=True).count(),
            "exercicios": Exercise.objects.count(),
            "exercicios_com_video": Exercise.objects.exclude(video_url="").count(),
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
