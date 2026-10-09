"""L'historique d'un projet, en une seule liste (décision 110).

Deux journaux le racontent : l'historique du référentiel (``ChangeLog``)
dit qui a créé, renommé, typé ou désactivé le projet, et pourquoi ; le
journal d'audit (``AuditLog``) dit ce qui est arrivé à ses dossiers, à leurs
lignes, à leurs pièces et aux demandes de rectification. La fiche d'un
projet les lit ensemble, du plus récent au plus ancien : qui, quoi, quand,
depuis quelle adresse, avant et après, motif.
"""

from django.db.models import Q

from core.models import ChangeLog

from .models import AuditLog, Dossier, ElementSupprime, Expense, Proof, Rectification

#: Au-delà, la liste est tronquée — le journal d'audit complet reste à la
#: page Audit, filtrable par projet.
PLAFOND = 300


def _entree_referentiel(entree):
    return {
        "source": "referentiel",
        "id": entree.pk,
        "action": entree.action,
        "action_display": entree.get_action_display(),
        "objet": entree.get_model_name_display(),
        "object_id": entree.object_id,
        "label": entree.label,
        "user": entree.performed_by,
        "ip_address": entree.ip_address,
        "motif": entree.motif,
        "avant": {champ: valeurs[0] for champ, valeurs in (entree.diff or {}).items()} or None,
        "apres": {champ: valeurs[1] for champ, valeurs in (entree.diff or {}).items()} or None,
        "note": "",
        "created_at": entree.created_at,
    }


def _entree_circuit(entree):
    detail = entree.detail or {}
    return {
        "source": "circuit",
        "id": entree.pk,
        "action": entree.action,
        "action_display": entree.get_action_display(),
        "objet": entree.object_type,
        "object_id": entree.object_id,
        "label": entree.label,
        "user": entree.user,
        "ip_address": entree.ip_address,
        "motif": str(detail.get("motif") or detail.get("reason") or ""),
        "avant": detail.get("before"),
        "apres": detail.get("after"),
        "note": str(detail.get("note") or ""),
        "created_at": entree.created_at,
    }


def retirees_des_dossiers(dossiers):
    """Les lignes et pièces retirées de ``dossiers`` : elles ne sont plus en
    base, leur trace dit encore d'où elles venaient (``dossier_id``)."""
    return Q(
        action=AuditLog.Action.DELETED, object_type__in=["Expense", "Proof"],
        detail__dossier_id__in=list(dossiers),
    )


def journal_du_projet(projet_id):
    """Ce qui, au journal d'audit, concerne les dossiers d'un projet, leurs
    lignes, leurs pièces et leurs demandes de rectification.

    Ce qui a été mis à la corbeille (décision 120) n'est plus en base : ses
    identifiants se relisent dans les copies de la corbeille, pour que la
    fiche du projet garde l'histoire — et la mise à la corbeille elle-même —
    de ce qui en est parti.
    """
    nature = ElementSupprime.Nature
    # Un filtre d'URL le donne en décimal ; une clé JSON se compare à un entier.
    projet_id = int(projet_id)
    dossiers = set(Dossier.objects.filter(project=projet_id).values_list("pk", flat=True))
    dossiers |= set(
        ElementSupprime.objects.filter(nature=nature.DOSSIER, donnees__project_id=projet_id)
        .values_list("objet_id", flat=True)
    )
    lignes = set(Expense.objects.filter(dossier__in=dossiers).values_list("pk", flat=True))
    rectifications = set(
        Rectification.objects.filter(expense__in=lignes).values_list("pk", flat=True)
    )
    for objet_id, donnees in ElementSupprime.objects.filter(
        nature=nature.LIGNE, donnees__dossier_id__in=list(dossiers)
    ).values_list("objet_id", "donnees"):
        lignes.add(objet_id)
        rectifications.update(r["id"] for r in donnees.get("rectifications", []))
    pieces = set(Proof.objects.filter(dossier__in=dossiers).values_list("pk", flat=True))
    pieces |= set(
        ElementSupprime.objects.filter(nature=nature.PIECE, donnees__dossier_id__in=list(dossiers))
        .values_list("objet_id", flat=True)
    )
    return (
        # La mise à la corbeille du projet lui-même (décision 120).
        Q(object_type="Project", object_id=projet_id)
        | Q(object_type="Dossier", object_id__in=dossiers)
        | Q(object_type="Expense", object_id__in=lignes)
        | Q(object_type="Proof", object_id__in=pieces)
        | Q(object_type="Rectification", object_id__in=rectifications)
        | retirees_des_dossiers(dossiers)
    )


def historique_du_projet(projet):
    """``{"entrees": [...], "tronque": bool}`` pour ``projet``."""
    referentiel = ChangeLog.objects.filter(
        model_name=ChangeLog.Models.PROJECT, object_id=projet.pk
    ).order_by("-created_at", "-pk")[: PLAFOND + 1]
    circuit = AuditLog.objects.filter(journal_du_projet(projet.pk)).order_by(
        "-created_at", "-pk"
    )[: PLAFOND + 1]
    entrees = sorted(
        [*map(_entree_referentiel, referentiel), *map(_entree_circuit, circuit)],
        key=lambda e: (e["created_at"], e["id"]),
        reverse=True,
    )
    return {"entrees": entrees[:PLAFOND], "tronque": len(entrees) > PLAFOND}
