"""Chaque dossier existant rejoint un projet (décisions 102 et 103).

Version 2.0 : un dossier appartient à un projet. Les dossiers d'avant n'en
avaient pas — le projet, facultatif, était porté par chaque ligne. Sans
rien deviner :

- un dossier dont **toutes** les lignes portent le **même** projet rejoint
  ce projet ;
- tout autre dossier — sans ligne, avec une ligne sans projet, ou des
  lignes de projets différents — rejoint le projet « Historique (avant
  2.0) » de son pays, créé pour l'occasion, sans type.

Les dossiers gardent leur N°ORDRE, sans type ni rang. **Les lignes ne sont
pas touchées** : ni leur projet, ni donc leur imputation sur une
sous-enveloppe de projet. Chaque dossier rangé laisse une entrée au journal
d'audit, chaque projet « Historique » une entrée d'historique.
"""

import django.db.models.deletion
from django.db import migrations, models

AUTEUR = "migration expenses.0019_dossiers_dans_un_projet"
NOM_HISTORIQUE = "Historique (avant 2.0)"
LOT = 500


def projet_historique(apps, country, traces):
    """Le projet « Historique » du pays, créé au besoin."""
    Project = apps.get_model("core", "Project")
    ChangeLog = apps.get_model("core", "ChangeLog")
    existant = Project.objects.filter(country=country, is_historical=True).first()
    if existant:
        return existant
    nom, rang = NOM_HISTORIQUE, 1
    # Le nom est unique par pays : un projet qui le porterait déjà garde le
    # sien, l'historique prend le suivant.
    while Project.objects.filter(country=country, name=nom).exists():
        rang += 1
        nom = f"{NOM_HISTORIQUE} ({rang})"
    projet = Project.objects.create(
        country=country, name=nom, is_historical=True, status="completed",
        reference=f"{country.code}-P-HIST",
        description="Dossiers ouverts avant la version 2.0, sans projet commun à leurs lignes.",
    )
    traces.append(ChangeLog(
        model_name="project", object_id=projet.pk, label=nom, action="created",
        country_id=country.pk, performed_by=AUTEUR, to_value=nom,
        diff={"name": [None, nom], "reference": [None, projet.reference]},
    ))
    return projet


def ranger_les_dossiers(apps, schema_editor):
    Country = apps.get_model("core", "Country")
    ChangeLog = apps.get_model("core", "ChangeLog")
    Dossier = apps.get_model("expenses", "Dossier")
    Expense = apps.get_model("expenses", "Expense")
    AuditLog = apps.get_model("expenses", "AuditLog")

    # Projets des lignes, par dossier : ``None`` pour une ligne sans projet.
    projets_des_lignes = {}
    for dossier_id, project_id in Expense.objects.values_list("dossier_id", "project_id"):
        projets_des_lignes.setdefault(dossier_id, set()).add(project_id)

    traces_historique, traces_audit, historiques = [], [], {}
    dossiers = list(Dossier.objects.filter(project__isnull=True).order_by("pk"))
    for dossier in dossiers:
        projets = projets_des_lignes.get(dossier.pk, set())
        if len(projets) == 1 and None not in projets:
            (dossier.project_id,) = projets
            motif = "Toutes ses lignes portaient ce projet."
        else:
            if dossier.country_id not in historiques:
                historiques[dossier.country_id] = projet_historique(
                    apps, Country.objects.get(pk=dossier.country_id), traces_historique
                )
            dossier.project_id = historiques[dossier.country_id].pk
            motif = "Ses lignes ne portaient pas un projet commun."
        traces_audit.append(AuditLog(
            user=AUTEUR, action="updated", object_type="Dossier",
            object_id=dossier.pk, label=dossier.number[:250],
            country_id=dossier.country_id,
            detail={"project": [None, dossier.project_id], "motif": motif},
        ))
    Dossier.objects.bulk_update(dossiers, ["project"], batch_size=LOT)
    ChangeLog.objects.bulk_create(traces_historique, batch_size=LOT)
    AuditLog.objects.bulk_create(traces_audit, batch_size=LOT)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_projets_types_et_numerotes"),
        ("expenses", "0018_contacts_des_beneficiaires"),
    ]

    operations = [
        migrations.AddField(
            model_name="dossier",
            name="external_ref",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="Référence d'origine"
            ),
        ),
        migrations.AddField(
            model_name="dossier",
            name="kind",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dossiers",
                to="core.dossierkind",
                verbose_name="Type de dossier",
            ),
        ),
        migrations.AddField(
            model_name="dossier",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dossiers",
                to="core.project",
                verbose_name="Projet",
            ),
        ),
        migrations.AddField(
            model_name="dossier",
            name="sequence",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Rang"
            ),
        ),
        migrations.AddConstraint(
            model_name="dossier",
            constraint=models.UniqueConstraint(
                condition=models.Q(("sequence__isnull", False)),
                fields=("project", "sequence"),
                name="unique_rang_de_dossier",
            ),
        ),
        migrations.AddConstraint(
            model_name="dossier",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_ref", ""), _negated=True),
                fields=("project", "external_ref"),
                name="unique_reference_d_origine_par_projet",
            ),
        ),
        migrations.RunPython(ranger_les_dossiers, migrations.RunPython.noop),
    ]
