"""Suppression des fichiers après le commit, avec reprise.

Le fichier d'une pièce retirée avec son brouillon ne s'efface plus dans la
transaction : la demande est enregistrée ici, exécutée après le commit et
reprise par l'ordonnanceur si le stockage n'a pas répondu.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_matrice_des_droits"),
        ("expenses", "0012_piece_unique_par_dossier"),
    ]

    operations = [
        migrations.CreateModel(
            name="FichierASupprimer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=500, unique=True, verbose_name="Chemin dans le stockage")),
                ("sha256", models.CharField(blank=True, max_length=64, verbose_name="Empreinte SHA-256")),
                ("dossier_number", models.CharField(blank=True, max_length=50, verbose_name="N° d'ordre du dossier")),
                ("requested_by", models.CharField(blank=True, max_length=180, verbose_name="Demandé par")),
                ("requested_at", models.DateTimeField(auto_now_add=True, verbose_name="Demandé le")),
                ("attempted_at", models.DateTimeField(blank=True, null=True, verbose_name="Dernier essai le")),
                ("attempts", models.PositiveSmallIntegerField(default=0, verbose_name="Essais")),
                ("deleted_at", models.DateTimeField(blank=True, null=True, verbose_name="Effacé le")),
                ("last_error", models.TextField(blank=True, verbose_name="Dernière erreur")),
                ("country", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="core.country", verbose_name="Pays")),
            ],
            options={
                "verbose_name": "Fichier à supprimer",
                "verbose_name_plural": "Fichiers à supprimer",
                "ordering": ["-requested_at", "-pk"],
            },
        ),
        migrations.AddIndex(
            model_name="fichierasupprimer",
            index=models.Index(
                condition=models.Q(("deleted_at__isnull", True)),
                fields=["attempted_at"],
                name="fichier_a_supprimer_idx",
            ),
        ),
    ]
