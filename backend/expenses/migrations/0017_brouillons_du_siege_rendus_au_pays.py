"""Les brouillons ouverts par le siège reviennent au pays (décision 89).

Le siège ne déclare plus : ni l'administrateur ni le super administrateur
ne créent de dossier, ne saisissent de ligne ni ne soumettent. Un brouillon
qu'ils avaient ouvert — à la main ou par l'import Excel — resterait sinon
sans personne pour le finir : son auteur n'a plus le droit de le modifier,
et le pays n'est pas son auteur (décision 46).

Ces brouillons perdent donc leur auteur (``created_by`` vide) : un
brouillon sans auteur connu se complète par le pays, et **celui qui le
soumet en devient l'auteur** (``transitions._soumettre_les_lignes``), pour
que le contrôle et la règle des quatre yeux s'y appliquent. Un brouillon
déjà déclaré puis rouvert reste insupprimable (``workflow.a_ete_declare``).
Ce qui est déclaré n'est pas touché. L'ancien auteur reste lisible dans le
journal d'audit : une entrée par objet repris, avec l'avant et l'après.
"""

from django.db import migrations

ROLES_DU_SIEGE = ("super_admin", "admin")
AUTEUR = "migration expenses.0017_brouillons_du_siege_rendus_au_pays"
#: La migration qui a désactivé les comptes DM et DF : ses entrées nomment
#: les anciens comptes du siège, désormais au rôle ``manager``.
REPRISE_DES_COMPTES = "migration accounts.0006_trois_roles"
LOT = 500


def rendre_au_pays(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    ChangeLog = apps.get_model("core", "ChangeLog")
    AuditLog = apps.get_model("expenses", "AuditLog")
    # Le siège d'aujourd'hui, et celui d'hier : un brouillon qu'un ancien
    # DM ou DF aurait ouvert n'a plus personne pour le finir non plus.
    siege = set(
        UserProfile.objects.filter(role__in=ROLES_DU_SIEGE).values_list(
            "user__username", flat=True
        )
    ) | set(
        ChangeLog.objects.filter(
            model_name="user", performed_by=REPRISE_DES_COMPTES
        ).values_list("label", flat=True)
    )
    if not siege:
        return
    for nom in ("Dossier", "Expense"):
        Modele = apps.get_model("expenses", nom)
        objets = list(
            Modele.objects.filter(status="draft", created_by__in=siege).order_by("pk")
        )
        traces = []
        for objet in objets:
            traces.append(
                AuditLog(
                    user=AUTEUR,
                    action="updated",
                    object_type=nom,
                    object_id=objet.pk,
                    label=str(getattr(objet, "number", "") or getattr(objet, "title", ""))[:250],
                    country_id=objet.country_id,
                    detail={
                        "created_by": [objet.created_by, ""],
                        "motif": "Brouillon ouvert par le siège, rendu au pays (décision 89).",
                    },
                )
            )
            objet.created_by = ""
        # Par lots : un stock d'imports peut compter des milliers de lignes,
        # et une écriture par ligne garderait les verrous longtemps.
        Modele.objects.bulk_update(objets, ["created_by"], batch_size=LOT)
        AuditLog.objects.bulk_create(traces, batch_size=LOT)


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0016_index_de_tri_des_listes"),
        ("accounts", "0006_trois_roles"),
    ]

    operations = [
        migrations.RunPython(rendre_au_pays, migrations.RunPython.noop),
    ]
