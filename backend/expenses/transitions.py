"""Services de transition du circuit de justification (décision 41).

Les règles du circuit vivaient dans les vues : une commande ou un import qui
voulait soumettre un dossier devait fabriquer une requête HTTP. Elles sont
ici, sous forme de services purs — sans HTTP ni sérialisation — que les vues,
l'import et les commandes appellent :

- :func:`soumettre` — le dossier part avec ses lignes ;
- :func:`rouvrir` — seule exception à l'irréversibilité, motivée ;
- :func:`mettre_en_controle`, :func:`trancher`, :func:`cloturer` — les
  actes de contrôle du siège, sur un dossier ou sur une ligne ;
- :func:`retirer_brouillon` — un brouillon, par son auteur, avec ce qu'il
  contient s'il s'agit d'un dossier ;
- :func:`controler_piece` — le contrôle documentaire d'un justificatif ;
- :func:`demander_rectification`, :func:`approuver_rectification`,
  :func:`refuser_rectification` — la seconde exception à l'irréversibilité :
  un constat remis en cause sur demande motivée, tranché par un
  administrateur qui n'est pas le demandeur.

Chaque service prend les verrous (``select_for_update``), vérifie l'état
(``next_status``), la capacité (``ACTION_CAPACITES``), les quatre yeux, les lignes
exigées, l'imputation et la politique de dépassement, journalise via
``core.journal`` et déclenche les notifications. Il reçoit l'``Access`` de
celui qui agit et une :class:`~core.journal.Trace` (qui, depuis où) ; il
rend un :class:`Resultat` — l'instance après transition, l'avertissement
éventuel, les entrées de journal écrites.

Un refus est une exception de ``core.regles`` : la vue la traduit en 400,
403 ou 404 (:func:`~core.regles.traduire_les_regles`), une commande
l'attrape telle quelle. Les messages sont ceux que l'API renvoyait déjà.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from accounts.permissions import COUNTRY_ROLES, exiger_la_capacite, roles_pour
from budget.models import Budget
from core.models import WorkflowConfiguration
from core.regles import HorsPerimetre, PermissionRefusee, RegleViolee
from notifications import triggers

from . import stockage
from .audit import enregistrer, preparer, record
from .models import (
    EXPENSE_RELATIONS,
    ZERO,
    AuditLog,
    Dossier,
    Expense,
    Proof,
    Rectification,
)
from .services import (
    attach_budget,
    check_budget_capacity,
    cle_d_imputation,
    committed_total,
)
from .workflow import (
    ACTION_CAPACITES,
    DECIDED_STATUSES,
    DELETABLE_STATUSES,
    FOUR_EYES_ACTIONS,
    LINES_REQUIRED,
    LOCKED_STATUSES,
    MOTIVATED_ACTIONS,
    PROOF_LOCKED_STATUSES,
    RECTIFIABLE_STATUSES,
    REOPEN_BLOCKING_STATUSES,
    Status,
    breaks_four_eyes,
    next_proof_status,
    next_status,
)

#: Message renvoyé quand une action qui exige un motif n'en reçoit pas.
MOTIF_MANQUANT = {
    "reject": gettext_lazy("Un rejet doit être motivé."),
    "reopen": gettext_lazy(
        "Une réouverture doit être motivée : le pays doit savoir ce qu'on "
        "lui demande."
    ),
    "rectify": gettext_lazy(
        "Une rectification doit être motivée : le siège doit savoir ce "
        "qu'il a constaté à tort."
    ),
}

#: Signalé au pays quand il soumet sans pièce. La soumission passe quand même :
#: bloquer reviendrait à ce qu'une dépense sans reçu ne soit jamais déclarée,
#: donc à ce que l'argent sorte sans laisser de trace — pire que l'écart.
SANS_PREUVE = gettext_lazy(
    "Aucun justificatif n'est joint : la dépense est déclarée sans preuve, "
    "elle creusera l'écart et sera signalée au siège."
)

#: Action de workflow → action d'audit.
AUDIT_ACTIONS = {
    "submit": AuditLog.Action.SUBMITTED,
    "review": AuditLog.Action.REVIEWED,
    "justify": AuditLog.Action.JUSTIFIED,
    "reject": AuditLog.Action.UNJUSTIFIED,
    "close": AuditLog.Action.CLOSED,
    "reopen": AuditLog.Action.REOPENED,
    "rectify": AuditLog.Action.RECTIFIED,
}

#: État visé d'une pièce → action d'audit.
PROOF_AUDIT_ACTIONS = {
    Proof.ProofStatus.VALIDATED: AuditLog.Action.APPROVED,
    Proof.ProofStatus.REJECTED: AuditLog.Action.REJECTED,
    Proof.ProofStatus.INCOMPLETE: AuditLog.Action.PROOF_INCOMPLETE,
    Proof.ProofStatus.TO_REVIEW: AuditLog.Action.PROOF_TO_REVIEW,
}


@dataclass
class Resultat:
    """Ce qu'un service rend : l'objet après coup, l'avertissement, les traces."""

    instance: object
    warning: str | None = None
    audit: list = field(default_factory=list)


