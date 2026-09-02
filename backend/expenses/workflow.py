"""Circuit de justification d'une dépense (§5.5).

    brouillon → soumis → en contrôle → justifié / non justifié → clôturé

La dépense constate un décaissement déjà effectué : le contrôleur n'autorise
pas un achat, il constate qu'une preuve le couvre — d'où « justifié » plutôt
que « validé ».

Deux principes gouvernent ce circuit :

- **Une fois soumise, une dépense est irréversible.** Elle ne revient jamais
  au brouillon, ne se modifie plus et ne se supprime pas. Le budget a été
  dépensé ; l'effacer reviendrait à perdre la trace de l'argent.
- **Une dépense non justifiée pèse malgré tout sur l'enveloppe.** L'absence de
  preuve ne fait pas revenir l'argent : elle se lit dans l'écart entre le
  montant dépensé et le montant justifié.
- **Personne ne justifie sa propre dépense.** Le pays déclare, le siège
  constate. Et même au siège, celui qui a saisi une dépense ne peut pas la
  justifier lui-même : sans cette séparation, une seule personne pourrait
  décaisser puis se donner quitus.
"""

from django.db import models


class Status(models.TextChoices):
    DRAFT = "draft", "Brouillon"
    SUBMITTED = "submitted", "Soumis"
    IN_REVIEW = "in_review", "En contrôle"
    JUSTIFIED = "justified", "Justifié"
    UNJUSTIFIED = "unjustified", "Non justifié"
    CLOSED = "closed", "Clôturé"


#: Transitions autorisées : action → (états de départ, état d'arrivée).
#:
#: ``submit`` ne part que du brouillon : une dépense déjà déclarée ne se
#: resoumet pas. ``justify`` accepte en revanche une dépense non justifiée —
#: c'est le seul chemin de rattrapage, ouvert par le dépôt d'une preuve
#: complémentaire.
TRANSITIONS = {
    "submit": ({Status.DRAFT}, Status.SUBMITTED),
    "review": ({Status.SUBMITTED}, Status.IN_REVIEW),
    "justify": (
        {Status.SUBMITTED, Status.IN_REVIEW, Status.UNJUSTIFIED},
        Status.JUSTIFIED,
    ),
    "reject": ({Status.SUBMITTED, Status.IN_REVIEW}, Status.UNJUSTIFIED),
    "close": ({Status.JUSTIFIED}, Status.CLOSED),
}

#: États verrouillés : la dépense est déclarée, plus rien ne se modifie.
#: Le brouillon seul reste une matière de travail.
LOCKED_STATUSES = frozenset(
    {
        Status.SUBMITTED,
        Status.IN_REVIEW,
        Status.JUSTIFIED,
        Status.UNJUSTIFIED,
        Status.CLOSED,
    }
)

#: Un justificatif reste déposable tant que le dossier n'est pas clôturé :
#: rassembler la preuve est précisément l'objet de l'application, et une
#: dépense non justifiée doit pouvoir être couverte après coup.
PROOF_LOCKED_STATUSES = frozenset({Status.CLOSED})

#: Seul un brouillon peut encore être retiré, par son auteur.
DELETABLE_STATUSES = frozenset({Status.DRAFT})

#: Déclarée mais pas encore contrôlée.
ENGAGING_STATUSES = frozenset({Status.SUBMITTED, Status.IN_REVIEW})

#: Décaissements constatés. La non-justification en fait partie : l'argent est
#: sorti, la preuve manque — c'est précisément ce que l'écart doit montrer.
CONSUMING_STATUSES = frozenset(
    {Status.JUSTIFIED, Status.UNJUSTIFIED, Status.CLOSED}
)


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
