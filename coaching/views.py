"""O painel do profissional e o aceite do aluno.

Nenhuma view aqui recebe o aluno como "o dono da sessão". Todas recebem um id
na URL e o trocam por um vínculo através de `permissions.vinculo_ativo`, que
levanta 403 quando o vínculo não existe, foi revogado ou não cobre o escopo.
É o único caminho, e é curto de propósito: quanto menos lugares decidem quem
pode o quê, menos lugares para errar.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from catalog.models import MealTemplate
from plans import services as plan_services
from plans.models import MealOption
from workouts.models import (
    Exercise,
    SessionExercise,
    TrainingSession,
    WorkoutTemplate,
)
from workouts.services import get_active_routine

from . import monitoring, permissions, portfolio, prescription
from .forms import (
    ConviteForm,
    MetasForm,
    PrescricaoForm,
    ProfessionalSignupForm,
    TrocaExercicioForm,
)
from .models import (
    CoachUpdate,
    LinkStatus,
    ProfessionalStudentLink,
)


class ProfissionalRequiredMixin(LoginRequiredMixin):
    """Sem perfil profissional não há painel — e não há 404 disfarçado.

    Quem não é profissional é mandado para o cadastro em vez de levar 403: a
    tela existe justamente para quem chegou por um link e ainda não se
    cadastrou, e um 403 aqui seria uma porta sem maçaneta.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not permissions.e_profissional(request.user):
            return redirect("coaching:signup")
        return super().dispatch(request, *args, **kwargs)


# ==========================================================================
# Cadastro do profissional
# ==========================================================================

class ProfessionalSignupView(LoginRequiredMixin, View):
    template_name = "coaching/signup.html"

    def get(self, request):
        if permissions.e_profissional(request.user):
            return redirect("coaching:panel")
        inicial = {"display_name": request.user.first_name or request.user.email}
        return render(request, self.template_name, {"form": ProfessionalSignupForm(initial=inicial)})

    def post(self, request):
        if permissions.e_profissional(request.user):
            return redirect("coaching:panel")
        form = ProfessionalSignupForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        perfil = form.save(commit=False)
        perfil.user = request.user
        perfil.save()
        messages.success(request, "Painel liberado. Convide seu primeiro aluno.")
        return redirect("coaching:panel")


# ==========================================================================
# Painel: a carteira
# ==========================================================================

class PanelView(ProfissionalRequiredMixin, TemplateView):
    template_name = "coaching/panel.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        alunos = portfolio.montar(permissions.carteira(self.request.user))
        situacao = self.request.GET.get("situacao") or "todos"

        contexto.update(
            {
                "nav": "painel",
                "perfil": self.request.user.professional_profile,
                "alunos": portfolio.filtrar(alunos, situacao),
                "contagem": portfolio.contagem(alunos),
                "filtros": portfolio.filtros_de(alunos, situacao),
                "situacao": situacao,
                "convites": ProfessionalStudentLink.objects.filter(
                    professional=self.request.user, status=LinkStatus.PENDING
                ).order_by("-created_at"),
                "convite_form": ConviteForm(
                    initial={"role": self.request.user.professional_profile.default_role}
                ),
            }
        )
        return contexto


class InviteCreateView(ProfissionalRequiredMixin, View):
    def post(self, request):
        form = ConviteForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Escolha o que o convite autoriza.")
            return redirect("coaching:panel")

        link = ProfessionalStudentLink.objects.create(
            professional=request.user, role=form.cleaned_data["role"]
        )
        messages.success(
            request, f"Convite {link.invite_code} criado. Vale por 7 dias."
        )
        return redirect("coaching:panel")


class InviteCancelView(ProfissionalRequiredMixin, View):
    def post(self, request, link_id):
        link = get_object_or_404(
            ProfessionalStudentLink,
            pk=link_id,
            professional=request.user,
            status=LinkStatus.PENDING,
        )
        link.delete()
        messages.success(request, "Convite cancelado.")
        return redirect("coaching:panel")