# --- Prédicats partagés -----------------------------------------------------


def exiger_l_auteur_du_brouillon(objet, acteur):
    """Un brouillon ne se modifie que par qui l'a saisi, ou par le siège.

    Un collègue du même pays qui changerait le montant laisserait l'auteur
    soumettre une ligne qu'il n'a pas écrite, sous son nom. Le siège, lui,
    corrige à découvert : chaque modification est journalisée avec avant
    et après. Sans auteur connu — import, compte disparu — la correction
    reste ouverte.
    """
    if acteur.role not in COUNTRY_ROLES:
        return
    if objet.created_by and objet.created_by != acteur.username:
        raise PermissionRefusee(_("Seul l'auteur d'un brouillon peut le modifier."))


#: Ce que dit un refus de modifier une ligne ou un dossier déclaré — les
#: mêmes phrases que les sérialiseurs, pour que la relecture sous verrou
#: réponde exactement ce qu'aurait répondu la validation.
VERROUILLE = {
    Expense: gettext_lazy(
        "Cette dépense est déclarée : elle ne peut plus être "
        "modifiée. Seul un brouillon reste modifiable."
    ),
    Dossier: gettext_lazy("Ce dossier est déclaré : il ne peut plus être modifié."),
}


def exiger_un_brouillon(objet):
    """Un dossier ou une ligne déclarés ne se modifient plus.

    Le sérialiseur le vérifie sur l'instance qu'il a reçue, lue **sans
    verrou** ; entre cette lecture et l'écriture, une soumission a pu
    passer. Les vues relisent donc l'objet sous verrou et redemandent ici,
    juste avant d'écrire : l'état qui compte est celui du verrou, pas
    celui de la lecture (audit du 8 septembre 2026, §3.6).
    """
    if objet.status in LOCKED_STATUSES:
        raise RegleViolee("non_field_errors", str(VERROUILLE[type(objet)]))


def exiger_les_quatre_yeux(objet, action, acteur):
    """Celui qui a saisi ou ouvert ne contrôle pas ce qu'il a saisi.

    Sur une ligne, l'absence d'auteur est rédhibitoire : on ne tranche pas
    une ligne d'origine inconnue. Sur un dossier sans auteur (import, compte
    supprimé), la règle joue sur chaque ligne, qui refuse tout contrôle sans
    auteur.
    """
    if action not in FOUR_EYES_ACTIONS:
        return
    if isinstance(objet, Expense) and not objet.created_by:
        raise RegleViolee(
            "created_by",
            _("Cette dépense n'a pas d'auteur connu : elle ne peut pas être contrôlée."),
        )
    if breaks_four_eyes(action, objet.created_by, acteur.username):
        if isinstance(objet, Dossier):
            raise PermissionRefusee(
                _("Vous avez ouvert ce dossier : son contrôle revient à quelqu'un d'autre.")
            )
        raise PermissionRefusee(
            _("Vous avez saisi cette dépense : son contrôle revient à quelqu'un d'autre.")
        )


def sans_preuve(dossier):
    """Le dossier est-il dépourvu de pièce exploitable ?"""
    return not dossier.proofs.exclude(
        status__in=[Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED]
    ).exists()


def exiger_un_dossier_ouvert(dossier):
    """Une ligne ne rejoint qu'un dossier encore en brouillon.

    Sans ce refus, la ligne arrivait en brouillon dans un dossier déjà
    passé : plus rien ne pouvait la soumettre, et la dépense restait
    indéfiniment en suspens dans un dossier clos.
    """
    if dossier is not None and dossier.status in LOCKED_STATUSES:
        raise RegleViolee(
            "dossier",
            _(
                "Le dossier {number} est déjà déclaré ({status}) : il "
                "n'accepte plus de nouvelle ligne. Ouvrez un nouveau "
                "dossier pour cette dépense."
            ).format(
                number=dossier.number, status=dossier.get_status_display().lower()
            ),
        )


def _detail(lignes):
    return ", ".join(
        f"{e.title} ({e.get_status_display().lower()})" for e in lignes[:5]
    )


# --- Verrous pour les vues de saisie -------------------------------------------


def verrouiller(objet):
    """Relit un dossier ou une ligne sous verrou, avec ses relations.

    Pour les vues de modification : elles reçoivent une instance lue sans
    verrou par ``get_object`` ; c'est celle-ci qu'elles doivent remplacer
    avant de vérifier l'état et d'écrire. À appeler dans une transaction.
    """
    return _CIRCUITS[type(objet)][0](objet)


def verrouiller_le_dossier_vise(dossier, ligne):
    """Le dossier qu'une ligne rejoint (ou garde), relu sous verrou.

    ``dossier`` est celui de la charge utile, ``None`` si elle n'en donne
    pas : c'est alors celui de la ligne. Rend ``None`` sans dossier.
    """
    vise = dossier if dossier is not None else getattr(ligne, "dossier", None)
    if vise is None:
        return None
    try:
        return _verrouiller_le_dossier(vise)
    except Dossier.DoesNotExist:
        # Retiré par son auteur pendant qu'on attendait son verrou : il
        # n'existe plus, ni pour cette écriture ni pour personne.
        raise HorsPerimetre() from None


