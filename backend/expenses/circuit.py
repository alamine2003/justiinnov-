"""Le circuit de justification : soumettre, rouvrir, contrôler, trancher,
clôturer, renommer (décisions 41 et 131).

Un tronc commun (:func:`_transition`) — verrou, état, capacité, journal — et
ce qui distingue un dossier d'une ligne (``_CIRCUITS``). Les vues passent par
:func:`executer` ; la saisie et la rectification réutilisent ses verrous et
son tronc.
"""

from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from accounts.permissions import exiger_la_capacite
from budget.models import Budget
from core.models import WorkflowConfiguration
from core.regles import PermissionRefusee, RegleViolee
from notifications import triggers

from .audit import enregistrer, preparer, record
from .exigences import (
    MOTIF_MANQUANT,
    Resultat,
    _detail,
    exiger_l_auteur_du_brouillon,
    exiger_les_quatre_yeux,
    relire_sous_verrou,
    sans_preuve,
)
from .models import (
    ZERO,
    AuditLog,
    Dossier,
    Expense,
)
from .services import (
    attach_budget,
    check_budget_capacity,
    cle_d_imputation,
    committed_total,
)
from .workflow import (
    ACTION_CAPACITES,
    LINES_REQUIRED,
    MOTIVATED_ACTIONS,
    PROOF_LOCKED_STATUSES,
    REOPEN_BLOCKING_STATUSES,
    Status,
    a_ete_declare,
    next_status,
)


