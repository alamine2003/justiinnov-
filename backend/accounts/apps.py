from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = _("Comptes et périmètres")

    def ready(self):
        # Active l'historisation du périmètre des comptes.
        from accounts import signals  # noqa: F401
