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
- **Personne ne contrôle sa propre dépense.** Le pays (manager) déclare,
  le siège constate — le DM met en contrôle, le DF tranche. Et même au
  siège, celui qui a saisi une ligne ou ouvert un dossier n'y accomplit
  aucun acte de contrôle : ni mise en contrôle, ni justification, ni rejet,
  ni clôture (``FOUR_EYES_ACTIONS``). Sans cette séparation, une seule
  personne pourrait décaisser puis se donner quitus.

Les actions que le demandeur peut tenter sont calculées ici aussi
(``expense_allowed_actions``, ``dossier_allowed_actions``) et exposées par
l'API : l'interface les affiche, elle ne recopie pas les règles.

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

from django.utils.translation import gettext_lazy as _

from accounts.permissions import roles_pour

from core.regles import RegleViolee

# Les états et leurs ensembles vivent dans ``core.statuts`` (décision 40) et
# sont ré-exportés ici : le circuit reste l'endroit où on vient les chercher.
from core.statuts import (  # noqa: F401
    CONSUMING_STATUSES,
    DECIDED_STATUSES,
    DELETABLE_STATUSES,
    ENGAGING_STATUSES,
    LOCKED_STATUSES,
    PROOF_LOCKED_STATUSES,
    Status,
)


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

#: Capacité exigée pour chaque action du circuit (``accounts.permissions``).
#: Par défaut, le pays (manager) soumet ; au siège, le DM met en contrôle et
#: le DF tranche (justifie, rejette, clôt), les administrateurs pouvant faire
#: l'un et l'autre ; les administrateurs seuls rouvrent — ni le pays, qui se
#: corrigerait lui-même, ni la direction financière, dont le constat ne se
#: défait pas. La matrice des droits peut élargir ces défauts, jamais au
#: pays pour le contrôle.
ACTION_CAPACITES = {
    "submit": "dossiers.submit",
    "review": "expenses.review",
    "justify": "expenses.validate",
    "reject": "expenses.validate",
    "close": "expenses.close",
    "reopen": "dossiers.reopen",
}

#: Actions de saisie et leur capacité. Elles ne sont pas des transitions —
#: l'état ne change pas — mais l'interface les propose au même endroit que
#: le circuit, et c'est le serveur qui dit si elles sont possibles :
#: brouillon ou non, auteur ou non, capacité ou non.
SAISIE_CAPACITES = {
    "edit": "expenses.update",
    "add_line": "expenses.create",
    "upload": "proofs.upload",
    "delete": "expenses.delete",
}

#: Actions soumises à la règle des quatre yeux : tout acte de contrôle, de
#: la mise en contrôle à la clôture. Celui qui a saisi une ligne ou ouvert
#: un dossier ne le prend pas en contrôle, ne le tranche pas et ne le clôt
#: pas — la clôture aussi est un constat, elle déclare l'affaire terminée.
#: Soumettre et rouvrir n'en relèvent pas : ce sont la déclaration et sa
#: remise en cause, pas son contrôle.
FOUR_EYES_ACTIONS = frozenset({"review", "justify", "reject", "close"})

#: États d'une ligne qui interdisent de rouvrir son dossier : le siège a
#: constaté, et un constat ne se défait pas. Une ligne non justifiée, elle,
#: n'a pas été constatée — l'absence de preuve a été relevée, rien de plus.
REOPEN_BLOCKING_STATUSES = frozenset({Status.JUSTIFIED, Status.CLOSED})

#: États exigés des lignes pour trancher le dossier. Le dossier ne dit pas
#: autre chose que ses lignes : « justifié » exige que chacune le soit ;
#: « non justifié » et « clôturé » exigent seulement qu'aucune ne reste en
#: suspens.
LINES_REQUIRED = {
    "justify": REOPEN_BLOCKING_STATUSES,
    "reject": DECIDED_STATUSES,
    "close": DECIDED_STATUSES,
}


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


class TransitionError(RegleViolee):
    """Transition demandée depuis un état qui ne l'autorise pas.

    Une règle violée sur le champ ``status`` : la vue la traduit comme les
    autres refus (``core.regles``), en 400 sur ``status``.
    """

    def __init__(self, message):
        super().__init__("status", message)


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


def can_transition(action, current, *, role, configuration=None):
    """Le rôle et l'état permettent-ils l'action ? Ni plus, ni moins."""
    if role not in roles_pour(ACTION_CAPACITES[action], configuration):
        return False
    try:
        next_status(action, current, configuration)
    except TransitionError:
        return False
    return True


def breaks_four_eyes(action, author, username):
    """L'action est-elle un acte de contrôle tenté par l'auteur de l'objet ?

    Seul prédicat des quatre yeux : ``allowed_actions`` (l'interface) et les
    services de transition (le refus) le partagent, pour ne jamais diverger.
    Sans auteur connu, la règle ne peut pas jouer — le service refuse alors
    tout contrôle sur la ligne (``transitions.exiger_un_auteur``).
    """
    return action in FOUR_EYES_ACTIONS and bool(author) and author == username


