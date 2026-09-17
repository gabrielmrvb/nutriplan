from django.apps import AppConfig


class WorkoutsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workouts"
    verbose_name = "treinos"

    def ready(self):
        # `workouts.doutrina.carregar()` (TREINO.md) já é eager por
        # construção — `accounts.models.TETO_POR_EXPERIENCIA` chama
        # `doutrina.teto_semanal(...)` na importação do módulo, então um
        # TREINO.md quebrado derruba o boot. `doutrina_corrida.carregar()`
        # (CORRIDA.md) é lazy — só validava no primeiro request de
        # `/treino/corridas/` — e por isso um documento quebrado passava
        # `manage.py check --deploy` no `scripts/build.sh` e só reprovava
        # depois do deploy, quando alguém abrisse a tela. Chamar aqui iguala
        # as duas doutrinas: o boot (e o `check --deploy` do build) reprova
        # ANTES de subir.
        from . import doutrina_corrida

        doutrina_corrida.carregar()
