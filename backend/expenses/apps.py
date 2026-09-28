from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "expenses"
    verbose_name = "Dépenses et justificatifs"

    def ready(self):
        from . import signals

        signals.connect()
