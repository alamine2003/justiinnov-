"""Identité d'une ligne importée, tranchée en base.

Deux imports simultanés du même classeur validaient chacun de leur côté
puis écrivaient tous deux : toutes les lignes existaient deux fois. Chaque
ligne importée porte désormais l'empreinte de ce qui la définit — jour,
libellé, montant — et la base refuse la seconde dans le même dossier.
Les lignes existantes gardent une empreinte vide : rien ne distingue une
ligne importée d'une ligne saisie, et deux dépenses saisies identiques
sont deux dépenses. Les doublons déjà présents se listent avec
``manage.py doublons_importes`` ; ils ne se suppriment pas d'ici.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0013_fichier_a_supprimer"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="import_key",
            field=models.CharField(
                blank=True, editable=False, max_length=64, null=True,
                verbose_name="Empreinte d'import",
            ),
        ),
        migrations.AddConstraint(
            model_name="expense",
            constraint=models.UniqueConstraint(
                condition=models.Q(("import_key__isnull", False)),
                fields=("dossier", "import_key"),
                name="ligne_importee_unique_par_dossier",
            ),
        ),
    ]
