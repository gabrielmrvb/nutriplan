"""A autorização, num lugar só.

Toda leitura e toda escrita do profissional sobre dados de aluno passa por
`vinculo_ativo()`. Não existe um segundo caminho: as views não filtram por
`professional_id` na mão, não confiam em id vindo da URL e não escondem botão
como forma de proteção — esconder botão é enfeite, a trava é aqui.

O desenho é o de negar por padrão. `vinculo_ativo` levanta `PermissionDenied`
em vez de devolver `None`, porque um `None` esquecido num `if` vira acesso
liberado, e um levantamento esquecido vira erro 500 — o modo errado de falhar é
o que fecha a porta, não o que abre.
"""
from django.core.exceptions import PermissionDenied

from .models import LinkStatus, ProfessionalStudentLink

#: Escopos. Uma view declara o que precisa e a função confere contra o papel do
#: vínculo — treinador não mexe em macro, nutricionista não mexe em série.
ESCOPO_TREINO = "treino"
ESCOPO_DIETA = "dieta"
#: Só ler. Serve às abas de monitoramento, que ambos os papéis enxergam.
ESCOPO_LEITURA = "leitura"


def vinculo_ativo(professional, student_id, escopo=ESCOPO_LEITURA):
    """O vínculo que autoriza este profissional sobre este aluno, ou 403.

    `student_id` vem da URL e é tratado como entrada hostil: a consulta filtra
    por `professional` *e* por `student`, então um id de outra pessoa não casa
    com nenhuma linha e o resultado é o mesmo de não existir vínculo.
    """
    if not getattr(professional, "is_authenticated", False):
        raise PermissionDenied("Não autenticado.")

    link = (
        ProfessionalStudentLink.objects.filter(
            professional=professional,
            student_id=student_id,
            status=LinkStatus.ACTIVE,
        )
        .select_related("student", "student__profile")
        .first()
    )
    if link is None:
        raise PermissionDenied("Sem vínculo ativo com este aluno.")

    if escopo == ESCOPO_TREINO and not link.pode_treino:
        raise PermissionDenied("Este vínculo não autoriza mexer no treino.")
    if escopo == ESCOPO_DIETA and not link.pode_dieta:
        raise PermissionDenied("Este vínculo não autoriza mexer na dieta.")
    return link


def e_profissional(user) -> bool:
    return getattr(user, "is_authenticated", False) and hasattr(
        user, "professional_profile"
    )


def carteira(professional):
    """Os vínculos ativos do profissional, prontos para a listagem."""
    return ProfessionalStudentLink.objects.da_carteira(professional).order_by(
        "student__first_name", "student__email"
    )


def profissionais_de(student):
    """Quem enxerga a ficha deste aluno — a lista que ele revoga."""
    return (
        ProfessionalStudentLink.objects.ativos()
        .filter(student=student)
        .select_related("professional", "professional__professional_profile")
        .order_by("-accepted_at")
    )