# ==========================================================================
# Aceite e revogação — o lado do aluno
# ==========================================================================

class InviteAcceptView(LoginRequiredMixin, View):
    """A tela que o aluno vê ao abrir o link do convite.

    O aceite é POST, e o GET só mostra o que está sendo pedido. Um convite que
    se aceitasse no GET seria aceito por qualquer pré-visualização de link —
    o WhatsApp abre a URL antes de a pessoa tocar nela.
    """

    template_name = "coaching/accept.html"

    def _convite(self, code):
        return ProfessionalStudentLink.objects.filter(
            invite_code=code.upper(), status=LinkStatus.PENDING
        ).select_related("professional", "professional__professional_profile").first()

    def get(self, request, code):
        link = self._convite(code)
        return render(
            request,
            self.template_name,
            {"link": link, "expirado": bool(link and link.convite_expirado)},
        )

    def post(self, request, code):
        link = self._convite(code)
        if link is None or link.convite_expirado:
            messages.error(request, "Esse convite não vale mais.")
            return redirect("plans:today")

        if link.professional_id == request.user.pk:
            messages.error(request, "Você não pode se vincular a si mesmo.")
            return redirect("plans:today")

        ja_existe = ProfessionalStudentLink.objects.filter(
            professional=link.professional, student=request.user, status=LinkStatus.ACTIVE
        ).first()
        if ja_existe:
            # O par já está ligado; aceitar de novo violaria o índice único.
            # Em vez de estourar, o convite serve para AMPLIAR o escopo — que é
            # o motivo real de um segundo convite entre as mesmas pessoas.
            ja_existe.role = link.role
            ja_existe.save(update_fields=["role"])
            link.delete()
            messages.success(request, "Acesso atualizado.")
            return redirect("accounts:professionals")

        link.aceitar(request.user)
        messages.success(
            request,
            f"{link.professional.first_name or 'Seu profissional'} agora acompanha você.",
        )
        return redirect("accounts:professionals")


class RevokeView(LoginRequiredMixin, View):
    """O aluno corta o acesso. Sem confirmação de ninguém, sem aviso prévio."""

    def post(self, request, link_id):
        link = get_object_or_404(
            ProfessionalStudentLink,
            pk=link_id,
            student=request.user,
            status=LinkStatus.ACTIVE,
        )
        link.revogar()
        messages.success(request, "Acesso revogado.")
        return redirect("accounts:professionals")


class DismissUpdateView(LoginRequiredMixin, View):
    """Marca os avisos do profissional como vistos."""

    def post(self, request):
        CoachUpdate.objects.filter(student=request.user, seen_at__isnull=True).update(
            seen_at=timezone.now()
        )
        destino = request.POST.get("next") or reverse("plans:today")
        return redirect(destino)


# ==========================================================================
# A central do aluno
# ==========================================================================

class StudentTabView(ProfissionalRequiredMixin, TemplateView):
    """Base das três abas. Só ela sabe trocar id de URL por vínculo."""

    aba = "monitoramento"
    escopo = permissions.ESCOPO_LEITURA

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        link = permissions.vinculo_ativo(
            self.request.user, self.kwargs["student_id"], self.escopo
        )
        contexto.update(
            {
                "nav": "painel",
                "link": link,
                "aluno": link.student,
                "iniciais": portfolio._iniciais(link.student),
                "aba": self.aba,
            }
        )
        return contexto


class StudentMonitorView(StudentTabView):
    template_name = "coaching/student_monitor.html"
    aba = "monitoramento"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        aluno = contexto["aluno"]
        perfil = getattr(aluno, "profile", None)
        plano = plan_services.get_active_plan(aluno)

        contexto.update(
            {
                "plano": plano,
                "peso": monitoring.grafico_de_peso(
                    aluno, perfil.target_weight_kg if perfil else None
                ),
                "dieta": monitoring.dieta(aluno, plano),
                "sessoes": monitoring.treinos(aluno),
            }
        )
        return contexto


