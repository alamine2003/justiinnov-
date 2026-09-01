"""Workflow de contrôle et de validation (§5.5).

    brouillon → soumis → en contrôle → validé / refusé → clôturé

Les transitions sont déclarées une fois et vérifiées côté serveur : le statut
n'est jamais modifiable directement par une écriture de champ.
"""

from django.db import models


class Status(models.TextChoices):
    DRAFT = "draft", "Brouillon"
    SUBMITTED = "submitted", "Soumis"
    IN_REVIEW = "in_review", "En contrôle"
    APPROVED = "approved", "Validé"
    REJECTED = "rejected", "Refusé"
    CLOSED = "closed", "Clôturé"


#: Transitions autorisées : action → (états de départ, état d'arrivée).
TRANSITIONS = {
    "submit": ({Status.DRAFT, Status.REJECTED}, Status.SUBMITTED),
    "review": ({Status.SUBMITTED}, Status.IN_REVIEW),
    "approve": ({Status.SUBMITTED, Status.IN_REVIEW}, Status.APPROVED),
    "reject": ({Status.SUBMITTED, Status.IN_REVIEW}, Status.REJECTED),
    "close": ({Status.APPROVED}, Status.CLOSED),
}

#: États après lesquels les données sont verrouillées (§6). Une dépense
#: validée ne se corrige que par une opération auditée, jamais en place.
LOCKED_STATUSES = frozenset({Status.APPROVED, Status.CLOSED})

#: États qui engagent le budget sans que la dépense soit encore validée.
ENGAGING_STATUSES = frozenset({Status.SUBMITTED, Status.IN_REVIEW})

#: États qui consomment réellement le budget.
CONSUMING_STATUSES = frozenset({Status.APPROVED, Status.CLOSED})


class TransitionError(Exception):
    """Transition demandée depuis un état qui ne l'autorise pas."""


def next_status(action, current):
    """État résultant d'une action, ou ``TransitionError``."""
    allowed_from, target = TRANSITIONS[action]
    if current not in allowed_from:
        labels = ", ".join(Status(s).label for s in sorted(allowed_from))
        raise TransitionError(
            f"Action impossible depuis l'état « {Status(current).label} » "
            f"(états attendus : {labels})."
        )
    return target