# --- Le dossier ---------------------------------------------------------------


def _verrouiller_le_dossier(dossier):
    return (
        Dossier.objects.select_related("country", "team", "owner")
        .select_for_update(of=("self",))
        .get(pk=dossier.pk)
    )


def _instantane_du_dossier(dossier):
    return {
        "status": dossier.status,
        "note": dossier.note,
        "reopen_note": dossier.reopen_note,
    }


def _exiger_les_lignes(dossier, *, attendus, consigne):
    """Le dossier ne dit pas autre chose que ses lignes.

    Un dossier « justifié » portant une ligne encore soumise mentirait :
    le total justifié, lui, n'aurait pas bougé.
    """
    en_suspens = dossier.expenses.exclude(status__in=attendus)
    if not en_suspens.exists():
        return
    raise RegleViolee(
        "expenses",
        _(
            "{count} ligne(s) ne sont pas dans l'état attendu : "
            "{detail}. {instruction}"
        ).format(
            count=en_suspens.count(), detail=_detail(en_suspens), instruction=consigne
        ),
    )


def _exiger_equipe_et_owner(lignes):
    """Une dépense déclarée dit qui l'a engagée (cahier des charges §7).

    L'équipe et le manager sont facultatifs en brouillon : l'import du
    classeur historique et une saisie en plusieurs fois doivent pouvoir
    laisser la ligne incomplète. Mais une dépense soumise sans eux ne
    s'imputerait que sur l'enveloppe du pays et ne répondrait pas à la
    question « au profit de qui ». Lieu, projet et intitulé restent
    facultatifs : décision consignée dans ``docs/model-de-donnees.md``.
    """
    incompletes = []
    for ligne in lignes:
        manques = []
        if ligne.team_id is None:
            manques.append(_("sans équipe"))
        if ligne.owner_id is None:
            manques.append(_("sans manager"))
        if manques:
            incompletes.append(f"« {ligne.title} » ({', '.join(manques)})")
    if not incompletes:
        return
    detail = ", ".join(incompletes[:5])
    if len(incompletes) > 5:
        detail += _(" et {count} autre(s)").format(count=len(incompletes) - 5)
    raise RegleViolee(
        "expenses",
        _(
            "{count} ligne(s) incomplète(s) : {detail}. Renseignez "
            "l'équipe et le manager de chaque ligne avant de "
            "soumettre le dossier."
        ).format(count=len(incompletes), detail=detail),
    )


def _soumettre_les_lignes(dossier, acteur, trace, resultat):
    """Le dossier et ses lignes partent ensemble.

    Côté pays, déclarer une dépense doit tenir en une action : remplir les
    lignes, joindre la pièce, soumettre. Soumettre chaque ligne puis le
    dossier serait une cérémonie sans objet.

    Le coût ne suit pas le nombre de lignes : l'enveloppe est résolue une
    fois par clé d'imputation, verrouillée une fois, son total engagé
    calculé une fois puis accumulé ; lignes et traces sont écrites en bloc.
    """
    # Les lignes sont verrouillées avec le dossier : une ligne modifiée
    # entre la lecture et l'écriture partirait avec un montant périmé.
    lignes = list(
        dossier.expenses.select_for_update(of=("self",)).select_related(
            "country", "project", "team", "owner"
        )
    )
    if not lignes:
        raise RegleViolee(
            "expenses",
            _(
                "Un dossier se soumet avec ses lignes de dépenses : "
                "ajoutez-en au moins une."
            ),
        )
    brouillons = [e for e in lignes if e.status == Status.DRAFT]
    _exiger_equipe_et_owner(brouillons)

    # Une résolution par clé d'imputation, pas par ligne.
    par_cle = {}
    for expense in brouillons:
        cle = cle_d_imputation(expense)
        if cle in par_cle:
            expense.budget = par_cle[cle]
        else:
            par_cle[cle] = attach_budget(expense)

    # Verrou : deux soumissions simultanées ne doivent pas franchir la
    # même enveloppe chacune de leur côté. Une requête pour toutes.
    # ``of=("self",)`` : seule l'enveloppe est verrouillée, pas les
    # référentiels joints — Postgres refuse un verrou sur le côté
    # nullable d'une jointure externe.
    verrouillees = (
        Budget.objects.select_for_update(of=("self",))
        .select_related("country", "project", "team", "manager")
        .in_bulk({b.pk for b in par_cle.values()})
    )
    engage = {pk: None for pk in verrouillees}
    depassements = {}
    maintenant = timezone.now()
    for expense in brouillons:
        budget = verrouillees[expense.budget_id]
        if engage[budget.pk] is None:
            # Les brouillons n'y figurent pas : rien à exclure.
            engage[budget.pk] = committed_total(budget)
        expense.budget = budget
        avertissement = check_budget_capacity(
            expense, budget, acteur.role, committed=engage[budget.pk]
        )
        engage[budget.pk] += expense.amount
        if avertissement:
            # Le dernier message d'une enveloppe porte le dépassement
            # cumulé : un seul avertissement par enveloppe suffit.
            depassements[budget.pk] = avertissement
        expense.status = Status.SUBMITTED
        expense.updated_at = maintenant

    Expense.objects.bulk_update(brouillons, ["budget", "status", "updated_at"])
    resultat.audit.extend(
        enregistrer(
            preparer(
                trace,
                AuditLog.Action.SUBMITTED,
                expense,
                from_status=Status.DRAFT,
                to_status=Status.SUBMITTED,
                note="soumise avec son dossier",
            )
            for expense in brouillons
        )
    )

    avertissements = list(depassements.values())
    if sans_preuve(dossier) and WorkflowConfiguration.charger().warn_without_proof_submission:
        avertissements.append(str(SANS_PREUVE))
    return " ".join(avertissements) or None