class StudentWorkoutView(StudentTabView):
    template_name = "coaching/student_workout.html"
    aba = "treino"
    escopo = permissions.ESCOPO_TREINO

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        rotina = get_active_routine(contexto["aluno"])
        sessoes = []
        if rotina:
            sessoes = list(
                rotina.sessions.order_by("order").prefetch_related(
                    Prefetch(
                        "exercises",
                        queryset=SessionExercise.objects.select_related(
                            "exercise"
                        ).order_by("order"),
                    )
                )
            )

        # A trava que protege a prescrição tem um efeito colateral honesto: se o
        # aluno mudar os dias de treino depois da prescrição, a ficha NÃO é
        # remontada — e passa a discordar da agenda dele em silêncio. Quem pode
        # resolver isso é o treinador, então é a ele que a tela conta.
        agenda_mudou = False
        if rotina and rotina.is_prescribed:
            declarados = {
                (dia.weekday, dia.start_time, dia.duration_min)
                for dia in contexto["aluno"].training_days.all()
            }
            na_ficha = {
                (sessao.weekday, sessao.start_time, sessao.duration_min)
                for sessao in sessoes
            }
            agenda_mudou = declarados != na_ficha

        contexto.update(
            {
                "rotina": rotina,
                "sessoes": sessoes,
                "agenda_mudou": agenda_mudou,
                "modelos": WorkoutTemplate.objects.filter(is_active=True).order_by(
                    "split", "order"
                ),
                "catalogo": Exercise.objects.filter(is_active=True).order_by("name"),
            }
        )
        return contexto


class StudentNutritionView(StudentTabView):
    template_name = "coaching/student_nutrition.html"
    aba = "dieta"
    escopo = permissions.ESCOPO_DIETA

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        aluno = contexto["aluno"]
        perfil = aluno.profile
        plano = plan_services.get_active_plan(aluno)

        slots = []
        if plano:
            slots = list(
                plano.slots.order_by("order").prefetch_related("options__template")
            )
            # As receitas que cabem em cada horário, por categoria. Uma consulta
            # para todas as categorias da tela em vez de uma por horário: são
            # cinco ou seis horários, e cinco consultas idênticas para montar um
            # `<select>` é a definição de N+1 preguiçoso.
            categorias = {slot.category for slot in slots}
            por_categoria = {}
            for modelo in MealTemplate.objects.filter(
                is_active=True, category__in=categorias
            ).order_by("name"):
                por_categoria.setdefault(modelo.category, []).append(modelo)
            for slot in slots:
                slot.receitas = por_categoria.get(slot.category, [])

        contexto.update(
            {
                "plano": plano,
                "slots": slots,
                "form": MetasForm(
                    initial={
                        "activity_level": perfil.activity_level,
                        "goal": perfil.goal,
                        "target_weight_kg": perfil.target_weight_kg,
                        "kcal_adjustment": perfil.kcal_adjustment,
                        "protein_g_per_kg": perfil.protein_g_per_kg,
                        "fat_kcal_share": (
                            perfil.fat_kcal_share * 100 if perfil.fat_kcal_share else None
                        ),
                    }
                ),
            }
        )
        return contexto


# ==========================================================================
# Escrita
# ==========================================================================

class PrescreverMixin(ProfissionalRequiredMixin):
    """Resolve o vínculo, executa e devolve para a aba, com mensagem."""

    escopo = permissions.ESCOPO_TREINO
    destino = "coaching:student_workout"

    def post(self, request, student_id, *args, **kwargs):
        link = permissions.vinculo_ativo(request.user, student_id, self.escopo)
        try:
            self.executar(request, link, *args, **kwargs)
        except prescription.ForaDaFaixa as erro:
            messages.error(request, str(erro))
        return redirect(self.destino, student_id=student_id)