#: Actions d'une ligne, dans l'ordre où l'interface les propose : la saisie
#: d'abord, le contrôle ensuite.
EXPENSE_ACTIONS = ("edit", "delete", "review", "justify", "reject", "close")

#: Actions d'un dossier, dans le même ordre que le circuit.
DOSSIER_ACTIONS = (
    "edit", "add_line", "upload", "delete",
    "submit", "review", "justify", "reject", "close", "reopen",
)


def peut_saisir(action, objet, *, role, username, configuration=None):
    """La saisie ``action`` (modifier, ajouter, déposer, supprimer) est-elle possible ?

    Une dépense déclarée ne se modifie plus ni ne se supprime ; une pièce se
    dépose jusqu'à la clôture ; un brouillon ne se retire que par son auteur
    (``transitions.retirer_brouillon``). Sans auteur connu — import, compte
    disparu — le retrait reste ouvert à qui a la capacité. Comme pour
    ``justify``, la liste dit ce qui peut être *tenté* : le retrait d'un
    dossier qui porte la ligne d'un autre auteur est proposé ici et refusé
    par le service, qui seul lit les lignes.
    """
    if role not in roles_pour(SAISIE_CAPACITES[action], configuration):
        return False
    if action == "delete":
        return objet.status in DELETABLE_STATUSES and (
            not objet.created_by or objet.created_by == username
        )
    if action == "upload":
        return objet.status not in PROOF_LOCKED_STATUSES
    return objet.status not in LOCKED_STATUSES


def expense_allowed_actions(expense, *, role, username, configuration=None):
    """Actions qu'un demandeur peut tenter sur une ligne (``allowed_actions``).

    Calculées côté serveur pour que l'interface n'ait pas à recopier les
    règles : capacité (matrice des droits), état courant, étape de contrôle
    obligatoire et quatre yeux. Une ligne sans auteur connu n'admet aucune
    action de contrôle, puisque la règle des quatre yeux ne peut pas y être
    vérifiée ; les actions de saisie (``SAISIE_CAPACITES``) obéissent aux
    mêmes règles que les services qui les exécutent (``peut_saisir``).

    La politique de dépassement n'entre pas dans ce calcul : elle se juge
    sous verrou, sur l'enveloppe, au moment de justifier — ``justify`` peut
    donc figurer ici et répondre 400 pour dépassement.
    """
    actions = []
    for action in EXPENSE_ACTIONS:
        if action in SAISIE_CAPACITES:
            if peut_saisir(
                action, expense, role=role, username=username, configuration=configuration
            ):
                actions.append(action)
        elif (
            expense.created_by
            and can_transition(action, expense.status, role=role, configuration=configuration)
            and not breaks_four_eyes(action, expense.created_by, username)
        ):
            actions.append(action)
    return actions


def dossier_allowed_actions(dossier, *, role, username, configuration=None):
    """Actions qu'un demandeur peut tenter sur un dossier (``allowed_actions``).

    Mêmes règles que pour la ligne, plus celles qui lient le dossier à ses
    lignes et à ses pièces : un dossier vide ne se soumet pas, ne se justifie
    pas sans pièce exploitable ni sans que chaque ligne le soit, ne se
    rejette ni ne se clôt sur une ligne en suspens, et ne se rouvre pas dès
    qu'une ligne a été constatée. Les compteurs viennent du dossier
    (:meth:`Dossier.line_counts`), annotés par ``with_totals`` sur une
    liste pour ne pas coûter une requête par dossier.

    Une action proposée peut encore être refusée à l'exécution (400) par
    les règles que le service seul vérifie, parce qu'elles demandent des
    lectures que cette liste ne fait pas : ``submit`` exige une équipe et
    un manager sur le dossier, et une enveloppe active pour chaque ligne à
    imputer ; la politique de dépassement se juge au montant consommé. La
    liste dit ce que le demandeur *peut tenter*, pas ce qui aboutira.
    """
    actions = []
    lines = None
    for action in DOSSIER_ACTIONS:
        if action in SAISIE_CAPACITES:
            if peut_saisir(
                action, dossier, role=role, username=username, configuration=configuration
            ):
                actions.append(action)
            continue
        if not can_transition(action, dossier.status, role=role, configuration=configuration):
            continue
        if breaks_four_eyes(action, dossier.created_by, username):
            continue
        if lines is None:
            lines = dossier.line_counts()
        if action == "submit" and lines["total"] == 0:
            continue
        if action == "justify" and (
            lines["pending"] or lines["unjustified"] or dossier.usable_proof_count() == 0
        ):
            continue
        if action in ("reject", "close") and lines["pending"]:
            continue
        if action == "reopen" and lines["settled"]:
            continue
        actions.append(action)
    return actions
