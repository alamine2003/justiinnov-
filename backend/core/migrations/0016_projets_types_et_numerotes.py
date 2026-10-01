"""Projets typés et numérotés, types de dossiers (décisions 100, 101, 103).

Version 2.0 : le projet devient la rubrique principale et contient des
dossiers typés. Cette migration :

- crée la liste **commune** des types de dossiers, celle que la direction a
  donnée (congrès : Stands, T-shirts, Collations, Voyages ; voyage :
  Billets, Carburant, Hôtellerie, Repas, Forfait ; soutien financier :
  Soutien financier) ; le siège la complète ensuite dans la configuration ;
- **numérote les projets existants** dans l'ordre de leur création :
  ``TG-P-2025-001``, l'année étant celle de la création. Ils restent sans
  type — « à typer » — : rien ne permet de deviner s'ils étaient un congrès
  ou un voyage, et un projet sans type n'accepte pas de nouveau dossier
  tant que le siège ne l'a pas typé.

Chaque objet créé ou numéroté laisse une entrée d'historique, signée par
la migration. Les dossiers sont rangés par ``expenses.0019``.
"""

from django.db import migrations, models

AUTEUR = "migration core.0016_projets_types_et_numerotes"

TYPES_DE_DOSSIERS = {
    "congres": ("Stands", "T-shirts", "Collations", "Voyages"),
    "voyage": ("Billets", "Carburant", "Hôtellerie", "Repas", "Forfait"),
    "soutien_financier": ("Soutien financier",),
}


def reference_de_projet(code, annee, rang):
    """``TG-P-2026-001`` — même format que ``core.numerotation``."""
    return f"{code}-P-{annee}-{rang:03d}"


def reprendre(apps, schema_editor):
    ChangeLog = apps.get_model("core", "ChangeLog")
    DossierKind = apps.get_model("core", "DossierKind")
    Project = apps.get_model("core", "Project")
    traces = []

    for project_kind, noms in TYPES_DE_DOSSIERS.items():
        for nom in noms:
            kind, cree = DossierKind.objects.get_or_create(
                project_kind=project_kind, name=nom
            )
            if cree:
                traces.append(ChangeLog(
                    model_name="dossier_kind", object_id=kind.pk, label=nom,
                    action="created", to_value=nom, performed_by=AUTEUR,
                    diff={"project_kind": [None, project_kind], "name": [None, nom]},
                ))

    rangs = {}
    projets = Project.objects.select_related("country").filter(
        reference__isnull=True, is_historical=False
    ).order_by("created_at", "pk")
    for projet in projets:
        annee = projet.created_at.year
        cle = (projet.country_id, annee)
        rangs[cle] = rangs.get(cle, 0) + 1
        projet.year = annee
        projet.sequence = rangs[cle]
        projet.reference = reference_de_projet(projet.country.code, annee, rangs[cle])
        projet.save(update_fields=["year", "sequence", "reference"])
        traces.append(ChangeLog(
            model_name="project", object_id=projet.pk, label=projet.name[:250],
            action="updated", country_id=projet.country_id, performed_by=AUTEUR,
            changed_fields=["reference"], to_value=projet.reference,
            diff={"reference": [None, projet.reference]},
        ))
    ChangeLog.objects.bulk_create(traces, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_historique_des_beneficiaires"),
    ]

    operations = [
        migrations.CreateModel(
            name="DossierKind",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Créé le"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Modifié le"),
                ),
                (
                    "project_kind",
                    models.CharField(
                        choices=[
                            ("congres", "Congrès"),
                            ("voyage", "Voyage"),
                            ("soutien_financier", "Soutien financier"),
                        ],
                        max_length=24,
                        verbose_name="Type de projet",
                    ),
                ),
                ("name", models.CharField(max_length=120, verbose_name="Nom")),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Description"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
            ],
            options={
                "verbose_name": "Type de dossier",
                "verbose_name_plural": "Types de dossiers",
                "ordering": ["project_kind", "name", "pk"],
            },
        ),
        migrations.AddField(
            model_name="project",
            name="is_historical",
            field=models.BooleanField(default=False, verbose_name="Projet historique"),
        ),
        migrations.AddField(
            model_name="project",
            name="kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("congres", "Congrès"),
                    ("voyage", "Voyage"),
                    ("soutien_financier", "Soutien financier"),
                ],
                max_length=24,
                verbose_name="Type de projet",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="reference",
            field=models.CharField(
                blank=True,
                max_length=32,
                null=True,
                unique=True,
                verbose_name="Référence",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="sequence",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Rang"
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="year",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Année"
            ),
        ),
        migrations.AlterField(
            model_name="changelog",
            name="model_name",
            field=models.CharField(
                choices=[
                    ("country", "Pays"),
                    ("manager", "Manager"),
                    ("team", "Équipe"),
                    ("cost_center", "Centre de coûts"),
                    ("project", "Projet"),
                    ("expense_title", "Intitulé de dépenses"),
                    ("marketing_category", "Catégorie marketing"),
                    ("budget", "Enveloppe budgétaire"),
                    ("reallocation", "Réallocation budgétaire"),
                    ("exchange_rate", "Taux de change"),
                    ("workflow_configuration", "Configuration du workflow"),
                    ("user", "Compte utilisateur"),
                    ("beneficiary", "Bénéficiaire"),
                    ("dossier_kind", "Type de dossier"),
                ],
                max_length=32,
                verbose_name="Entité",
            ),
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(
                condition=models.Q(("sequence__isnull", False)),
                fields=("country", "year", "sequence"),
                name="unique_rang_de_projet",
            ),
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_historical", True)),
                fields=("country",),
                name="un_projet_historique_par_pays",
            ),
        ),
        migrations.AddConstraint(
            model_name="dossierkind",
            constraint=models.UniqueConstraint(
                fields=("project_kind", "name"), name="unique_type_de_dossier"
            ),
        ),
        migrations.RunPython(reprendre, migrations.RunPython.noop),
    ]
