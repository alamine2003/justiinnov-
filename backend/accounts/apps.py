from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Comptes et périmètres"

    def ready(self):
        # Active l'historisation du périmètre des comptes.
        from accounts import signals  # noqa: F401
