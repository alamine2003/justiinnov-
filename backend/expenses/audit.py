"""Écriture du journal d'audit du circuit, des pièces et des fichiers.

Couche d'adaptation de la façade ``core.journal`` (décision 38) : les vues
et les services de transition des dépenses nomment l'action, la famille se
déduit d'elle, et tout le reste — auteur, adresse, appareil — est rempli par
la façade. Chaque action sensible produit une trace : qui, quoi, quand,
depuis quelle session, et l'ancienne/nouvelle valeur le cas échéant (§6).
"""

from core import journal

from .models import AuditLog

#: Famille de journal de chaque action ; ``circuit`` pour toutes les autres.
_FAMILLES = {
    AuditLog.Action.APPROVED: "piece",
    AuditLog.Action.REJECTED: "piece",
    AuditLog.Action.PROOF_INCOMPLETE: "piece",
    AuditLog.Action.PROOF_TO_REVIEW: "piece",
    AuditLog.Action.PROOF_UPLOADED: "piece",
    AuditLog.Action.PROOF_REPLACED: "piece",
    AuditLog.Action.DOWNLOADED: "fichier",
    AuditLog.Action.IMPORTED: "import",
}


def famille_de(action):
    return _FAMILLES.get(action, "circuit")


def preparer(request, action, instance, *, label="", country=None, **detail):
    """Construit une entrée sans l'enregistrer (voir ``core.journal.preparer``)."""
    return journal.preparer(
        request, action, instance, famille=famille_de(action),
        label=label, country=country, **detail,
    )


def record(request, action, instance, *, label="", country=None, **detail):
    """Journalise une action en déléguant à :func:`core.journal.tracer`.

    ``request`` est la requête HTTP ou une :class:`core.journal.Trace`
    (services de transition, commandes).
    """
    return journal.tracer(
        request, action, instance, famille=famille_de(action),
        label=label, country=country, **detail,
    )


def enregistrer(entrees):
    """Écrit d'un coup des entrées préparées."""
    return journal.enregistrer(entrees)
