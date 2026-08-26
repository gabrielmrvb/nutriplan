"""Os avisos do profissional, disponíveis em qualquer tela do aluno.

Um processador de contexto e não um bloco por template: a mudança pode ter sido
no treino e o aluno abrir a dieta primeiro. O aviso precisa alcançá-lo onde ele
estiver, e não onde a mudança aconteceu.

O custo é uma consulta por página autenticada, e ela é barata — índice em
(student, seen_at) e no máximo três linhas lidas.
"""
from .models import CoachUpdate
from .permissions import e_profissional

#: Três avisos. Acima disso vira mural, e um mural com sete recados é um mural
#: que se fecha sem ler.
LIMITE = 3


def coach_updates(request):
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return {}

    # A aba "Alunos" da barra de baixo depende disto. Dava para o template
    # perguntar `user.professional_profile` direto, e funcionaria — mas por
    # acidente: o motor de template engole em silêncio a exceção de relação
    # ausente. Um booleano explícito diz o que quer dizer.
    contexto = {"is_professional": e_profissional(user)}

    avisos = list(
        CoachUpdate.objects.filter(student=user, seen_at__isnull=True)
        .select_related("professional")[: LIMITE + 1]
    )
    contexto.update(
        {
            "coach_updates": avisos[:LIMITE],
            "coach_updates_extra": max(0, len(avisos) - LIMITE),
        }
    )
    return contexto
