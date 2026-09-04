from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = _("Gestion des pays et organisations")

    def ready(self):
        # Active les signaux d'historisation (attachements / changements)
        from core import signals  # noqa: F401