def _rouvrir_les_lignes(dossier, motif, trace, resultat):
    """Le dossier rouvert emporte ses lignes au brouillon.

    Chaque ligne perd son imputation : elle n'est plus déclarée, elle ne
    pèse plus sur l'enveloppe — l'engagé disparaît, ce que le pays et le
    siège verront dans les chiffres. Les pièces déposées restent : elles
    n'ont pas cessé d'être des preuves, c'est la déclaration qu'on
    redemande. Une ligne déjà justifiée ou clôturée bloque tout : le
    siège a constaté, et un constat ne se défait pas ligne à ligne.
    """
    lignes = list(
        dossier.expenses.select_for_update(of=("self",)).select_related("country")
    )
    constatees = [e for e in lignes if e.status in REOPEN_BLOCKING_STATUSES]
    if constatees:
        raise RegleViolee(
            "expenses",
            _(
                "{count} ligne(s) ont déjà été constatées par le siège : "
                "{detail}. Un dossier ne se rouvre pas après constat."
            ).format(count=len(constatees), detail=_detail(constatees)),
        )

    maintenant = timezone.now()
    traces = []
    for ligne in lignes:
        if ligne.status == Status.DRAFT:
            continue
        traces.append(
            preparer(
                trace,
                AuditLog.Action.REOPENED,
                ligne,
                from_status=ligne.status,
                to_status=Status.DRAFT,
                note=motif,
                dossier=dossier.number,
                before={"status": ligne.status, "budget": ligne.budget_id},
                after={"status": Status.DRAFT, "budget": None},
            )
        )
        ligne.status = Status.DRAFT
        ligne.budget = None
        ligne.updated_at = maintenant
    Expense.objects.bulk_update(lignes, ["budget", "status", "updated_at"])
    resultat.audit.extend(enregistrer(traces))


def _avant_sur_le_dossier(dossier, action, acteur, note, donnees, trace, resultat):
    """Contrôles propres au dossier. Renvoie un avertissement ou ``None``."""
    if action == "submit":
        return _soumettre_les_lignes(dossier, acteur, trace, resultat)

    if action == "reopen":
        _rouvrir_les_lignes(dossier, note, trace, resultat)
        return None

    exiger_les_quatre_yeux(dossier, action, acteur)

    if action == "close":
        # Clôturer, c'est déclarer l'affaire terminée. Une ligne encore en
        # brouillon, soumise ou en contrôle n'a pas été tranchée : la
        # classer avec le dossier reviendrait à perdre la dépense de vue
        # sans jamais dire si elle est justifiée.
        _exiger_les_lignes(
            dossier,
            attendus=LINES_REQUIRED["close"],
            consigne=_("Justifiez-les ou marquez-les non justifiées avant de clôturer."),
        )

    if action == "justify":
        if sans_preuve(dossier):
            # Justifier un dossier sans preuve viderait de son sens
            # l'ensemble documentaire que le N°ORDRE représente. Une
            # pièce rejetée ou archivée n'en est pas une.
            raise RegleViolee(
                "proofs", _("Un dossier ne peut être justifié sans justificatif.")
            )
        _exiger_les_lignes(
            dossier,
            attendus=LINES_REQUIRED["justify"],
            consigne=_("Justifiez chaque ligne avant le dossier."),
        )

    if action == "reject":
        _exiger_les_lignes(
            dossier,
            attendus=LINES_REQUIRED["reject"],
            consigne=_(
                "Tranchez chaque ligne avant de constater la "
                "non-justification du dossier."
            ),
        )
    return None


def _appliquer_au_dossier(dossier, action, note, donnees):
    """Le motif d'une réouverture a son propre champ.

    ``note`` est la remarque de contrôle du siège ; une réouverture ne
    doit pas l'effacer, et son motif doit rester lisible sur la fiche
    même après que le pays a resoumis le dossier. Une rectification ne
    touche à aucune des deux : son motif vit sur la demande, et c'est la
    ligne qu'elle rectifie — le dossier ne fait que la suivre.
    """
    if action == "reopen":
        dossier.reopen_note = note
    elif action == "rectify":
        return
    elif note:
        dossier.note = note


def _apres_sur_le_dossier(dossier, action, note, trace):
    if action == "submit":
        triggers.dossier_submitted(dossier, trace.compte)
    elif action == "reopen":
        triggers.dossier_reopened(dossier, trace.compte, note)