class AjustarExercicioView(PrescreverMixin, View):
    def executar(self, request, link, item_id):
        item = get_object_or_404(
            SessionExercise.objects.select_related("session__plan", "exercise"),
            pk=item_id,
            session__plan__user_id=link.student_id,
        )
        form = PrescricaoForm(request.POST)
        if not form.is_valid():
            raise prescription.ForaDaFaixa(
                "; ".join(m for erros in form.errors.values() for m in erros)
            )
        prescription.ajustar_exercicio(link, item, **form.cleaned_data)
        messages.success(request, f"{item.exercise.name} atualizado.")


class TrocarExercicioView(PrescreverMixin, View):
    def executar(self, request, link, item_id):
        item = get_object_or_404(
            SessionExercise.objects.select_related("session__plan", "exercise"),
            pk=item_id,
            session__plan__user_id=link.student_id,
        )
        form = TrocaExercicioForm(request.POST)
        if not form.is_valid():
            raise prescription.ForaDaFaixa("Escolha um exercício do catálogo.")
        prescription.trocar_exercicio(link, item, form.cleaned_data["exercise"])
        messages.success(request, "Exercício trocado.")


class RemoverExercicioView(PrescreverMixin, View):
    def executar(self, request, link, item_id):
        item = get_object_or_404(
            SessionExercise.objects.select_related("session__plan", "exercise"),
            pk=item_id,
            session__plan__user_id=link.student_id,
        )
        prescription.remover_exercicio(link, item)
        messages.success(request, "Exercício removido.")


class AdicionarExercicioView(PrescreverMixin, View):
    def executar(self, request, link, session_id):
        session = get_object_or_404(
            TrainingSession, pk=session_id, plan__user_id=link.student_id
        )
        form = TrocaExercicioForm(request.POST)
        if not form.is_valid():
            raise prescription.ForaDaFaixa("Escolha um exercício do catálogo.")
        prescription.adicionar_exercicio(link, session, form.cleaned_data["exercise"])
        messages.success(request, "Exercício incluído.")


class ClonarModeloView(PrescreverMixin, View):
    def executar(self, request, link, session_id):
        session = get_object_or_404(
            TrainingSession, pk=session_id, plan__user_id=link.student_id
        )
        modelo = get_object_or_404(
            WorkoutTemplate, pk=request.POST.get("template"), is_active=True
        )
        prescription.clonar_modelo(link, session, modelo)
        messages.success(request, f"Treino {session.label} montado com {modelo.name}.")


class AjustarMetasView(PrescreverMixin, View):
    escopo = permissions.ESCOPO_DIETA
    destino = "coaching:student_nutrition"

    def executar(self, request, link):
        form = MetasForm(request.POST)
        if not form.is_valid():
            raise prescription.ForaDaFaixa(
                "; ".join(m for erros in form.errors.values() for m in erros)
            )
        plano, _ = prescription.ajustar_metas(link, **form.cleaned_data)
        messages.success(
            request,
            f"Metas atualizadas: {plano.target_kcal} kcal, {plano.protein_g} g de "
            f"proteína, {plano.carb_g} g de carboidrato, {plano.fat_g} g de gordura.",
        )


class TrocarOpcaoView(PrescreverMixin, View):
    escopo = permissions.ESCOPO_DIETA
    destino = "coaching:student_nutrition"

    def executar(self, request, link, option_id):
        opcao = get_object_or_404(
            MealOption.objects.select_related("slot__plan"),
            pk=option_id,
            slot__plan__user_id=link.student_id,
        )
        modelo = get_object_or_404(
            MealTemplate, pk=request.POST.get("template"), is_active=True
        )
        prescription.trocar_opcao(link, opcao, modelo)
        messages.success(request, f"Opção {opcao.label} agora é {modelo.name}.")
