"""Deux types de notification pour la rectification d'un constat : la
demande, qui attend un administrateur, et sa décision."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0005_reprise_des_emails"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(choices=[("budget_threshold", "Seuil budgétaire atteint"), ("budget_overrun", "Dépassement budgétaire"), ("expense_submitted", "Dépense à contrôler"), ("expense_rejected", "Dépense rejetée"), ("proof_missing", "Justificatif manquant"), ("proof_incomplete", "Justificatif incomplet"), ("reallocation_requested", "Demande de réallocation"), ("storage_error", "Anomalie de stockage"), ("dossier_reopened", "Dossier rouvert"), ("rectification_requested", "Demande de rectification"), ("rectification_decided", "Décision sur une rectification")], max_length=32, verbose_name="Type"),
        ),
    ]