# --- La ligne -------------------------------------------------------------------


def _verrouiller_la_ligne(expense):
    return (
        Expense.objects.select_related(*EXPENSE_RELATIONS)
        .select_for_update(of=("self",))
        .get(pk=expense.pk)
    )


def _instantane_de_la_ligne(expense):
    return {
        "status": expense.status,
        "justified_amount": str(expense.justified_amount),
        "control_note": expense.control_note,
    }


def _avant_sur_la_ligne(expense, action, acteur, note, donnees, trace, resultat):
    """Sépare la déclaration du contrôle, impute l'enveloppe et applique la
    politique de dépassement."""
    exiger_les_quatre_yeux(expense, action, acteur)
    if action != "justify":
        return None

    budget = attach_budget(expense)
    # Verrou sur l'enveloppe : la politique « soumettre à approbation »
    # se juge ici, sur un total engagé qui ne bouge pas sous nos pieds.
    budget = Budget.objects.select_for_update().get(pk=budget.pk)
    expense.budget = budget
    # L'imputation est persistée par la sauvegarde de la transition.
    return check_budget_capacity(expense, budget, acteur.role, at_approval=True)


def _appliquer_a_la_ligne(expense, action, note, donnees):
    """Le siège (DF) fixe ce qui est prouvé, et pourquoi.

    Le motif va dans ``control_note`` : ``note`` est la remarque du
    déclarant, qu'un rejet ne doit pas effacer.
    """
    if note:
        expense.control_note = note
    if action == "justify":
        justifie = donnees.get("justified_amount")
        if justifie is None:
            justifie = expense.amount
        if justifie > expense.amount:
            raise RegleViolee(
                "justified_amount",
                _(
                    "Le montant justifié ne peut pas dépasser la dépense ({amount})."
                ).format(amount=expense.amount),
            )
        expense.justified_amount = justifie
    elif action == "reject":
        # Non justifiée : rien n'est prouvé, l'écart est entier.
        expense.justified_amount = ZERO
    elif action == "rectify":
        # Le constat est défait : plus rien n'est tenu pour prouvé tant que
        # le siège n'a pas tranché à nouveau. L'imputation reste — la
        # dépense est toujours déclarée. Le motif de la rectification
        # prend la place de la remarque de contrôle qu'il remet en cause.
        expense.justified_amount = ZERO


def _apres_sur_la_ligne(expense, action, note, trace):
    if action == "reject":
        triggers.expense_rejected(expense, trace.compte, note)


#: Ce qui distingue le circuit d'un dossier de celui d'une ligne : verrou,
#: photographie pour le journal, contrôles préalables, décision, effets.
_CIRCUITS = {
    Dossier: (
        _verrouiller_le_dossier, _instantane_du_dossier,
        _avant_sur_le_dossier, _appliquer_au_dossier, _apres_sur_le_dossier,
    ),
    Expense: (
        _verrouiller_la_ligne, _instantane_de_la_ligne,
        _avant_sur_la_ligne, _appliquer_a_la_ligne, _apres_sur_la_ligne,
    ),
}


def _transition(objet, action, acteur, trace, *, note="", justified_amount=None):
    """Tronc commun d'une transition : verrou, état, rôle, contrôles, journal.

    Le rôle a pu être vérifié par la vue (``RolePermission``) ; il l'est de
    nouveau ici, pour que le service se suffise. L'objet est relu sous
    verrou : celui qu'on nous donne a été lu avant, et deux personnes du
    siège qui tranchent la même ligne au même instant liraient tous deux
    « soumise » et passeraient tous deux — le second écraserait le premier
    sans que le journal ne le dise.
    """
    verrouiller, instantane, avant, appliquer, apres = _CIRCUITS[type(objet)]
    exiger_la_capacite(ACTION_CAPACITES[action], acteur)
    note = (note or "").strip()
    if action in MOTIVATED_ACTIONS and not note:
        raise RegleViolee("note", str(MOTIF_MANQUANT[action]))
    donnees = {"justified_amount": justified_amount}

    with transaction.atomic():
        instance = verrouiller(objet)
        target = next_status(action, instance.status, WorkflowConfiguration.charger())
        previous = instance.status
        photo = instantane(instance)
        resultat = Resultat(instance)
        resultat.warning = avant(instance, action, acteur, note, donnees, trace, resultat)

        instance.status = target
        appliquer(instance, action, note, donnees)
        instance.save()

        resultat.audit.append(
            record(
                trace,
                AUDIT_ACTIONS[action],
                instance,
                country=instance.country,
                from_status=previous,
                to_status=target,
                note=note,
                before=photo,
                after=instantane(instance),
            )
        )
        apres(instance, action, note, trace)
    return resultat


# --- Services ---------------------------------------------------------------------


def soumettre(dossier, acteur, trace):
    """Déclare le dossier : ses lignes partent avec lui.

    Un dossier vide ne se soumet pas ; un dossier sans pièce se soumet avec
    un avertissement (``Resultat.warning``), de même qu'un dépassement que
    la politique de l'enveloppe tolère.
    """
    return _transition(dossier, "submit", acteur, trace)


