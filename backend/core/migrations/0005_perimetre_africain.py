"""Restreint la plateforme aux pays africains et retire les pays d'essai.

La base contenait la France et la Belgique, restes des jeux d'essai antérieurs
au cadrage du projet. Elles apparaissaient dans les listes, dans le sélecteur
de pays du siège, et faussaient la consolidation : leur devise n'a aucun taux
publié vers le FCFA.

Le retrait est conditionnel. Un pays hors périmètre qui porterait un budget, un
dossier, une dépense ou un compte n'est pas supprimé mais désactivé : rien de
ce qui a une valeur probante ne disparaît, conformément à la règle du projet.
Seule une fiche vide, qui ne prouve rien, s'efface.
"""

from django.db import migrations

from core.africa import AFRICAN_COUNTRY_CODES


def _porte_des_donnees(country):
    """Un pays porte-t-il quoi que ce soit qu'on ne puisse pas perdre ?"""
    return any(
        [
            country.budgets.exists(),
            country.dossiers.exists(),
            country.expenses.exists(),
            country.profiles.exists(),
        ]
    )


def retirer_les_pays_hors_afrique(apps, schema_editor):
    Country = apps.get_model("core", "Country")
    ChangeLog = apps.get_model("core", "ChangeLog")

    for country in Country.objects.all():
        if (country.code or "").upper() in AFRICAN_COUNTRY_CODES:
            continue

        if _porte_des_donnees(country):
            # Trace conservée : la fiche reste, inactive et invisible des
            # listes courantes, mais son historique reste consultable.
            if country.is_active:
                country.is_active = False
                country.save(update_fields=["is_active"])
                _journaliser(ChangeLog, country, "deactivated")
        else:
            # Les signaux ne se déclenchent pas sur un modèle historique : la
            # trace doit être écrite ici, sans quoi le pays disparaîtrait des
            # listes sans que rien n'explique pourquoi.
            _journaliser(ChangeLog, country, "deleted")
            country.delete()


def _journaliser(ChangeLog, country, action):
    ChangeLog.objects.create(
        model_name="country",
        object_id=country.pk,
        label=country.name,
        action=action,
        # Volontairement sans `country=` : la ligne survit à la fiche
        # supprimée, une clé étrangère la ferait passer à NULL sans intérêt.
        from_value=f"{country.name} ({country.code})",
        to_value="",
        changed_fields=[],
        performed_by="migration 0005 — périmètre africain",
    )


def restaurer(apps, schema_editor):
    """Rien à restaurer : les pays d'essai n'ont pas à revenir.

    Le sens inverse existe pour que la migration soit réversible sans erreur,
    pas pour recréer des données qui n'auraient pas dû exister.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_changelog_model_name"),
        # Les compteurs ci-dessus traversent ces applications : leurs tables
        # doivent exister avant que la migration ne les interroge.
        ("accounts", "0001_initial"),
        ("budget", "0002_remove_budget_unique_enveloppe_pays_annee_and_more"),
        ("expenses", "0003_statuts_justification"),
    ]

    operations = [
        migrations.RunPython(retirer_les_pays_hors_afrique, restaurer),
    ]
