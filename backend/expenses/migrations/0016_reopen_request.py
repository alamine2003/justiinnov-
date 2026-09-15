"""Demande de réouverture d'un dossier déclaré.

Seul un administrateur rouvre ; le pays, qui voit son erreur le premier,
peut désormais le *demander* sur un dossier soumis ou en contrôle, motif à
l'appui. Un administrateur — jamais l'auteur de la demande — approuve, et
le dossier passe par la réouverture ordinaire, ou refuse. La demande garde
l'état du dossier qu'elle visait. Voir ``expenses.workflow``.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0015_rectification"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReopenRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Modifié le")),
                ("status", models.CharField(choices=[("pending", "En attente"), ("approved", "Approuvée"), ("refused", "Refusée")], default="pending", max_length=20, verbose_name="Statut")),
                ("motif", models.TextField(verbose_name="Motif de la demande")),
                ("requested_by", models.CharField(blank=True, max_length=180, verbose_name="Demandée par")),
                ("decided_by", models.CharField(blank=True, max_length=180, verbose_name="Décidée par")),
                ("decided_at", models.DateTimeField(blank=True, null=True, verbose_name="Décidée le")),
                ("decision_note", models.TextField(blank=True, verbose_name="Motif de la décision")),
                ("previous_status", models.CharField(choices=[("draft", "Brouillon"), ("submitted", "Soumis"), ("in_review", "En contrôle"), ("justified", "Justifié"), ("unjustified", "Non justifié"), ("closed", "Clôturé")], max_length=20, verbose_name="État avant réouverture")),
                ("dossier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reopen_requests", to="expenses.dossier", verbose_name="Dossier")),
            ],
            options={
                "verbose_name": "Demande de réouverture",
                "verbose_name_plural": "Demandes de réouverture",
                "ordering": ["-created_at", "-pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="reopenrequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("dossier",),
                name="reopen_request_une_en_attente_par_dossier",
            ),
        ),
        migrations.AddConstraint(
            model_name="reopenrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(("status", "pending"), ("decided_at__isnull", False), _connector="OR"),
                name="reopen_request_decision_datee",
            ),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(choices=[("created", "Création"), ("updated", "Modification"), ("submitted", "Soumission"), ("reviewed", "Mise en contrôle"), ("justified", "Justification"), ("unjustified", "Constat de non-justification"), ("approved", "Validation d'un justificatif"), ("rejected", "Rejet d'un justificatif"), ("proof_incomplete", "Justificatif signalé incomplet"), ("proof_to_review", "Justificatif remis à contrôler"), ("deleted", "Suppression d'un brouillon"), ("closed", "Clôture"), ("reopened", "Réouverture"), ("rectification_requested", "Demande de rectification"), ("rectification_decided", "Décision sur une rectification"), ("rectified", "Rectification d'un constat"), ("reopen_requested", "Demande de réouverture"), ("reopen_decided", "Décision sur une réouverture"), ("proof_uploaded", "Dépôt de justificatif"), ("proof_replaced", "Remplacement de justificatif"), ("downloaded", "Téléchargement"), ("imported", "Import Excel")], max_length=32, verbose_name="Action"),
        ),
    ]
