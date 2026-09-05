"""Services de transition des réallocations budgétaires (décision 41).

Le circuit d'une réallocation — demande, approbation, refus — vivait dans
la vue, réécrit à part de celui des dépenses et journalisé autrement. Il
est ici, sur le même patron que ``expenses.transitions`` : des services
purs, sans HTTP, qui prennent les verrous, vérifient le rôle, le périmètre,
le disponible et l'absence d'auto-décision, puis journalisent.

Deux journaux, à dessein : l'``AuditLog`` (famille ``circuit``) garde la
demande et la décision — qui, quand, depuis où, avec quel motif — comme il
garde une soumission ou un rejet ; le ``ChangeLog`` des enveloppes, tenu
par les signaux du référentiel, garde le mouvement des montants. L'un dit
qu'on a arbitré, l'autre ce que l'arbitrage a changé.

Un refus est une exception de ``core.regles`` : la vue la traduit en 400,
403 ou 404 ; le sérialiseur (``can_decide``) l'interprète en booléen.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.permissions import BUDGET_WRITE_ROLES, RolePermission
from core.journal import Trace, tracer  # noqa: F401 — ``Trace`` ré-exportée
from core.regles import HorsPerimetre, PermissionRefusee, RegleViolee
from notifications import triggers

from .aggregates import consumption
from .models import Budget, BudgetReallocation

#: Actions d'audit d'une réallocation. Ce sont des valeurs de
#: ``expenses.models.AuditLog.Action`` — que ``budget`` ne peut importer
#: (décision 40) : la demande est une création, la décision une
#: modification dont ``detail`` dit le sens (``from_status``/``to_status``).
ACTION_DEMANDEE = "created"
ACTION_DECIDEE = "updated"


@dataclass
class Resultat:
    """Ce qu'un service rend : la réallocation après coup et les traces."""

    instance: BudgetReallocation
    warning: str | None = None
    audit: list = field(default_factory=list)


def disponible(budget):
    """Ce qu'une enveloppe peut encore céder : l'alloué moins le consommé
    et l'engagé. Recalculé sur l'instance, hors annotations de liste."""
    totals = consumption(budget)
    return budget.amount - totals["consumed"] - totals["engaged"]


def exiger_le_role(acteur):
    """Demander, approuver, refuser : la direction seule (``BUDGET_WRITE_ROLES``)."""
    if acteur is None or acteur.role not in BUDGET_WRITE_ROLES:
        raise PermissionRefusee(str(RolePermission.message))


def exiger_le_perimetre(acteur, *budgets):
    """Chaque enveloppe est dans le périmètre de l'acteur, sinon elle
    n'existe pas pour lui."""
    if acteur is None or acteur.has_global_scope:
        return
    for budget in budgets:
        if budget.country_id not in acteur.country_ids:
            raise HorsPerimetre()


def exiger_le_disponible(source, montant):
    """L'argent déjà sorti ou engagé n'est plus transférable.

    Partagé par le sérialiseur (à la demande, pour l'erreur de saisie) et
    par :func:`approuver` (sous verrou : une dépense a pu sortir entre la
    demande et la décision).
    """
    reste = disponible(source)
    if montant > reste:
        raise RegleViolee(
            "amount",
            _(
                "Le montant dépasse le disponible de l'enveloppe source ({available})."
            ).format(available=reste),
        )


def verifier_la_decision(reallocation, acteur):
    """La réallocation se décide-t-elle, et par cet acteur ?

    Trois refus, trois codes : déjà traitée (400), demandée par l'acteur
    lui-même (403 — demander et approuver sont deux regards), destination
    hors périmètre (404 — le queryset ne filtre que par le pays de la
    source, la destination doit être dans le périmètre elle aussi).
    """
    if reallocation.status != BudgetReallocation.Status.PENDING:
        raise RegleViolee("status", _("Cette réallocation a déjà été traitée."))
    if reallocation.requested_by == acteur.username:
        raise PermissionRefusee(
            _("Vous ne pouvez pas décider d'une réallocation que vous avez demandée.")
        )
    exiger_le_perimetre(acteur, reallocation.target)


def peut_decider(reallocation, acteur):
    """``can_decide`` : les mêmes conditions que la décision, en booléen."""
    if acteur is None or acteur.role not in BUDGET_WRITE_ROLES:
        return False
    try:
        verifier_la_decision(reallocation, acteur)
    except (RegleViolee, PermissionRefusee, HorsPerimetre):
        return False
    return True


