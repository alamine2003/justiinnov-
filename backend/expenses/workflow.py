"""Circuit de justification d'une dépense (§5.5).

    brouillon → soumis → en contrôle → justifié / non justifié → clôturé

La dépense constate un décaissement déjà effectué : le siège (la direction
financière) n'autorise pas un achat, il constate qu'une preuve le couvre —
d'où « justifié » plutôt que « validé ».

Trois principes gouvernent ce circuit :

- **Une fois soumise, une dépense est irréversible.** Elle ne revient jamais
  au brouillon, ne se modifie plus et ne se supprime pas. Le budget a été
  dépensé ; l'effacer reviendrait à perdre la trace de l'argent.
- **Une dépense non justifiée pèse malgré tout sur l'enveloppe.** L'absence de
  preuve ne fait pas revenir l'argent : elle se lit dans l'écart entre le
  montant dépensé et le montant justifié.
- **Personne ne justifie sa propre dépense.** Le pays (manager) déclare,
  le siège constate — le DM met en contrôle, le DF tranche. Et même au
  siège, celui qui a saisi une dépense ne
  peut pas la justifier lui-même : sans cette séparation, une seule personne
  pourrait décaisser puis se donner quitus.

**La réouverture est la seule exception à l'irréversibilité.** Un
administrateur (RH ou super administrateur) peut renvoyer au brouillon un
dossier déclaré mais pas encore constaté, pour demander des comptes au pays :
une ligne mal imputée, un montant douteux, une pièce qui ne correspond pas.
Elle n'est pas une correction silencieuse, et le circuit le garantit :

- elle est réservée aux administrateurs, jamais au pays qui a déclaré ni à la
  direction financière qui constate ;
- elle exige un motif, conservé sur le dossier et dans le journal d'audit,
  sur le dossier et sur chacune de ses lignes ;
- elle est refusée dès qu'une ligne est justifiée ou clôturée : le siège a
  constaté, ce constat ne se défait pas ;
- le pays en est prévenu, et devra resoumettre le dossier — qui repassera
  par tout le circuit.

Le dossier rouvert libère l'engagement de ses lignes sur l'enveloppe : elles
ne sont plus déclarées, elles ne pèsent plus. Le journal, lui, garde tout.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Status(models.TextChoices):
    DRAFT = "draft", _("Brouillon")
    SUBMITTED = "submitted", _("Soumis")
    IN_REVIEW = "in_review", _("En contrôle")
    JUSTIFIED = "justified", _("Justifié")
    UNJUSTIFIED = "unjustified", _("Non justifié")
    CLOSED = "closed", _("Clôturé")


#: Transitions autorisées : action → (états de départ, état d'arrivée).
#:
#: ``submit`` ne part que du brouillon : une dépense déjà déclarée ne se
#: resoumet pas — et une ligne ne se soumet jamais seule : c'est le dossier
#: qui emporte ses lignes. ``justify`` accepte en revanche une dépense non
#: justifiée — c'est le seul chemin de rattrapage, ouvert par le dépôt d'une
#: preuve complémentaire. ``reopen`` ramène un dossier déclaré au brouillon
#: tant que rien n'y a été constaté : voir le module.
TRANSITIONS = {
    "submit": ({Status.DRAFT}, Status.SUBMITTED),
    "review": ({Status.SUBMITTED}, Status.IN_REVIEW),
    "justify": (
        {Status.SUBMITTED, Status.IN_REVIEW, Status.UNJUSTIFIED},
        Status.JUSTIFIED,
    ),
    "reject": ({Status.SUBMITTED, Status.IN_REVIEW}, Status.UNJUSTIFIED),
    "close": ({Status.JUSTIFIED}, Status.CLOSED),
    "reopen": (
        {Status.SUBMITTED, Status.IN_REVIEW, Status.UNJUSTIFIED},
        Status.DRAFT,
    ),
}

#: Actions qui exigent un motif : un rejet et une réouverture se justifient
#: auprès de celui qui les subit.
MOTIVATED_ACTIONS = frozenset({"reject", "reopen"})

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

#: États d'une ligne qui interdisent de rouvrir son dossier : le siège a
#: constaté, et un constat ne se défait pas. Une ligne non justifiée, elle,
#: n'a pas été constatée — l'absence de preuve a été relevée, rien de plus.
REOPEN_BLOCKING_STATUSES = frozenset({Status.JUSTIFIED, Status.CLOSED})

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


#: Contrôle documentaire d'une pièce : état courant → états atteignables.
#:
#: Une pièce reçue ou à contrôler peut être validée, rejetée, signalée
#: incomplète ou remise dans la file. Une pièce incomplète n'est pas
#: « re-signalée » incomplète : on attend le complément, puis on tranche.
#: Validée, rejetée ou archivée, elle ne bouge plus : seul un remplacement
#: par une nouvelle version (qui l'archive) fait avancer le dossier. Sans ce
#: tableau, la direction financière pouvait dévalider une pièce déjà
#: validée, voire ressusciter une pièce archivée.
PROOF_TRANSITIONS = {
    "received": frozenset({"validated", "rejected", "incomplete", "to_review"}),
    "to_review": frozenset({"validated", "rejected", "incomplete", "to_review"}),
    "incomplete": frozenset({"to_review", "validated", "rejected"}),
    "validated": frozenset(),
    "rejected": frozenset(),
    "archived": frozenset(),
}


class TransitionError(Exception):
    """Transition demandée depuis un état qui ne l'autorise pas."""


def next_proof_status(current, target, labels):
    """Vérifie une transition documentaire ; ``labels`` traduit les états."""
    if target not in PROOF_TRANSITIONS.get(current, frozenset()):
        atteignables = ", ".join(
            str(labels[s]) for s in sorted(PROOF_TRANSITIONS.get(current, ()))
        ) or _("aucun : la pièce est figée")
        raise TransitionError(
            _(
                "Un justificatif « {current} » ne peut pas passer à "
                "« {target} » (états atteignables : {reachable})."
            ).format(
                current=labels[current], target=labels[target], reachable=atteignables
            )
        )
    return target


def next_status(action, current, configuration=None):
    """État résultant d'une action, ou ``TransitionError``."""
    allowed_from, target = TRANSITIONS[action]
    if (
        action == "justify"
        and current == Status.SUBMITTED
        and configuration is not None
        and configuration.require_review_step
    ):
        raise TransitionError(
            _("La dépense doit passer en contrôle avant d'être justifiée.")
        )
    if current not in allowed_from:
        labels = ", ".join(str(Status(s).label) for s in sorted(allowed_from))
        raise TransitionError(
            _(
                "Action impossible depuis l'état « {current} » "
                "(états attendus : {expected})."
            ).format(current=Status(current).label, expected=labels)
        )
    return target
