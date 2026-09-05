"""Façade unique d'écriture des journaux (décision 38).

Deux journaux, une seule porte. ``ChangeLog`` garde l'histoire de ce qui
*structure* la plateforme — référentiel, comptes, configuration, sessions —
avec l'ancienne et la nouvelle valeur ; ``AuditLog`` garde celle de ce qui
*engage* — circuit de justification, pièces, fichiers, imports et exports.
Chaque écriture, quel que soit le journal, dit qui, quoi, quand, depuis
quelle adresse et quel appareil : c'est ici, et nulle part ailleurs, que ces
champs se remplissent, pour qu'ils se remplissent de la même façon partout.
Un test structurel (``core.tests.test_journal_unique``) refuse toute autre
création directe d'une entrée.

L'appelant nomme une **famille** ; la famille choisit le journal :

- ``referentiel``, ``compte``, ``configuration``, ``session`` → ``ChangeLog``
  (``avant``/``apres`` sont deux photographies dont la différence devient
  ``diff`` et ``changed_fields``) ;
- ``circuit``, ``piece``, ``fichier``, ``import``, ``export`` → ``AuditLog``
  (``avant``/``apres`` partent dans ``detail`` sous ``before``/``after``,
  les clés que l'interface lit déjà).

``expenses`` n'est pas importé en tête de module : ``core`` est au bas de
l'ordre des dépendances (décision 40) et ne connaît le modèle d'audit que
par son nom, résolu à l'écriture.
"""

import datetime
import decimal
from dataclasses import dataclass

from django.apps import apps

from .models import ChangeLog
from .requetes import client_ip, get_current_request

FAMILLES_HISTORIQUE = frozenset({"referentiel", "compte", "configuration", "session"})
FAMILLES_AUDIT = frozenset({"circuit", "piece", "fichier", "import", "export"})

#: Entité de ``ChangeLog`` qu'une famille implique d'elle-même. Le
#: référentiel, lui, la reçoit de l'appelant (``entite=``) : un pays, une
#: équipe ou une enveloppe n'y ont pas la même.
_ENTITE_PAR_FAMILLE = {
    "compte": ChangeLog.Models.USER,
    "session": ChangeLog.Models.USER,
    "configuration": ChangeLog.Models.WORKFLOW_CONFIGURATION,
}


def serialisable(value):
    """Valeur d'un champ sous une forme acceptée par ``JSONField``.

    Les nombres décimaux et les dates n'ont pas d'équivalent JSON : ils
    partent en texte, sans arrondi ni fuseau implicite.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [serialisable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): serialisable(v) for k, v in value.items()}
    return str(value)


def difference(avant, apres):
    """``{champ: [ancienne valeur, nouvelle valeur]}`` entre deux photographies.

    Les clés sont parcourues dans l'ordre d'``apres`` puis d'``avant`` : un
    champ qui disparaît compte autant qu'un champ qui change.
    """
    champs = list(apres) + [c for c in avant if c not in apres]
    return {
        champ: [serialisable(avant.get(champ)), serialisable(apres.get(champ))]
        for champ in champs
        if avant.get(champ) != apres.get(champ)
    }


@dataclass(frozen=True)
class Trace:
    """Qui signe une écriture, depuis où, avec quel appareil.

    Construite par la vue depuis la requête (:meth:`depuis_requete`) et
    passée aux services de transition (décision 41), qui journalisent sans
    connaître HTTP. ``compte`` est l'instance utilisateur, quand il y en a
    une : les notifications s'en servent pour ne pas prévenir l'auteur de
    l'action ; hors requête (commande, tâche) elle peut manquer, l'entrée
    reste alors anonyme — comme aujourd'hui.
    """

    user: str = ""
    ip: str | None = None
    user_agent: str = ""
    compte: object = None

    @classmethod
    def depuis_requete(cls, request):
        """La trace d'une requête ; celle en cours si ``request`` est ``None``."""
        if request is None:
            request = get_current_request()
        if request is None:
            return cls()
        user = getattr(request, "user", None)
        connecte = user is not None and user.is_authenticated
        return cls(
            user=user.username if connecte else "",
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
            compte=user if connecte else None,
        )

    @classmethod
    def depuis_compte(cls, user, ip=None):
        """La trace d'une commande qui agit au nom d'un compte, sans requête."""
        return cls(user=user.username, ip=ip, compte=user)


def _trace(source):
    """Une :class:`Trace`, qu'on nous ait donné une requête ou une trace."""
    if isinstance(source, Trace):
        return source
    return Trace.depuis_requete(source)


def _pays(instance, country):
    """Pays de l'entrée : celui donné, sinon celui que porte l'instance."""
    if country is not None:
        return country
    return getattr(instance, "country", None)


