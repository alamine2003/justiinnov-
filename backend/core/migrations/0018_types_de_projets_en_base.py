"""Types de projets en base, réglables par le super administrateur (décision 119).

Jusqu'ici le type d'un projet était une liste figée dans le code
(``congres``, ``voyage``, ``soutien_financier``). Il devient une table,
``ProjectType``, que le super administrateur complète dans « Configuration
› Types de projets ». Cette migration :

- crée la table et ses **trois types d'origine**, sous leurs codes d'avant
  — les colonnes ``Project.kind`` et ``DossierKind.project_kind`` gardent
  leurs valeurs, rien n'est réécrit dans les projets ni dans les types de
  dossiers ; les noms anglais sont ceux du catalogue de traduction ;
- passe à ``NULL`` le type vide des projets non typés (« Historique » et
  projets d'avant la 2.0) : une clé étrangère ne vise pas ``""`` ;
- change les deux colonnes en clés étrangères vers ``ProjectType.code`` ;
- donne un **ordre** aux types de dossiers, celui du nom, qui était déjà
  l'ordre de leurs dossiers prédéfinis.

Chaque type créé laisse une entrée d'historique, signée par la migration.
"""

from django.db import migrations, models
import django.db.models.deletion

AUTEUR = "migration core.0018_types_de_projets_en_base"

TYPES_D_ORIGINE = (
    ("congres", "Congrès", "Congress"),
    ("voyage", "Voyage", "Trip"),
    ("soutien_financier", "Soutien financier", "Financial support"),
)


def creer_les_types(apps, schema_editor):
    ChangeLog = apps.get_model("core", "ChangeLog")
    ProjectType = apps.get_model("core", "ProjectType")
    traces = []
    for ordre, (code, nom, nom_en) in enumerate(TYPES_D_ORIGINE, start=1):
        type_, cree = ProjectType.objects.get_or_create(
            code=code, defaults={"name": nom, "name_en": nom_en, "ordre": ordre}
        )
        if cree:
            traces.append(ChangeLog(
                model_name="project_type", object_id=type_.pk, label=nom,
                action="created", to_value=nom, performed_by=AUTEUR,
                diff={"code": [None, code], "name": [None, nom], "name_en": [None, nom_en]},
            ))
    ChangeLog.objects.bulk_create(traces)


def vider_les_types_vides(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    Project.objects.filter(kind="").update(kind=None)


def remettre_les_types_vides(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    Project.objects.filter(kind__isnull=True).update(kind="")


def ordonner_les_types_de_dossiers(apps, schema_editor):
    DossierKind = apps.get_model("core", "DossierKind")
    rangs = {}
    for kind in DossierKind.objects.order_by("project_kind", "name", "pk"):
        rangs[kind.project_kind] = rangs.get(kind.project_kind, 0) + 1
        kind.ordre = rangs[kind.project_kind]
        kind.save(update_fields=["ordre"])


def contraintes_immediates(apps, schema_editor):
    # Les mises à jour ci-dessus laissent des déclencheurs différés en
    # attente ; PostgreSQL refuse alors de modifier la table.
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_motif_de_l_historique"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Modifié le")),
                ("code", models.SlugField(editable=False, max_length=24, unique=True, verbose_name="Code")),
                ("name", models.CharField(max_length=80, unique=True, verbose_name="Nom")),
                ("name_en", models.CharField(blank=True, max_length=80, verbose_name="Nom en anglais")),
                ("description", models.TextField(blank=True, verbose_name="Description")),
                ("ordre", models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
            ],
            options={
                "verbose_name": "Type de projet",
                "verbose_name_plural": "Types de projets",
                "ordering": ["ordre", "name", "pk"],
            },
        ),
        migrations.AlterField(
            model_name="changelog",
            name="model_name",
            field=models.CharField(
                choices=[
                    ("country", "Pays"), ("manager", "Manager"), ("team", "Équipe"),
                    ("cost_center", "Centre de coûts"), ("project", "Projet"),
                    ("expense_title", "Intitulé de dépenses"),
                    ("marketing_category", "Catégorie marketing"),
                    ("budget", "Enveloppe budgétaire"),
                    ("reallocation", "Réallocation budgétaire"),
                    ("exchange_rate", "Taux de change"),
                    ("workflow_configuration", "Configuration du workflow"),
                    ("user", "Compte utilisateur"), ("beneficiary", "Bénéficiaire"),
                    ("dossier_kind", "Type de dossier"), ("project_type", "Type de projet"),
                ],
                max_length=32,
                verbose_name="Entité",
            ),
        ),
        migrations.RunPython(creer_les_types, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="project",
            name="kind",
            field=models.CharField(blank=True, max_length=24, null=True, verbose_name="Type de projet"),
        ),
        migrations.RunPython(vider_les_types_vides, remettre_les_types_vides),
        migrations.RunPython(contraintes_immediates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="project",
            name="kind",
            field=models.ForeignKey(
                blank=True, db_column="kind", null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name="projects",
                to="core.projecttype", to_field="code", verbose_name="Type de projet",
            ),
        ),
        migrations.AlterField(
            model_name="dossierkind",
            name="project_kind",
            field=models.ForeignKey(
                db_column="project_kind", on_delete=django.db.models.deletion.PROTECT,
                related_name="dossier_kinds", to="core.projecttype", to_field="code",
                verbose_name="Type de projet",
            ),
        ),
        migrations.AddField(
            model_name="dossierkind",
            name="ordre",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Ordre"),
        ),
        migrations.RunPython(ordonner_les_types_de_dossiers, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="dossierkind",
            options={
                "ordering": ["project_kind__ordre", "project_kind__name", "ordre", "name", "pk"],
                "verbose_name": "Type de dossier",
                "verbose_name_plural": "Types de dossiers",
            },
        ),
    ]
