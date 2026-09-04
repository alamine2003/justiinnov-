"""Configuration du workflow : un singleton, amorcé depuis l'environnement.

Les défauts des colonnes sont ceux du modèle, littéraux : une valeur
d'environnement lue au moment de ``makemigrations`` se figerait sinon dans
le fichier. L'environnement n'intervient que dans ``creer_configuration``,
une seule fois, à la création de l'unique ligne.
"""

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


def seuils_par_defaut():
    return [80, 90, 100]


def creer_configuration(apps, schema_editor):
    configuration = apps.get_model("core", "WorkflowConfiguration")
    configuration.objects.get_or_create(
        pk=1,
        defaults={
            "alert_thresholds": list(settings.ALERT_THRESHOLDS),
            "unusual_expense_factor": Decimal(str(settings.UNUSUAL_EXPENSE_FACTOR)),
            "unjustified_alert_days": settings.UNJUSTIFIED_ALERT_DAYS,
            "warn_without_proof_submission": settings.WARN_WITHOUT_PROOF_SUBMISSION,
        },
    )


def ne_pas_revenir_en_arriere(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("core", "0006_valide_code_pays_africain")]

    operations = [
        migrations.CreateModel(
            name="WorkflowConfiguration",
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
                    "require_review_step",
                    models.BooleanField(
                        default=False, verbose_name="Étape de contrôle obligatoire"
                    ),
                ),
                (
                    "unjustified_alert_days",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="Délai d'alerte sans justification",
                    ),
                ),
                (
                    "alert_thresholds",
                    models.JSONField(default=seuils_par_defaut, verbose_name="Seuils d'alerte"),
                ),
                (
                    "unusual_expense_factor",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("5"),
                        max_digits=8,
                        verbose_name="Facteur de dépense inhabituelle",
                    ),
                ),
                (
                    "default_overrun_policy",
                    models.CharField(
                        choices=[
                            ("block", "Bloquer"),
                            ("warn", "Alerter"),
                            ("approval", "Soumettre à approbation"),
                        ],
                        default="block",
                        max_length=20,
                        verbose_name="Politique de dépassement par défaut",
                    ),
                ),
                (
                    "warn_without_proof_submission",
                    models.BooleanField(
                        default=True,
                        verbose_name="Avertir à la soumission sans pièce",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Modifié le")),
            ],
            options={"verbose_name": "Configuration du workflow"},
        ),
        migrations.AlterField(
            model_name="changelog",
            name="model_name",
            field=models.CharField(
                choices=[
                    ("country", "Pays"),
                    ("manager", "Manager"),
                    ("team", "Équipe"),
                    ("cost_center", "Centre de coûts"),
                    ("project", "Projet"),
                    ("expense_title", "Intitulé de dépenses"),
                    ("marketing_category", "Catégorie marketing"),
                    ("budget", "Enveloppe budgétaire"),
                    ("reallocation", "Réallocation budgétaire"),
                    ("exchange_rate", "Taux de change"),
                    ("workflow_configuration", "Configuration du workflow"),
                ],
                max_length=32,
                verbose_name="Entité",
            ),
        ),
        migrations.RunPython(creer_configuration, ne_pas_revenir_en_arriere),
    ]
