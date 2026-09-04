"""Le N°ORDRE devient unique par pays, et non plus globalement.

Le classeur du client numérote ses dossiers de 1 à n **dans chaque pays** :
une unicité globale refusait le « 12 » du Togo dès que la Côte d'Ivoire
avait le sien, et le message trahissait au passage l'existence du dossier
voisin. Aucune reprise de données n'est nécessaire : ce qui était unique
globalement l'est a fortiori par pays.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0008_journal_d_audit_immuable"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dossier",
            name="number",
            field=models.CharField(max_length=50, verbose_name="N° d'ordre"),
        ),
        migrations.AddConstraint(
            model_name="dossier",
            constraint=models.UniqueConstraint(
                fields=("country", "number"), name="unique_dossier_par_pays"
            ),
        ),
    ]
