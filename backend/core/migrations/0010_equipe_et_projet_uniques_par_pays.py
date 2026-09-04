"""Nom d'équipe et nom de projet uniques par pays.

Deux « Équipe Lomé » au Togo ne se distinguent ni à l'écran ni dans un
classeur importé : la ligne irait à l'une ou à l'autre au hasard. Avant de
poser la contrainte, les doublons déjà en base sont renommés — jamais
supprimés ni fusionnés : des dépenses, des enveloppes et des comptes y sont
peut-être rattachés, et rien ne se supprime. Le plus ancien garde son nom ;
les suivants reçoivent un suffixe « (2) », « (3) »… que l'administrateur
pourra corriger à la main.
"""

from django.db import migrations, models

LONGUEUR_MAX = 180


def _renommer_les_doublons(modele):
    """Renomme les homonymes d'un même pays, du plus ancien au plus récent."""
    vus = set()
    # ``pk`` en dernier : deux entités créées dans la même seconde doivent
    # être départagées de façon stable.
    for entite in modele.objects.order_by("country_id", "name", "created_at", "pk"):
        cle = (entite.country_id, entite.name)
        if cle not in vus:
            vus.add(cle)
            continue
        indice = 2
        while True:
            suffixe = f" ({indice})"
            nouveau = entite.name[: LONGUEUR_MAX - len(suffixe)] + suffixe
            if (entite.country_id, nouveau) not in vus and not modele.objects.filter(
                country_id=entite.country_id, name=nouveau
            ).exists():
                break
            indice += 1
        entite.name = nouveau
        # ``update`` plutôt que ``save`` : les signaux d'historisation ne
        # sont pas chargés dans une migration, et ``updated_at`` ne doit
        # pas laisser croire à une modification métier.
        modele.objects.filter(pk=entite.pk).update(name=nouveau)
        vus.add((entite.country_id, nouveau))


def dedoublonner(apps, schema_editor):
    _renommer_les_doublons(apps.get_model("core", "Team"))
    _renommer_les_doublons(apps.get_model("core", "Project"))


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_historique_immuable"),
    ]

    operations = [
        # Le renommage est irréversible par nature : revenir en arrière ne
        # recrée pas des doublons, il retire seulement la contrainte.
        migrations.RunPython(dedoublonner, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(
                fields=("country", "name"), name="unique_projet_par_pays"
            ),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=models.UniqueConstraint(
                fields=("country", "name"), name="unique_equipe_par_pays"
            ),
        ),
    ]
