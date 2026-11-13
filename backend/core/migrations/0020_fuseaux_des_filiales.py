"""Chaque pays retrouve son fuseau horaire (décision 128).

Le fuseau était un texte libre : en production, le Bénin et le Congo ont été
ouverts en « UTC » et le Gabon en « GMT », alors qu'ils vivent à UTC+1.
L'heure, le jour, le mois et l'exercice d'une dépense se lisent dans le
fuseau de son pays : ils se lisaient une heure trop tôt.

Un pays dont le fuseau n'est pas l'un des siens reçoit son fuseau officiel.
Un pays déjà juste n'est pas touché — la RDC à Lubumbashi le reste. Chaque
correction laisse une entrée dans l'historique, avec l'ancien fuseau et le
nouveau.

Conséquence assumée : les dépenses déjà saisies dans ces pays s'affichent
désormais une heure plus tard, et une ligne saisie entre 23 h et minuit y
change de jour. Aucun montant ne bouge.

La table est une copie figée de ``core.africa.FUSEAUX`` à la 2.4.7 : une
migration ne doit pas changer de sens le jour où la liste des filiales
évolue.
"""

from django.db import migrations

AUTEUR = "migration core.0020_fuseaux_des_filiales"
MOTIF = "Fuseau qui n'était pas celui du pays, remplacé par son fuseau officiel (décision 128)."

#: Code du pays → ses fuseaux, le premier étant l'officiel.
FUSEAUX = {
    "BF": ("Africa/Ouagadougou",),
    "BJ": ("Africa/Porto-Novo",),
    "CD": ("Africa/Kinshasa", "Africa/Lubumbashi"),
    "CG": ("Africa/Brazzaville",),
    "CI": ("Africa/Abidjan",),
    "CM": ("Africa/Douala",),
    "DJ": ("Africa/Djibouti",),
    "GA": ("Africa/Libreville",),
    "GM": ("Africa/Banjul",),
    "GN": ("Africa/Conakry",),
    "MG": ("Indian/Antananarivo",),
    "ML": ("Africa/Bamako",),
    "MR": ("Africa/Nouakchott",),
    "NE": ("Africa/Niamey",),
    "SN": ("Africa/Dakar",),
    "TD": ("Africa/Ndjamena",),
    "TG": ("Africa/Lome",),
}


def corriger_les_fuseaux(apps, schema_editor):
    Country = apps.get_model("core", "Country")
    ChangeLog = apps.get_model("core", "ChangeLog")
    for pays in Country.objects.order_by("pk"):
        acceptes = FUSEAUX.get(pays.code)
        # Hors des filiales, ou déjà juste : rien à corriger.
        if not acceptes or pays.timezone in acceptes:
            continue
        ancien, nouveau = pays.timezone, acceptes[0]
        Country.objects.filter(pk=pays.pk).update(timezone=nouveau)
        ChangeLog.objects.create(
            model_name="country",
            object_id=pays.pk,
            label=pays.name[:250],
            action="updated",
            country_id=pays.pk,
            from_value=ancien,
            to_value=nouveau,
            changed_fields=["timezone"],
            diff={"timezone": [ancien, nouveau]},
            performed_by=AUTEUR,
            motif=MOTIF,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_interrupteur_de_la_corbeille"),
    ]

    operations = [
        # Sans retour : l'ancien fuseau était faux, et il reste à l'historique.
        migrations.RunPython(corriger_les_fuseaux, migrations.RunPython.noop),
    ]
