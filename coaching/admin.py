from django.contrib import admin

from .models import CoachUpdate, ProfessionalProfile, ProfessionalStudentLink


@admin.register(ProfessionalProfile)
class ProfessionalProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "default_role", "council_id", "created_at")
    search_fields = ("display_name", "user__email", "council_id")


@admin.register(ProfessionalStudentLink)
class ProfessionalStudentLinkAdmin(admin.ModelAdmin):
    list_display = ("professional", "student", "role", "status", "invite_code", "created_at")
    list_filter = ("status", "role")
    search_fields = ("professional__email", "student__email", "invite_code")
    # Somente leitura: um vínculo criado à mão no admin pularia o aceite do
    # aluno, que é a única coisa que autoriza o acesso.
    readonly_fields = ("invite_code", "created_at", "accepted_at", "revoked_at")


@admin.register(CoachUpdate)
class CoachUpdateAdmin(admin.ModelAdmin):
    list_display = ("student", "professional", "kind", "message", "created_at", "seen_at")
    list_filter = ("kind",)
