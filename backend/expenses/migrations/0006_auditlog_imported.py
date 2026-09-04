from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("expenses", "0005_devise_du_decaissement")]

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
                    ("deleted", "Suppression d'un brouillon"),
                    ("closed", "Clôture"),
                    ("proof_uploaded", "Dépôt de justificatif"),
                    ("proof_replaced", "Remplacement de justificatif"),
                    ("downloaded", "Téléchargement"),
                    ("imported", "Import Excel"),
                ],
                max_length=32,
                verbose_name="Action",
            ),
        )
    ]