#: Signalé au pays quand il soumet sans pièce. La soumission passe quand même :
#: bloquer reviendrait à ce qu'une dépense sans reçu ne soit jamais déclarée,
#: donc à ce que l'argent sorte sans laisser de trace — pire que l'écart.
SANS_PREUVE = gettext_lazy(
    "%(count)s ligne(s) sans justificatif : elles sont déclarées sans preuve, "
    "elles creuseront l'écart et seront signalées au siège."
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


# --- Le dossier ---------------------------------------------------------------


def _verrouiller_le_dossier(dossier):
    return relire_sous_verrou(
        Dossier.objects.select_related("country", "team", "owner")
        .select_for_update(of=("self",)),
        dossier.pk,
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


def _exiger_les_auteurs_des_lignes(brouillons, acteur):
    """Une ligne en brouillon ne part que sous la main de son auteur.

    Le dossier se soumet par son auteur (``exiger_l_auteur_du_brouillon``),
    mais un dossier sans auteur connu peut porter les lignes de plusieurs
    collègues : le premier qui le soumettait déclarait, sous son nom, ce
    que les autres n'avaient pas fini de saisir (décision 114). Une ligne
    sans auteur connu reste soumise par qui déclare le dossier, comme
    avant (migration ``expenses.0017``).

    La règle ne vise que les lignes **jamais déclarées** : une ligne déjà
    soumise, revenue au brouillon par une réouverture, a été déclarée par
    son auteur. Elle repart avec le dossier — sans quoi un dossier rouvert
    dont une ligne porte un autre auteur (un collègue parti, des données
    d'avant la décision 89) ne se resoumettait plus jamais : ni
    modifiable, ni retirable, ni déclarable.
    """
    autrui = [
        ligne for ligne in brouillons
        if ligne.created_by and ligne.created_by != acteur.username
        and not a_ete_declare(ligne)
    ]
    if autrui:
        raise PermissionRefusee(
            _(
                "Ce dossier contient {count} ligne(s) en brouillon saisie(s) "
                "par quelqu'un d'autre ({author}) : seul leur auteur peut "
                "les déclarer."
            ).format(count=len(autrui), author=autrui[0].created_by)
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
    _exiger_les_auteurs_des_lignes(brouillons, acteur)
    _exiger_equipe_et_owner(brouillons)

    # Une résolution par clé d'imputation, pas par ligne.
    par_cle: dict[tuple[Any, ...], Any] = {}
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
    reprises = set()
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
        # Même règle que pour le dossier : une ligne sans auteur connu prend
        # celui qui la déclare, sans quoi elle ne se contrôlerait jamais
        # (``exiger_un_auteur``) et resterait engagée sans issue.
        if not expense.created_by:
            expense.created_by = acteur.username
            reprises.add(expense.pk)

    Expense.objects.bulk_update(
        brouillons, ["budget", "status", "updated_at", "created_by"]
    )
    resultat.audit.extend(
        enregistrer(
            preparer(
                trace,
                AuditLog.Action.SUBMITTED,
                expense,
                from_status=Status.DRAFT,
                to_status=Status.SUBMITTED,
                note=(
                    "soumise avec son dossier ; sans auteur connu, elle prend "
                    "celui qui la déclare"
                    if expense.pk in reprises
                    else "soumise avec son dossier"
                ),
            )
            for expense in brouillons
        )
    )

    avertissements = list(depassements.values())
    manquantes = sans_preuve(dossier)
    if manquantes and WorkflowConfiguration.charger().warn_without_proof_submission:
        avertissements.append(str(SANS_PREUVE) % {"count": manquantes})
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
        # Un brouillon part par son auteur : un collègue du pays ne déclare
        # pas à la place de qui saisit encore.
        exiger_l_auteur_du_brouillon(
            dossier, acteur, _("Seul l'auteur d'un brouillon peut le soumettre.")
        )
        # Un brouillon sans auteur connu — compte disparu, brouillon rendu au
        # pays (décision 89) — prend pour auteur celui qui le déclare : sans
        # auteur, la règle des quatre yeux ne pourrait pas se vérifier et
        # plus personne ne pourrait le contrôler.
        if not dossier.created_by:
            dossier.created_by = acteur.username
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
        manquantes = dossier.lignes_a_prouver_pour_clore().count()
        if manquantes:
            # Une pièce rejetée après la justification laisse sa ligne sans
            # preuve : clôturer figerait pour toujours un constat que plus
            # rien ne soutient (décisions 107 et 115). Le pays dépose une
            # autre pièce — possible jusqu'à la clôture —, ou le constat se
            # fait rectifier. Une ligne constatée non justifiée n'en attend
            # pas : l'absence de preuve est ce qu'on a constaté.
            raise RegleViolee(
                "proofs",
                _("%(count)s ligne(s) sans justificatif : le dossier ne peut pas être clôturé.")
                % {"count": manquantes},
            )

    if action == "justify":
        manquantes = sans_preuve(dossier)
        if manquantes:
            # Justifier un dossier dont une ligne n'a pas de preuve viderait
            # de son sens le constat : chaque ligne a sa pièce (décision
            # 107). Une pièce rejetée ou archivée n'en est pas une.
            raise RegleViolee(
                "proofs",
                _("%(count)s ligne(s) sans justificatif : le dossier ne peut pas être justifié.")
                % {"count": manquantes},
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
    return relire_sous_verrou(
        Expense.objects.avec_les_relations().select_for_update(of=("self",)),
        expense.pk,
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
    """L'administrateur fixe ce qui est prouvé, et pourquoi.

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


def mettre_en_controle(objet, acteur, trace, *, note=""):
    """Prend un dossier ou une ligne soumis en contrôle (l'administrateur).

    ``note``, facultative, est la remarque de contrôle : gardée sur l'objet
    (``Dossier.note``, ``Expense.control_note``) et au journal.
    """
    return _transition(objet, "review", acteur, trace, note=note)


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


def cloturer(objet, acteur, trace, *, note=""):
    """Clôt un dossier ou une ligne justifiés : l'affaire est terminée.

    ``note``, facultative, est gardée comme celle d'une mise en contrôle.
    """
    return _transition(objet, "close", acteur, trace, note=note)


#: Nom d'action de l'API → service. Une action nouvelle s'ajoute ici, sans
#: rouvrir :func:`executer` (décision 124). Le motif suit chaque
#: transition : l'API l'accepte partout, et une remarque saisie puis perdue
#: sans un mot ferait croire qu'elle est gardée. Les décisions du siège
#: (``validate``, ``reject``…) passent par :func:`trancher`.
_SERVICES = {
    "submit": lambda objet, acteur, trace, note, montant: soumettre(objet, acteur, trace),
    "reopen": lambda objet, acteur, trace, note, montant: rouvrir(objet, acteur, note, trace),
    "review": lambda objet, acteur, trace, note, montant: mettre_en_controle(
        objet, acteur, trace, note=note
    ),
    "close": lambda objet, acteur, trace, note, montant: cloturer(objet, acteur, trace, note=note),
}


def executer(objet, action, acteur, trace, *, note="", justified_amount=None):
    """Joue une transition nommée comme dans l'API (``submit``, ``review``…).
    Les vues passent par ici ; un appelant qui sait ce qu'il fait appelle le
    service par son nom.

    ``rectify`` n'en fait pas partie : un constat ne se défait qu'à
    l'approbation d'une demande (:func:`approuver_rectification`).
    """
    if action == "rectify":
        raise ValueError("executer : rectify ne se joue qu'en approuvant une demande")
    service = _SERVICES.get(action)
    if service is not None:
        return service(objet, acteur, trace, note, justified_amount)
    return trancher(
        objet, action, acteur, note=note, justified_amount=justified_amount, trace=trace
    )


@transaction.atomic
def renommer(dossier, label, acteur, trace):
    """Change le titre d'un dossier, jusqu'à sa clôture (décisions 104 et 108).

    Le titre ne porte ni montant ni preuve : le changer ne touche à rien de
    ce qui a été déclaré. Une fois le dossier clôturé, plus rien ne bouge,
    pas même le titre. L'ancien et le nouveau titre restent au journal
    d'audit.
    """
    exiger_la_capacite("dossiers.rename", acteur)
    instance = relire_sous_verrou(
        Dossier.objects.select_related("country").select_for_update(of=("self",)),
        dossier.pk,
    )
    if instance.status in PROOF_LOCKED_STATUSES:
        raise RegleViolee("status", _("Un dossier clôturé ne se renomme plus."))
    nouveau = (label or "").strip()
    if not nouveau:
        raise RegleViolee("label", _("Le titre d'un dossier ne peut pas être vide."))
    ancien = instance.label
    resultat = Resultat(instance)
    if nouveau == ancien:
        return resultat
    instance.label = nouveau
    instance.save(update_fields=["label", "updated_at"])
    resultat.audit.append(
        record(
            trace, AuditLog.Action.RENAMED, instance,
            label=f"{instance.number} — {nouveau}"[:250],
            avant={"label": ancien}, apres={"label": nouveau},
        )
    )
    return resultat
