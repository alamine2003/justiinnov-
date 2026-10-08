"""La corbeille du super administrateur (décision 120).

Ce qui part à la corbeille y garde une copie figée. Comme le journal
d'audit (``0008_journal_d_audit_immuable``, dont la fonction est reprise),
la base refuse toute modification et toute suppression d'une ligne : la
corbeille ne se vide pas, quel que soit le chemin d'écriture.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_interrupteur_de_la_corbeille"),
        ("expenses", "0022_remise_a_zero_des_essais"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("created", "Création"),
                    ("updated", "Modification"),
                    ("submitted", "Soumission"),
                    ("reviewed", "Mise en contrôle"),
                    ("justified", "Justification"),
                    ("unjustified", "Constat de non-justification"),
                    ("approved", "Validation d'un justificatif"),
                    ("rejected", "Rejet d'un justificatif"),
                    ("proof_incomplete", "Justificatif signalé incomplet"),
                    ("proof_to_review", "Justificatif remis à contrôler"),
                    ("deleted", "Suppression d'un brouillon"),
                    ("closed", "Clôture"),
                    ("reopened", "Réouverture"),
                    ("rectification_requested", "Demande de rectification"),
                    ("rectification_decided", "Décision sur une rectification"),
                    ("rectified", "Rectification d'un constat"),
                    ("proof_uploaded", "Dépôt de justificatif"),
                    ("proof_replaced", "Remplacement de justificatif"),
                    ("downloaded", "Téléchargement"),
                    ("imported", "Import Excel"),
                    ("renamed", "Renommage"),
                    ("purged", "Remise à zéro des essais"),
                    ("trashed", "Mise à la corbeille"),
                ],
                max_length=32,
                verbose_name="Action",
            ),
        ),
        migrations.CreateModel(
            name="ElementSupprime",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "nature",
                    models.CharField(
                        choices=[
                            ("projet", "Projet"),
                            ("dossier", "Dossier"),
                            ("ligne", "Ligne de dépense"),
                            ("piece", "Justificatif"),
                        ],
                        max_length=16,
                        verbose_name="Nature",
                    ),
                ),
                (
                    "objet_id",
                    models.PositiveBigIntegerField(
                        verbose_name="Identifiant d'origine"
                    ),
                ),
                (
                    "reference",
                    models.CharField(
                        blank=True, max_length=64, verbose_name="Référence"
                    ),
                ),
                (
                    "libelle",
                    models.CharField(
                        blank=True, max_length=250, verbose_name="Libellé"
                    ),
                ),
                (
                    "montant",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=16,
                        null=True,
                        verbose_name="Montant",
                    ),
                ),
                (
                    "devise",
                    models.CharField(blank=True, max_length=3, verbose_name="Devise"),
                ),
                ("donnees", models.JSONField(default=dict, verbose_name="Données")),
                (
                    "fichier",
                    models.CharField(
                        blank=True, max_length=500, verbose_name="Fichier"
                    ),
                ),
                (
                    "sha256",
                    models.CharField(
                        blank=True, max_length=64, verbose_name="Empreinte SHA-256"
                    ),
                ),
                ("motif", models.TextField(verbose_name="Motif")),
                (
                    "supprime_par",
                    models.CharField(
                        max_length=180, verbose_name="Mis à la corbeille par"
                    ),
                ),
                (
                    "supprime_le",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Mis à la corbeille le"
                    ),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(
                        blank=True, null=True, verbose_name="Adresse IP"
                    ),
                ),
                (
                    "country",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="core.country",
                        verbose_name="Pays",
                    ),
                ),
                (
                    "racine",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="emportes",
                        to="expenses.elementsupprime",
                        verbose_name="Retiré avec",
                    ),
                ),
            ],
            options={
                "verbose_name": "Élément de la corbeille",
                "verbose_name_plural": "Corbeille",
                "ordering": ["-supprime_le", "-pk"],
                "indexes": [
                    models.Index(
                        fields=["country", "supprime_le"], name="corbeille_pays_date"
                    ),
                    models.Index(fields=["nature", "objet_id"], name="corbeille_objet"),
                ],
            },
        ),
        migrations.RunSQL(
            """
            CREATE TRIGGER corbeille_immuable
              BEFORE UPDATE OR DELETE ON expenses_elementsupprime
              FOR EACH ROW EXECUTE FUNCTION refuser_modification_journal();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS corbeille_immuable ON expenses_elementsupprime;",
        ),
    ]