def rouvrir(dossier, acteur, motif, trace):
    """Renvoie un dossier déclaré au brouillon, pour demander des comptes.

    Seule exception à l'irréversibilité (voir ``workflow``) : réservée aux
    administrateurs, motivée, refusée dès qu'une ligne a été constatée,
    tracée sur le dossier et sur chaque ligne. Il n'existe pas d'équivalent
    sur une ligne : le dossier emporte ses lignes, à la réouverture comme à
    la soumission.
    """
    return _transition(dossier, "reopen", acteur, trace, note=motif)


def mettre_en_controle(objet, acteur, trace):
    """Prend un dossier ou une ligne soumis en contrôle (le DM)."""
    return _transition(objet, "review", acteur, trace)


def trancher(objet, action, acteur, *, note="", justified_amount=None, trace):
    """Le siège constate : ``justify`` ou ``reject``, sur un dossier ou une ligne.

    Sur une ligne, ``justified_amount`` fixe ce qui est prouvé (toute la
    dépense par défaut, jamais plus) ; un rejet le remet à zéro et exige un
    motif. Sur un dossier, la décision exige que chaque ligne soit déjà
    tranchée.
    """
    if action not in ("justify", "reject"):
        raise ValueError(f"trancher : action inconnue {action!r}")
    return _transition(
        objet, action, acteur, trace, note=note, justified_amount=justified_amount
    )


def cloturer(objet, acteur, trace):
    """Clôt un dossier ou une ligne justifiés : l'affaire est terminée."""
    return _transition(objet, "close", acteur, trace)


#: Nom d'action de l'API → service. Les vues passent par ici ; un appelant
#: qui sait ce qu'il fait appelle le service par son nom.
def executer(objet, action, acteur, trace, *, note="", justified_amount=None):
    """Joue une transition nommée comme dans l'API (``submit``, ``review``…).

    ``rectify`` n'en fait pas partie : un constat ne se défait qu'à
    l'approbation d'une demande (:func:`approuver_rectification`).
    """
    if action == "rectify":
        raise ValueError("executer : rectify ne se joue qu'en approuvant une demande")
    if action == "submit":
        return soumettre(objet, acteur, trace)
    if action == "reopen":
        return rouvrir(objet, acteur, note, trace)
    if action == "review":
        return mettre_en_controle(objet, acteur, trace)
    if action == "close":
        return cloturer(objet, acteur, trace)
    return trancher(
        objet, action, acteur, note=note, justified_amount=justified_amount, trace=trace
    )


@transaction.atomic
def retirer_brouillon(objet, acteur, trace):
    """Retire un brouillon — dossier ou ligne — par son auteur.

    Une fois déclaré, l'effacer reviendrait à perdre la trace de l'argent :
    c'est précisément ce que l'application doit empêcher. Un brouillon
    jamais soumis n'a en revanche aucune valeur probante. Un dossier part
    avec ses lignes et ses pièces, chacune laissant sa trace ; il ne se
    retire pas s'il porte la ligne d'un autre auteur — ce serait effacer le
    travail de quelqu'un d'autre sous couvert de ranger le sien.
    """
    exiger_la_capacite("expenses.delete", acteur)
    instance = (
        type(objet)._default_manager.select_related("country")
        .select_for_update(of=("self",))
        .get(pk=objet.pk)
    )
    if instance.status not in DELETABLE_STATUSES:
        raise RegleViolee(
            "status",
            _(
                "Cet élément est déclaré : il ne peut plus être "
                "supprimé. Seul un brouillon peut l'être."
            ),
        )
    if instance.created_by and instance.created_by != acteur.username:
        raise PermissionRefusee(_("Seul l'auteur d'un brouillon peut le supprimer."))

    resultat = Resultat(instance)
    if isinstance(instance, Expense):
        resultat.audit.append(
            record(
                trace, AuditLog.Action.DELETED, instance,
                label=f"Brouillon supprimé — {instance}", amount=str(instance.amount),
            )
        )
        instance.delete()
        return resultat

    lignes = _retirer_le_contenu(instance, acteur, trace, resultat)
    resultat.audit.append(
        record(
            trace, AuditLog.Action.DELETED, instance,
            label=f"Brouillon supprimé — {instance}", lines=lignes,
        )
    )
    instance.delete()
    return resultat


