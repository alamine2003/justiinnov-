"""La synthèse de l'audit : ce que le super administrateur doit voir d'un coup d'œil (décision 111).

Les deux journaux — le circuit (``AuditLog``) et le référentiel, les
comptes et la configuration (``ChangeLog``) — lus sur une période et,
au besoin, un pays. Tout se compte ici, en base : l'interface affiche.

- **compteurs** : ce qui a été déclaré et tranché, et ce qui demande
  attention — réouvertures, rectifications, refus, sorties de données,
  imports, changements de droits, échecs de connexion, 2FA réinitialisées ;
- **par jour**, **par utilisateur**, **par pays** : où et par qui ;
- **à surveiller** : les derniers événements sensibles, en clair.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.models import ChangeLog

from .historique import _entree_circuit, _entree_referentiel
from .models import AuditLog

#: Période par défaut : les trente derniers jours.
JOURS_PAR_DEFAUT = 30
#: Utilisateurs les plus actifs montrés.
PREMIERS = 10
#: Événements sensibles montrés.
A_SURVEILLER = 20

A = AuditLog.Action
C = ChangeLog.Actions

#: Compteurs du circuit : clé de l'interface → couples (actions du journal
#: d'audit, objet compté ; ``None`` : tout objet). Une soumission ou une
#: réouverture s'écrit sur le dossier **et** sur chacune de ses lignes :
#: elle se compte une fois, sur le dossier. Une décision se compte par
#: ligne tranchée — le refus d'une ligne s'écrit ``unjustified`` — ; un
#: refus, par ligne non justifiée ou par pièce rejetée ; une
#: rectification, par demande.
COMPTEURS_CIRCUIT = {
    "declarations": [([A.SUBMITTED], "Dossier")],
    "decisions": [([A.JUSTIFIED, A.UNJUSTIFIED], "Expense")],
    "reouvertures": [([A.REOPENED], "Dossier")],
    "rectifications": [([A.RECTIFICATION_REQUESTED], None)],
    "refus": [([A.UNJUSTIFIED], "Expense"), ([A.REJECTED], "Proof")],
    "pieces": [([A.PROOF_UPLOADED, A.PROOF_REPLACED], None)],
    "sorties": [([A.DOWNLOADED], None)],
    "imports": [([A.IMPORTED], None)],
    "suppressions": [([A.DELETED], None)],
    "renommages": [([A.RENAMED], None)],
}

#: Ce qui, dans le circuit, mérite qu'on y regarde à deux fois.
SENSIBLES_CIRCUIT = [
    A.REOPENED, A.RECTIFICATION_REQUESTED, A.RECTIFICATION_DECIDED, A.RECTIFIED,
    A.DELETED, A.UNJUSTIFIED, A.REJECTED, A.IMPORTED,
]
#: Et dans le référentiel, les comptes, la configuration.
SENSIBLES_REFERENTIEL = Q(
    action__in=[C.LOGIN_FAILED, C.TOTP_RESET, C.PASSWORD_RESET, C.DEACTIVATED, C.DELETED]
) | Q(model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION)


def _periode(debut, fin):
    aujourd_hui = timezone.localdate()
    fin = fin or aujourd_hui
    debut = debut or fin - timedelta(days=JOURS_PAR_DEFAUT - 1)
    return debut, fin


def synthese(circuit, referentiel, *, debut=None, fin=None):
    """La synthèse des deux journaux, déjà cloisonnés et filtrés par pays.

    ``circuit`` et ``referentiel`` sont les querysets visibles du demandeur
    (``AuditLog`` et ``ChangeLog``) ; ``debut`` et ``fin`` bornent la
    période (dates incluses).
    """
    debut, fin = _periode(debut, fin)
    circuit = circuit.filter(created_at__date__gte=debut, created_at__date__lte=fin)
    referentiel = referentiel.filter(created_at__date__gte=debut, created_at__date__lte=fin)

    comptes = {
        (action, objet): n
        for action, objet, n in circuit.order_by()
        .values_list("action", "object_type").annotate(n=Count("pk"))
    }
    compteurs = {
        cle: sum(
            n for (action, type_d_objet), n in comptes.items()
            if any(action in actions and objet in (None, type_d_objet) for actions, objet in regles)
        )
        for cle, regles in COMPTEURS_CIRCUIT.items()
    }
    compteurs["circuit"] = sum(comptes.values())
    compteurs["referentiel"] = referentiel.count()
    compteurs["changements_de_droits"] = referentiel.filter(
        model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION
    ).count()
    compteurs["echecs_de_connexion"] = referentiel.filter(action=C.LOGIN_FAILED).count()
    compteurs["reinitialisations_2fa"] = referentiel.filter(action=C.TOTP_RESET).count()
    compteurs["desactivations"] = referentiel.filter(action=C.DEACTIVATED).count()
    compteurs["projets"] = referentiel.filter(model_name=ChangeLog.Models.PROJECT).count()

    jours = {}
    for jour, n in (
        circuit.annotate(jour=TruncDate("created_at")).order_by()
        .values_list("jour").annotate(n=Count("pk"))
    ):
        jours.setdefault(jour, {"jour": jour, "circuit": 0, "referentiel": 0})["circuit"] = n
    for jour, n in (
        referentiel.annotate(jour=TruncDate("created_at")).order_by()
        .values_list("jour").annotate(n=Count("pk"))
    ):
        jours.setdefault(jour, {"jour": jour, "circuit": 0, "referentiel": 0})["referentiel"] = n

    utilisateurs = {}
    for user, n in circuit.exclude(user="").order_by().values_list("user").annotate(n=Count("pk")):
        utilisateurs[user] = utilisateurs.get(user, 0) + n
    for user, n in (
        referentiel.exclude(performed_by="").order_by()
        .values_list("performed_by").annotate(n=Count("pk"))
    ):
        utilisateurs[user] = utilisateurs.get(user, 0) + n

    pays = {}
    for country_id, nom, n in (
        circuit.exclude(country=None).order_by()
        .values_list("country", "country__name").annotate(n=Count("pk"))
    ):
        pays[country_id] = {"country": country_id, "name": nom, "count": n}

    sensibles = sorted(
        [
            *map(_entree_circuit, circuit.filter(action__in=SENSIBLES_CIRCUIT)
                 .order_by("-created_at", "-pk")[:A_SURVEILLER]),
            *map(_entree_referentiel, referentiel.filter(SENSIBLES_REFERENTIEL)
                 .order_by("-created_at", "-pk")[:A_SURVEILLER]),
        ],
        key=lambda e: (e["created_at"], e["id"]),
        reverse=True,
    )[:A_SURVEILLER]

    return {
        "debut": debut,
        "fin": fin,
        "compteurs": compteurs,
        "par_jour": [jours[jour] for jour in sorted(jours)],
        "par_utilisateur": [
            {"user": user, "count": n}
            for user, n in sorted(utilisateurs.items(), key=lambda kv: (-kv[1], kv[0]))[:PREMIERS]
        ],
        "par_pays": sorted(pays.values(), key=lambda p: (-p["count"], p["name"])),
        "a_surveiller": sensibles,
    }
