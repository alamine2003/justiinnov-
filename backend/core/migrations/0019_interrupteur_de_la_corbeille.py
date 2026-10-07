"""L'interrupteur de la corbeille du super administrateur (décision 120).

Fermé par défaut, en base aussi (``db_default``) : une migration plus
ancienne qui écrit la configuration sans connaître le champ — les tests de
reprise en rejouent — ne doit pas buter sur la colonne.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_types_de_projets_en_base"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowconfiguration",
            name="suppressions_ouvertes",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Suppressions ouvertes (corbeille)"
            ),
        ),
    ]