def _retirer_le_contenu(dossier, acteur, trace, resultat):
    """Les lignes et les pièces d'un brouillon de dossier, une à une.

    Les lignes sont protégées en base contre la cascade : elles sont
    retirées une à une, chacune laissant sa trace. Rend le nombre de lignes.

    Lignes et pièces sont lues **sous verrou**, comme le dossier : une
    ligne lue sans verrou pouvait être soumise entre la lecture et le
    retrait. Les fichiers, eux, ne s'effacent pas ici — un stockage n'a
    pas de retour arrière — mais après le commit (``stockage``).
    """
    lignes = list(
        dossier.expenses.select_for_update(of=("self",)).select_related("country")
    )
    autrui = [
        ligne for ligne in lignes
        if ligne.created_by and ligne.created_by != acteur.username
    ]
    if autrui:
        raise PermissionRefusee(
            _(
                "Ce dossier contient des lignes saisies par quelqu'un "
                "d'autre ({author}) : il ne peut pas être supprimé."
            ).format(author=autrui[0].created_by)
        )
    if any(ligne.status != Status.DRAFT for ligne in lignes):
        raise RegleViolee(
            "expenses",
            _("Ce dossier contient une ligne déclarée : il ne peut plus être supprimé."),
        )

    for ligne in lignes:
        resultat.audit.append(
            record(
                trace, AuditLog.Action.DELETED, ligne,
                label=f"Brouillon supprimé avec son dossier — {ligne}",
                amount=str(ligne.amount), dossier=dossier.number,
            )
        )
        ligne.delete()

    # La plus récente d'abord : une nouvelle version référence celle
    # qu'elle remplace, et cette référence est protégée.
    pieces = (
        dossier.proofs.select_for_update(of=("self",))
        .select_related("dossier__country")
        .order_by("-pk")
    )
    for piece in pieces:
        resultat.audit.append(
            record(
                trace, AuditLog.Action.DELETED, piece,
                label=f"Justificatif supprimé avec son dossier — {piece}",
                country=dossier.country, sha256=piece.sha256, version=piece.version,
                dossier=dossier.number,
            )
        )
        # Le fichier ne doit pas survivre à sa fiche : un stockage qui
        # garde des pièces orphelines finit par en servir à tort. Mais il
        # ne s'efface qu'une fois le retrait acquis, après le commit.
        stockage.programmer_la_suppression(piece, trace=trace, dossier=dossier)
        piece.delete()
    return len(lignes)


@transaction.atomic
def controler_piece(proof, statut, acteur, *, motif="", trace):
    """Contrôle documentaire : valide, rejette ou signale un justificatif.

    Relève du siège (``proofs.review``), pas du déposant. Une pièce d'un
    dossier clôturé ne se contrôle plus, comme il ne s'en dépose plus ; les
    états atteignables sont ceux de ``PROOF_TRANSITIONS``.
    """
    exiger_la_capacite("proofs.review", acteur)
    motif = (motif or "").strip()
    piece = (
        Proof.objects.select_related("dossier__country")
        .select_for_update(of=("self",))
        .get(pk=proof.pk)
    )
    if piece.dossier.status in PROOF_LOCKED_STATUSES:
        raise RegleViolee(
            "status",
            _("Le dossier est clôturé : ses justificatifs ne se contrôlent plus."),
        )
    next_proof_status(piece.status, statut, dict(Proof.ProofStatus.choices))

    previous = piece.status
    piece.status = statut
    piece.rejection_reason = motif if statut == Proof.ProofStatus.REJECTED else ""
    piece.is_complete = statut != Proof.ProofStatus.INCOMPLETE
    piece.save()

    entree = record(
        trace,
        PROOF_AUDIT_ACTIONS[statut],
        piece,
        country=piece.dossier.country,
        from_status=previous,
        to_status=statut,
        reason=motif,
    )
    return Resultat(piece, audit=[entree])


# --- La rectification (seconde exception) ---------------------------------------


def _exiger_le_perimetre(acteur, expense):
    """La ligne est dans le périmètre de l'acteur, sinon elle n'existe pas
    pour lui — pays, et équipes pour un manager qui y est restreint."""
    if acteur is None:
        raise HorsPerimetre()
    if not acteur.has_global_scope and expense.country_id not in acteur.country_ids:
        raise HorsPerimetre()
    if acteur.team_ids is not None and expense.team_id not in acteur.team_ids:
        raise HorsPerimetre()


def verifier_la_decision_de_rectification(rectification, acteur):
    """La demande se décide-t-elle, et par cet acteur ?

    Deux refus, deux codes : déjà traitée (400), demandée par l'acteur
    lui-même (403 — demander et trancher sont deux regards, comme pour une
    réallocation).
    """
    if rectification.status != Rectification.Status.PENDING:
        raise RegleViolee(
            "status", _("Cette demande de rectification a déjà été traitée.")
        )
    if rectification.requested_by and rectification.requested_by == acteur.username:
        raise PermissionRefusee(
            _("Vous ne pouvez pas décider d'une rectification que vous avez demandée.")
        )


def peut_decider_rectification(rectification, acteur, configuration=None):
    """``can_decide`` : les mêmes conditions que la décision, en booléen.

    ``configuration`` évite à une liste de relire la matrice ligne par ligne.
    """
    if acteur is None or acteur.role not in roles_pour(
        "rectifications.decide", configuration
    ):
        return False
    try:
        verifier_la_decision_de_rectification(rectification, acteur)
    except (RegleViolee, PermissionRefusee):
        return False
    return True


def _verrouiller_la_demande(rectification, acteur):
    """Relit la demande sous verrou et vérifie qu'elle se décide.

    Le statut est contrôlé **après** la prise du verrou : lu avant, deux
    approbations simultanées le verraient toutes deux « en attente » et
    défaisaient le constat deux fois.
    """
    verrouillee = (
        Rectification.objects.select_related("expense__country", "expense__dossier")
        .select_for_update(of=("self",))
        .get(pk=rectification.pk)
    )
    verifier_la_decision_de_rectification(verrouillee, acteur)
    return verrouillee


