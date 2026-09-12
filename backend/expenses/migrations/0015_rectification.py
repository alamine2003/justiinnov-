"""Demande de rectification d'un constat (seconde exception à l'irréversibilité).

Une ligne justifiée ou clôturée ne se rouvre pas ; elle peut être rectifiée,
en deux temps : une demande motivée par n'importe qui, une décision d'un
administrateur — jamais l'auteur de la demande. Approuvée, la ligne revient
en contrôle ; la demande garde l'état et le montant justifié qu'elle défait.
Voir ``expenses.workflow``.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0014_ligne_importee_unique"),
    ]

    operations = [
        migrations.CreateModel(
            name="Rectification",
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
                ("previous_status", models.CharField(choices=[("draft", "Brouillon"), ("submitted", "Soumis"), ("in_review", "En contrôle"), ("justified", "Justifié"), ("unjustified", "Non justifié"), ("closed", "Clôturé")], max_length=20, verbose_name="État avant rectification")),
                ("previous_justified_amount", models.DecimalField(decimal_places=2, max_digits=16, verbose_name="Montant justifié avant rectification")),
                ("expense", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rectifications", to="expenses.expense", verbose_name="Dépense")),
            ],
            options={
                "verbose_name": "Demande de rectification",
                "verbose_name_plural": "Demandes de rectification",
                "ordering": ["-created_at", "-pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="rectification",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("expense",),
                name="rectification_une_en_attente_par_ligne",
            ),
        ),
        migrations.AddConstraint(
            model_name="rectification",
            constraint=models.CheckConstraint(
                condition=models.Q(("status", "pending"), ("decided_at__isnull", False), _connector="OR"),
                name="rectification_decision_datee",
            ),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(choices=[("created", "Création"), ("updated", "Modification"), ("submitted", "Soumission"), ("reviewed", "Mise en contrôle"), ("justified", "Justification"), ("unjustified", "Constat de non-justification"), ("approved", "Validation d'un justificatif"), ("rejected", "Rejet d'un justificatif"), ("proof_incomplete", "Justificatif signalé incomplet"), ("proof_to_review", "Justificatif remis à contrôler"), ("deleted", "Suppression d'un brouillon"), ("closed", "Clôture"), ("reopened", "Réouverture"), ("rectification_requested", "Demande de rectification"), ("rectification_decided", "Décision sur une rectification"), ("rectified", "Rectification d'un constat"), ("proof_uploaded", "Dépôt de justificatif"), ("proof_replaced", "Remplacement de justificatif"), ("downloaded", "Téléchargement"), ("imported", "Import Excel")], max_length=32, verbose_name="Action"),
        ),
    ]