def verrouiller_pour_decision(reallocation, acteur):
    """Relit la réallocation sous verrou et vérifie qu'elle se décide.

    Le statut est contrôlé **après** la prise du verrou : lu avant, deux
    approbations simultanées le verraient toutes deux « en attente » et
    exécuteraient le transfert deux fois.
    """
    # Sans jointure : le verrou ne doit porter que sur la réallocation, les
    # enveloppes sont verrouillées ensuite, dans l'ordre de leurs
    # identifiants.
    verrouillee = BudgetReallocation.objects.select_for_update().get(pk=reallocation.pk)
    verifier_la_decision(verrouillee, acteur)
    return verrouillee


def _journaliser(trace, action, reallocation, **detail):
    return tracer(
        trace, action, reallocation, famille="circuit",
        country=reallocation.source.country,
        amount=str(reallocation.amount),
        source=reallocation.source_id, target=reallocation.target_id,
        **detail,
    )


def _decider(reallocation, acteur, note, trace, statut):
    """Tronc commun d'une décision : statut, motif, signature, journal."""
    reallocation.status = statut
    reallocation.decision_note = note
    reallocation.decided_by = acteur.username
    reallocation.decided_at = timezone.now()
    reallocation.save()
    return _journaliser(
        trace, ACTION_DECIDEE, reallocation,
        from_status=BudgetReallocation.Status.PENDING, to_status=statut, note=note,
    )


# --- Services ---------------------------------------------------------------------


@transaction.atomic
def demander(source, target, montant, motif, acteur, trace):
    """Demande un transfert entre deux enveloppes de même devise.

    Le disponible de la source est jugé sous verrou dès la demande : une
    demande qu'on sait impossible n'a pas à attendre l'arbitre.
    """
    exiger_le_role(acteur)
    exiger_le_perimetre(acteur, source, target)
    if source.pk == target.pk:
        raise RegleViolee("target", _("La source et la destination doivent différer."))
    if source.country.currency != target.country.currency:
        raise RegleViolee(
            "target",
            _(
                "Les deux enveloppes doivent être dans la même devise "
                "({source} → {target})."
            ).format(source=source.country.currency, target=target.country.currency),
        )
    if not (motif or "").strip():
        raise RegleViolee("reason", _("La justification est obligatoire."))
    source = Budget.objects.select_related("country").select_for_update(of=("self",)).get(pk=source.pk)
    exiger_le_disponible(source, montant)

    reallocation = BudgetReallocation.objects.create(
        source=source, target=target, amount=montant, reason=motif,
        requested_by=acteur.username,
    )
    entree = _journaliser(trace, ACTION_DEMANDEE, reallocation, reason=motif)
    triggers.reallocation_requested(reallocation, trace.compte)
    return Resultat(reallocation, audit=[entree])


@transaction.atomic
def approuver(reallocation, acteur, note, trace):
    """Approuve et exécute le transfert.

    Les deux enveloppes sont verrouillées dans l'ordre de leurs
    identifiants : deux réallocations croisées (A→B et B→A) approuvées en
    même temps prendraient sinon les verrous en sens inverse et
    s'interbloqueraient.
    """
    exiger_le_role(acteur)
    note = (note or "").strip()
    reallocation = verrouiller_pour_decision(reallocation, acteur)
    budgets = {
        budget.pk: budget
        for budget in Budget.objects.select_for_update()
        .filter(pk__in=[reallocation.source_id, reallocation.target_id])
        .order_by("pk")
    }
    source = budgets[reallocation.source_id]
    target = budgets[reallocation.target_id]
    if reallocation.amount > disponible(source):
        # L'argent déjà sorti ou engagé n'est plus transférable : la source
        # doit pouvoir couvrir ses dépenses après le transfert.
        raise RegleViolee(
            "amount",
            _("Le disponible de l'enveloppe source ne couvre plus ce montant."),
        )
    source.amount -= reallocation.amount
    target.amount += reallocation.amount
    source.save(update_fields=["amount", "updated_at"])
    target.save(update_fields=["amount", "updated_at"])

    entree = _decider(
        reallocation, acteur, note, trace, BudgetReallocation.Status.APPROVED
    )
    return Resultat(reallocation, audit=[entree])


@transaction.atomic
def refuser(reallocation, acteur, note, trace):
    """Refuse le transfert. Le motif est obligatoire (§5.5)."""
    exiger_le_role(acteur)
    note = (note or "").strip()
    if not note:
        raise RegleViolee("note", _("Un refus doit être motivé."))
    reallocation = verrouiller_pour_decision(reallocation, acteur)
    entree = _decider(
        reallocation, acteur, note, trace, BudgetReallocation.Status.REJECTED
    )
    return Resultat(reallocation, audit=[entree])
