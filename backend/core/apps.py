from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Gestion des pays et organisations"

    def ready(self):
        # Active les signaux d'historisation (attachements / changements)
        from core import signals  # noqa: F401