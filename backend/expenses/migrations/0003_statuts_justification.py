"""Renomme les états du circuit vers le vocabulaire de la justification.

Une dépense n'est pas « validée » : elle est **justifiée** ou non. Le contrôle
constate qu'une preuve couvre un décaissement déjà effectué, il n'autorise pas
un achat.
"""

from django.db import migrations

RENAMES = [("approved", "justified"), ("rejected", "unjustified")]


def vers_justification(apps, schema_editor):
    for model_name in ("Dossier", "Expense"):
        model = apps.get_model("expenses", model_name)
        for ancien, nouveau in RENAMES:
            model.objects.filter(status=ancien).update(status=nouveau)


def retour(apps, schema_editor):
    for model_name in ("Dossier", "Expense"):
        model = apps.get_model("expenses", model_name)
        for ancien, nouveau in RENAMES:
            model.objects.filter(status=nouveau).update(status=ancien)


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0002_alter_auditlog_action_alter_dossier_status_and_more")
    ]
    operations = [migrations.RunPython(vers_justification, retour)]