def _entree_historique(trace, action, instance, famille, avant, apres, label,
                       country, detail):
    """Entrée ``ChangeLog``, non enregistrée.

    ``detail`` admet ce que l'appelant a déjà calculé — ``entite``,
    ``from_value``, ``to_value``, ``changed_fields``, ``diff``,
    ``performed_by`` — ; le reste est déduit.
    """
    entite = detail.pop("entite", None) or _ENTITE_PAR_FAMILLE.get(famille)
    if entite is None:
        raise ValueError("Une entrée du référentiel nomme son entité (entite=).")
    diff = detail.pop("diff", None)
    changed_fields = detail.pop("changed_fields", None)
    if diff is None and avant is not None and apres is not None:
        diff = difference(avant, apres)
        changed_fields = changed_fields or list(diff)
    performed_by = detail.pop("performed_by", None)
    if performed_by is None:
        performed_by = trace.user
    to_value = detail.pop("to_value", None)
    if to_value is None:
        to_value = str(instance) if instance is not None else ""
    from_value = detail.pop("from_value", "")
    if detail:
        raise TypeError(
            "Paramètres inconnus pour une entrée d'historique : "
            + ", ".join(sorted(detail))
        )
    if label == "" and instance is not None:
        label = str(instance)
    return ChangeLog(
        model_name=entite,
        object_id=getattr(instance, "pk", None),
        label=label[:250],
        action=action,
        # Tel que donné : les signaux du référentiel le résolvent eux-mêmes,
        # et savent qu'un pays en cours de suppression ne se référence pas.
        country=country,
        from_value=from_value,
        to_value=to_value,
        changed_fields=changed_fields or [],
        diff=diff or {},
        performed_by=performed_by,
        ip_address=trace.ip,
    )


def _entree_audit(trace, action, instance, avant, apres, label, country, detail):
    """Entrée ``AuditLog``, non enregistrée.

    ``instance`` est l'objet visé, ou le *nom* du type quand l'action ne
    porte sur aucun objet précis (un export, un import) : l'entrée dit alors
    « Export », sans identifiant.
    """
    AuditLog = apps.get_model("expenses", "AuditLog")
    if avant is not None:
        detail["before"] = avant
    if apres is not None:
        detail["after"] = apres
    if isinstance(instance, str):
        object_type, object_id, pays = instance, None, country
        libelle = label
    else:
        object_type, object_id = instance.__class__.__name__, instance.pk
        pays = _pays(instance, country)
        libelle = label or str(instance)
    champs = {"country": pays}
    if isinstance(pays, int):
        # Un identifiant plutôt qu'une instance : l'export ne charge pas le
        # pays pour le seul plaisir de le journaliser.
        champs = {"country_id": pays}
    return AuditLog(
        user=trace.user,
        action=action,
        object_type=object_type,
        object_id=object_id,
        label=libelle[:250],
        detail=detail,
        ip_address=trace.ip,
        user_agent=trace.user_agent,
        **champs,
    )


def preparer(request, action, instance, *, famille, avant=None, apres=None,
             label="", country=None, **detail):
    """Construit une entrée sans l'enregistrer.

    Sert aux actions qui touchent beaucoup d'objets d'un coup (soumission
    d'un dossier de vingt lignes) : les entrées sont écrites ensemble par
    :func:`enregistrer`, en une requête, plutôt qu'une par ligne.

    ``request`` est la requête HTTP, ou déjà une :class:`Trace` (services de
    transition). Sans l'une ni l'autre, la requête courante
    (``core.requetes``) signe l'entrée ; hors requête — commande, tâche —
    l'auteur reste vide et l'adresse nulle.
    """
    trace = _trace(request)
    # Une clé de détail qui porte le nom d'un paramètre (``country``,
    # ``label``) se passe dans ``detail={...}`` ; elle rejoint les autres.
    complement = detail.pop("detail", None)
    if complement:
        detail.update(complement)
    if famille in FAMILLES_HISTORIQUE:
        return _entree_historique(
            trace, action, instance, famille, avant, apres, label, country, detail
        )
    if famille in FAMILLES_AUDIT:
        return _entree_audit(trace, action, instance, avant, apres, label, country, detail)
    raise ValueError(f"Famille de journal inconnue : {famille!r}")


def tracer(request, action, instance, *, famille, avant=None, apres=None,
           label="", country=None, **detail):
    """Journalise une action : construit l'entrée et l'enregistre.

    Point d'entrée unique de l'écriture des journaux ; voir le module.
    """
    entree = preparer(
        request, action, instance, famille=famille, avant=avant, apres=apres,
        label=label, country=country, **detail,
    )
    entree.save()
    return entree


def enregistrer(entrees):
    """Écrit d'un coup des entrées préparées, une requête par journal."""
    par_journal = {}
    for entree in entrees:
        par_journal.setdefault(type(entree), []).append(entree)
    ecrites = []
    for journal, lot in par_journal.items():
        ecrites.extend(journal.objects.bulk_create(lot))
    return ecrites