def _journaliser_la_demande(trace, action, rectification, **detail):
    return record(
        trace, action, rectification,
        country=rectification.expense.country,
        expense=rectification.expense_id,
        dossier=rectification.expense.dossier.number,
        **detail,
    )


def _decider_la_demande(rectification, acteur, note, trace, statut):
    """Tronc commun d'une décision : statut, motif, signature, journal."""
    rectification.status = statut
    rectification.decision_note = note
    rectification.decided_by = acteur.username
    rectification.decided_at = timezone.now()
    rectification.save()
    return _journaliser_la_demande(
        trace, AuditLog.Action.RECTIFICATION_DECIDED, rectification,
        from_status=Rectification.Status.PENDING, to_status=statut, note=note,
    )


@transaction.atomic
def demander_rectification(expense, acteur, motif, trace):
    """Demande la rectification d'un constat : une ligne justifiée ou
    clôturée l'a été à tort, et voici pourquoi.

    Ouverte à tous par défaut (``rectifications.request``) : le pays voit
    l'erreur le premier. La ligne ne bouge pas — seule la décision la fera
    revenir en contrôle — mais la demande relève ce qu'elle remet en cause
    (état, montant justifié), pour que le journal et la fiche le disent
    encore quand la ligne aura été tranchée à nouveau. Une seule demande
    en attente par ligne : la contrainte en base y veille aussi.
    """
    exiger_la_capacite("rectifications.request", acteur)
    _exiger_le_perimetre(acteur, expense)
    motif = (motif or "").strip()
    if not motif:
        raise RegleViolee("motif", str(MOTIF_MANQUANT["rectify"]))
    ligne = _verrouiller_la_ligne(expense)
    if ligne.status not in RECTIFIABLE_STATUSES:
        raise RegleViolee(
            "status",
            _(
                "Seule une ligne justifiée ou clôturée se rectifie : "
                "celle-ci est « {status} »."
            ).format(status=ligne.get_status_display().lower()),
        )
    if ligne.rectifications.filter(status=Rectification.Status.PENDING).exists():
        raise RegleViolee(
            "expense",
            _("Une demande de rectification est déjà en attente sur cette ligne."),
        )
    demande = Rectification.objects.create(
        expense=ligne,
        motif=motif,
        requested_by=acteur.username,
        previous_status=ligne.status,
        previous_justified_amount=ligne.justified_amount,
    )
    entree = _journaliser_la_demande(
        trace, AuditLog.Action.RECTIFICATION_REQUESTED, demande,
        from_status=ligne.status, note=motif,
        justified_amount=str(ligne.justified_amount),
    )
    triggers.rectification_requested(demande, trace.compte)
    return Resultat(demande, audit=[entree])


@transaction.atomic
def approuver_rectification(rectification, acteur, note, trace):
    """Approuve la demande : la ligne revient en contrôle, le dossier la suit.

    Deux verrous dans l'ordre du circuit — le dossier, puis la ligne —
    comme à la soumission et à la réouverture : une clôture du dossier
    prise au même instant attend, et trouve la ligne revenue en contrôle
    au lieu de clore par-dessus. La transition ``rectify`` passe par le
    tronc commun (``_transition``) : état de départ vérifié, journal
    ``rectified`` avec avant et après, montant justifié remis à zéro. Le
    dossier ne suit que s'il avait été constaté (justifié, non justifié ou
    clôturé) : un dossier encore en contrôle n'a rien à défaire.
    """
    exiger_la_capacite("rectifications.decide", acteur)
    note = (note or "").strip()
    demande = _verrouiller_la_demande(rectification, acteur)
    _exiger_le_perimetre(acteur, demande.expense)
    dossier = _verrouiller_le_dossier(demande.expense.dossier)

    ligne = _transition(demande.expense, "rectify", acteur, trace, note=demande.motif)
    traces = list(ligne.audit)
    if dossier.status in DECIDED_STATUSES:
        suivi = _transition(dossier, "rectify", acteur, trace, note=demande.motif)
        traces.extend(suivi.audit)

    traces.append(
        _decider_la_demande(demande, acteur, note, trace, Rectification.Status.APPROVED)
    )
    triggers.rectification_decided(demande, trace.compte)
    return Resultat(demande, audit=traces)


@transaction.atomic
def refuser_rectification(rectification, acteur, note, trace):
    """Refuse la demande : le constat tient. Le refus est motivé — le
    demandeur doit savoir pourquoi on ne le suit pas."""
    exiger_la_capacite("rectifications.decide", acteur)
    note = (note or "").strip()
    if not note:
        raise RegleViolee("note", _("Un refus doit être motivé."))
    demande = _verrouiller_la_demande(rectification, acteur)
    _exiger_le_perimetre(acteur, demande.expense)
    entree = _decider_la_demande(
        demande, acteur, note, trace, Rectification.Status.REFUSED
    )
    triggers.rectification_decided(demande, trace.compte)
    return Resultat(demande, audit=[entree])
