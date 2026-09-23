"""Les brouillons ouverts par le siège reviennent au pays (décision 89).

Le siège ne déclare plus : ni l'administrateur ni le super administrateur
ne créent de dossier, ne saisissent de ligne ni ne soumettent. Un brouillon
qu'ils avaient ouvert — à la main ou par l'import Excel — resterait sinon
sans personne pour le finir : son auteur n'a plus le droit de le modifier,
et le pays n'est pas son auteur (décision 46).

Ces brouillons perdent donc leur auteur (``created_by`` vide) : un
brouillon sans auteur connu se complète et se soumet par le pays, comme un
brouillon dont l'auteur a disparu. Un brouillon n'a pas de valeur probante ;
ce qui est déclaré n'est pas touché. L'ancien auteur reste lisible dans le
journal d'audit : une entrée par objet repris, avec l'avant et l'après.
"""

from django.db import migrations

ROLES_DU_SIEGE = ("super_admin", "admin")
AUTEUR = "migration expenses.0017_brouillons_du_siege_rendus_au_pays"


def rendre_au_pays(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    AuditLog = apps.get_model("expenses", "AuditLog")
    siege = set(
        UserProfile.objects.filter(role__in=ROLES_DU_SIEGE).values_list(
            "user__username", flat=True
        )
    )
    if not siege:
        return
    for nom in ("Dossier", "Expense"):
        Modele = apps.get_model("expenses", nom)
        for objet in (
            Modele.objects.filter(status="draft", created_by__in=siege)
            .select_related("country")
            .order_by("pk")
        ):
            ancien = objet.created_by
            objet.created_by = ""
            objet.save(update_fields=["created_by"])
            AuditLog(
                user=AUTEUR,
                action="updated",
                object_type=nom,
                object_id=objet.pk,
                label=str(getattr(objet, "number", "") or getattr(objet, "title", ""))[:250],
                country=objet.country,
                detail={
                    "created_by": [ancien, ""],
                    "motif": "Brouillon ouvert par le siège, rendu au pays (décision 89).",
                },
            ).save()


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0016_index_de_tri_des_listes"),
        ("accounts", "0006_trois_roles"),
    ]

    operations = [
        migrations.RunPython(rendre_au_pays, migrations.RunPython.noop),
    ]
