"""Rattache les bénéficiaires à un pays.

Le référentiel était commun à tous les pays : un pays lisait les fournisseurs
et les prospects du voisin, de quoi reconstituer qui il démarche et qui il
paie. Le nom était unique globalement par-dessus le marché, si bien que deux
pays ne pouvaient pas déclarer le même fournisseur.

Le champ est ajouté sans valeur par défaut : la table est vide, aucune fiche
n'a donc à être rattachée à l'aveugle. Si elle ne l'était pas, il faudrait
d'abord décider à quel pays revient chaque bénéficiaire — ce qu'aucune valeur
par défaut ne saurait trancher.
"""

import django.db.models.deletion
from django.db import migrations, models


def refuser_si_des_fiches_existent(apps, schema_editor):
    Beneficiary = apps.get_model("expenses", "Beneficiary")
    if Beneficiary.objects.exists():
        raise RuntimeError(
            "Des bénéficiaires existent : rattachez-les d'abord à un pays. "
            "Aucun rattachement automatique n'est possible sans deviner."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_valide_code_pays_africain"),
        ("expenses", "0003_statuts_justification"),
    ]

    operations = [
        migrations.RunPython(
            refuser_si_des_fiches_existent, migrations.RunPython.noop
        ),
        # Le nom n'est plus unique globalement : deux pays peuvent déclarer
        # le même fournisseur.
        migrations.AlterField(
            model_name="beneficiary",
            name="name",
            field=models.CharField(max_length=180, verbose_name="Nom"),
        ),
        migrations.AddField(
            model_name="beneficiary",
            name="country",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="beneficiaries",
                to="core.country",
                verbose_name="Pays",
                # Pas de défaut : la table est vide (contrôlé ci-dessus).
                null=False,
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="beneficiary",
            constraint=models.UniqueConstraint(
                fields=("country", "name"), name="unique_beneficiaire_par_pays"
            ),
        ),
    ]
