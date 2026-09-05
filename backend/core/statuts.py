"""États du circuit de justification, et les ensembles qu'on en tire.

    brouillon → soumis → en contrôle → justifié / non justifié → clôturé

Les états vivent ici, au bas de l'ordre des dépendances (décision 40), parce
que les enveloppes (``budget``) les lisent pour calculer engagé et consommé
alors que le circuit (``expenses``) lit les enveloppes : sans ce module,
chacun importait l'autre. Le circuit lui-même — transitions, rôles, quatre
yeux — reste dans ``expenses.workflow``, qui ré-exporte ces noms.
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

#: Lignes tranchées : le siège a dit ce qu'il en était, preuve ou pas. Un
#: dossier ne se rejette ni ne se clôture tant qu'une ligne ne l'est pas.
DECIDED_STATUSES = frozenset(
    {Status.JUSTIFIED, Status.UNJUSTIFIED, Status.CLOSED}
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
