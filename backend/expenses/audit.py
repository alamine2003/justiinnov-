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


def champs_journalises(serializer, *calcules):
    """Champs qu'une modification peut faire bouger : ceux que la charge
    utile écrit, plus ceux que le serveur calcule à cette occasion."""
    editables = [
        nom for nom, champ in serializer.fields.items() if not champ.read_only
    ]
    return (*editables, *calcules)


def photographier(instance, champs):
    """Photographie des champs, dans la forme du journal.

    Une clé étrangère est notée par son identifiant : c'est ce que la
    charge utile porte et ce que l'interface relit.
    """
    photo = {}
    for champ in champs:
        attribut = instance._meta.get_field(champ).attname
        photo[champ] = journal.serialisable(getattr(instance, attribut))
    return photo


def journaliser_la_modification(request, instance, avant, champs):
    """Trace ``updated`` : avant et après de **tout** ce qui a changé.

    Une trace qui ne disait que le montant laissait passer, sans trace,
    un changement de date, de bénéficiaire ou de dossier. Rien de changé,
    rien d'écrit : une écriture qui remet les mêmes valeurs n'est pas une
    modification. Rend l'entrée, ou ``None``.
    """
    apres = photographier(instance, champs)
    changes = journal.difference(avant, apres)
    if not changes:
        return None
    return record(
        request,
        AuditLog.Action.UPDATED,
        instance,
        before={champ: valeurs[0] for champ, valeurs in changes.items()},
        after={champ: valeurs[1] for champ, valeurs in changes.items()},
        changed_fields=list(changes),
    )
