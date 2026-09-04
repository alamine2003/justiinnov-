"""Type de notification « Dossier rouvert ».

La réouverture d'un dossier déclaré est la seule exception à
l'irréversibilité : le pays doit en être prévenu sous un type qui lui est
propre, et non sous « Dépense rejetée » faute de mieux.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_index_dedup_key'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='kind',
            field=models.CharField(choices=[('budget_threshold', 'Seuil budgétaire atteint'), ('budget_overrun', 'Dépassement budgétaire'), ('expense_submitted', 'Dépense à contrôler'), ('expense_rejected', 'Dépense rejetée'), ('proof_missing', 'Justificatif manquant'), ('proof_incomplete', 'Justificatif incomplet'), ('reallocation_requested', 'Demande de réallocation'), ('storage_error', 'Anomalie de stockage'), ('dossier_reopened', 'Dossier rouvert')], max_length=32, verbose_name='Type'),
        ),
    ]
