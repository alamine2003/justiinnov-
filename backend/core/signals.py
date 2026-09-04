"""Historisation automatique des changements et des rattachements de pays.

La détection des modifications s'effectue en ``pre_save``, au moment où
l'instance en mémoire diffère encore de l'état en base de données.
"""

import datetime
import decimal
from contextvars import ContextVar
from functools import partial

from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import (
    ChangeLog,
    CostCenter,
    Country,
    ExpenseTitle,
    Manager,
    MarketingCategory,
    Project,
    Team,
)
from .requetes import client_ip

ALL_MODELS = (Country, Manager, Team, CostCenter, Project, ExpenseTitle, MarketingCategory)

#: Requête HTTP en cours de traitement, posée par ``CurrentRequestMiddleware``.
#:
#: Une variable de contexte plutôt qu'un ``threading.local`` : elle suit la
#: tâche, pas le fil d'exécution. Avec des workers gunicorn en threads, ou
#: du code asynchrone, un ``threading.local`` mal remis à zéro ferait signer
#: les écritures d'une requête par l'utilisateur d'une autre.
_requete_courante = ContextVar("requete_courante", default=None)

_MODEL_NAME = {
    "Country": ChangeLog.Models.COUNTRY,
    "Manager": ChangeLog.Models.MANAGER,
    "Team": ChangeLog.Models.TEAM,
    "CostCenter": ChangeLog.Models.COST_CENTER,
    "Project": ChangeLog.Models.PROJECT,
    "ExpenseTitle": ChangeLog.Models.EXPENSE_TITLE,
    "MarketingCategory": ChangeLog.Models.MARKETING_CATEGORY,
}


def get_current_request():
    """Requête en cours, ou ``None`` hors requête (commande, tâche, test)."""
    return _requete_courante.get()


def set_current_request(request):
    """Pose la requête courante et rend le jeton qui permet de la retirer."""
    return _requete_courante.set(request)


def reset_current_request(token):
    _requete_courante.reset(token)


def get_current_user():
    """Utilisateur authentifié de la requête courante, ou ``None``.

    Lu au moment de l'écriture et non à l'entrée du middleware : pour une
    requête par jeton, ``request.user`` n'est forcé par DRF qu'à l'entrée de
    la vue, bien après le middleware.
    """
    request = get_current_request()
    if request is None:
        return None
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return user


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


def journaliser(instance, action, model_name, *, label=None, country=None,
                from_value="", to_value=None, changed_fields=None, diff=None,
                performed_by=None, request=None):
    """Écrit une entrée d'historique signée par la requête courante.

    Point d'entrée unique : les signaux ci-dessous, la configuration du
    workflow et les comptes passent tous par ici, pour que « qui, depuis
    quelle adresse » soit rempli de la même façon partout.
    """
    request = request or get_current_request()
    if performed_by is None:
        user = get_current_user() if request is None else getattr(request, "user", None)
        performed_by = (
            user.username if user is not None and user.is_authenticated else ""
        )
    return ChangeLog.objects.create(
        model_name=model_name,
        object_id=getattr(instance, "pk", None),
        label=(label if label is not None else str(instance))[:250],
        action=action,
        country=country,
        from_value=from_value,
        to_value=str(instance) if to_value is None else to_value,
        changed_fields=changed_fields or [],
        diff=diff or {},
        performed_by=performed_by,
        ip_address=client_ip(request) if request is not None else None,
    )


def _resolve_country(instance, *, verify_exists=False):
    """Pays auquel rattacher l'entrée d'historique.

    Un ``Country`` est rattaché à lui-même : sans cela, ses propres créations,
    mises à jour et (dés)activations ne remonteraient jamais dans
    ``/api/history/?country={id}``.

    ``verify_exists`` sert aux suppressions : le pays peut être en cours de
    suppression en cascade, et l'historique ne doit alors pas y faire référence
    sous peine de violer la contrainte de clé étrangère.
    """
    if isinstance(instance, Country):
        if verify_exists and not Country.objects.filter(pk=instance.pk).exists():
            return None
        return instance
    country_id = getattr(instance, "country_id", None)
    if country_id is None:
        return None
    # ``.first()`` vérifie au passage que le pays n'est pas déjà supprimé.
    return Country.objects.filter(pk=country_id).first()


def _log(instance, action, model_name, from_value="", changed_fields=None,
         country_resolver=None, diff=None):
    """Crée une entrée d'historique pour une instance."""
    deleted = action == ChangeLog.Actions.DELETED
    if country_resolver is not None:
        country = country_resolver(instance)
    else:
        country = _resolve_country(instance, verify_exists=deleted)
    journaliser(
        instance,
        action,
        model_name,
        country=country,
        from_value=from_value,
        to_value="" if deleted else str(instance),
        changed_fields=changed_fields,
        diff=diff,
    )


def _previous(instance):
    """Retourne l'état en base d'une instance existante, ou None."""
    if instance.pk is None:
        return None
    return instance.__class__.objects.filter(pk=instance.pk).first()


def _plain_changes(instance, previous):
    """Champs simples modifiés (exclut updated_at et les relations M2M).

    Retourne ``{champ: [ancienne valeur, nouvelle valeur]}`` ; pour une clé
    étrangère, la valeur est l'identifiant visé.
    """
    changes = {}
    for field in instance._meta.concrete_fields:
        if field.attname == "updated_at":
            continue
        before = getattr(previous, field.attname)
        after = getattr(instance, field.attname)
        if before != after:
            changes[field.name] = [serialisable(before), serialisable(after)]
    return changes


def _track_creation_update(sender, instance, model_name=None,
                           country_resolver=None, **kwargs):
    """Journalise toute modification d'une entité existante.

    Couvre la mise à jour générique (``updated``), l'activation /
    désactivation (``deactivated`` / ``reactivated``) et le changement de
    rattachement de pays (``reassigned``).
    """
    previous = _previous(instance)
    model_name = model_name or _MODEL_NAME.get(
        sender.__name__, ChangeLog.Models.COUNTRY
    )
    is_country = sender is Country

    if previous is None:
        # La création est journalisée en post_save (une fois l'id connu).
        return

    changes = _plain_changes(instance, previous)

    # Les événements qualifiés (rattachement, activation) sont journalisés à
    # part, puis retirés de la liste : les champs restants produisent une
    # entrée « mise à jour » distincte, afin qu'une modification simultanée du
    # pays *et* d'autres champs ne perde aucune trace.

    # 1. Rattachement de pays modifié (sous-ressources rattachées à un pays).
    if not is_country and "country" in changes:
        _log(
            instance,
            ChangeLog.Actions.REASSIGNED,
            model_name,
            from_value=f"{previous.country.name} ({previous.country.code})",
            changed_fields=["country"],
            diff={"country": changes.pop("country")},
            country_resolver=country_resolver,
        )

    # 2. Activation / désactivation d'un pays.
    if is_country and "is_active" in changes:
        action = (
            ChangeLog.Actions.REACTIVATED
            if instance.is_active
            else ChangeLog.Actions.DEACTIVATED
        )
        _log(
            instance, action, model_name,
            changed_fields=["is_active"],
            diff={"is_active": changes.pop("is_active")},
            country_resolver=country_resolver,
        )

    # 3. Mise à jour générique des champs restants.
    if changes:
        _log(
            instance,
            ChangeLog.Actions.UPDATED,
            model_name,
            from_value=str(previous),
            changed_fields=list(changes),
            diff=changes,
            country_resolver=country_resolver,
        )


def _log_creation(sender, instance, created, model_name=None,
                  country_resolver=None, **kwargs):
    if created:
        _log(
            instance,
            ChangeLog.Actions.CREATED,
            model_name or _MODEL_NAME[sender.__name__],
            country_resolver=country_resolver,
        )


def _log_deletion(sender, instance, model_name=None, country_resolver=None,
                  **kwargs):
    """Journalise les suppressions restantes (admin Django, shell, cascade).

    L'API n'expose plus ``DELETE`` (cf. :class:`core.mixins.NoDestroyModelViewSet`),
    mais une suppression par un autre canal ne doit jamais passer sous silence.
    """
    _log(
        instance,
        ChangeLog.Actions.DELETED,
        model_name or _MODEL_NAME[sender.__name__],
        from_value=str(instance),
        country_resolver=country_resolver,
    )
    if isinstance(instance, Country):
        # Les entités filles sont supprimées *avant* leur pays : leurs entrées
        # d'historique, créées quelques instants plus tôt, y font encore
        # référence. Le pays n'existant plus, ces liens doivent être coupés
        # avant la fin de la transaction (contrainte de clé étrangère).
        ChangeLog.objects.filter(country_id=instance.pk).update(country=None)


def register(model, model_name, country_resolver=None):
    """Branche la journalisation sur un modèle d'une autre application.

    Permet à ``budget`` — ou à toute app en dépendant — de réutiliser cette
    machinerie sans que ``core`` ait à connaître ses modèles : la dépendance
    reste dirigée dans le bon sens.

    ``country_resolver`` sert aux modèles qui n'ont pas de champ ``country``
    propre, comme une réallocation, rattachée au pays de son enveloppe source.
    """
    options = {"model_name": model_name, "country_resolver": country_resolver}
    # ``weak=False`` est indispensable : Django ne garde qu'une référence
    # faible sur ses receivers. Un ``partial`` construit ici n'est référencé
    # nulle part ailleurs — le ramasse-miettes l'emportait, et le signal
    # cessait silencieusement d'être écouté. Une enveloppe pouvait alors être
    # réduite sans laisser de trace, selon le moment où le GC était passé.
    for signal, handler in (
        (pre_save, _track_creation_update),
        (post_save, _log_creation),
        (post_delete, _log_deletion),
    ):
        receiver(signal, sender=model, weak=False)(partial(handler, **options))


def journaliser_relation(instance, action, pk_set, model_name, *, champ,
                         accessor, libelle=str, country=None, porteur=None):
    """Journalise un ajout/retrait dans une relation multiple.

    Le signal ``m2m_changed`` arrive en ``post_*`` : la relation contient
    déjà le nouvel état. L'ancien est reconstitué à partir de ``pk_set``, les
    identifiants ajoutés ou retirés par l'appel. ``porteur`` est l'objet sur
    lequel ``memoriser_avant_clear`` a gardé l'état (par défaut ``instance``).
    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    apres = {obj.pk: libelle(obj) for obj in accessor.all()}
    if action == "post_add":
        avant = {pk: nom for pk, nom in apres.items() if pk not in pk_set}
    elif action == "post_remove":
        avant = dict(apres)
        retires = accessor.model.objects.filter(pk__in=pk_set)
        avant.update({obj.pk: libelle(obj) for obj in retires})
    else:
        # ``post_clear`` ne transmet pas les identifiants retirés : le signal
        # ``pre_clear`` les a mis de côté sur l'instance.
        porteur = instance if porteur is None else porteur
        avant = getattr(porteur, "_relation_avant_clear", {}).get(champ, {})
    if avant == apres:
        return
    avant, apres = sorted(avant.values()), sorted(apres.values())
    journaliser(
        instance,
        ChangeLog.Actions.UPDATED,
        model_name,
        country=country,
        from_value=", ".join(avant),
        changed_fields=[champ],
        diff={champ: [avant, apres]},
    )


def memoriser_avant_clear(instance, action, champ, accessor, libelle=str):
    """En ``pre_clear``, garde l'état d'une relation avant son vidage."""
    if action == "pre_clear":
        memo = getattr(instance, "_relation_avant_clear", None)
        if memo is None:
            memo = instance._relation_avant_clear = {}
        memo[champ] = {obj.pk: libelle(obj) for obj in accessor.all()}


@receiver(m2m_changed, sender=Country.managers.through)
def _track_country_managers(sender, instance, action, pk_set, reverse, **kwargs):
    """Les managers d'un pays sont un rattachement : il se journalise.

    ``Country.save()`` ne voit pas une relation multiple, modifiée après
    coup par ``managers.set()`` : sans ce receveur, changer le responsable
    d'un pays ne laissait aucune trace.
    """
    if reverse:
        # ``manager.countries.set(...)`` : on journalise côté pays, pour que
        # l'entrée apparaisse dans l'historique du pays concerné.
        for country in Country.objects.filter(pk__in=pk_set or []):
            _track_country_managers(
                sender, country, action, {instance.pk}, False, **kwargs
            )
        return
    memoriser_avant_clear(instance, action, "managers", instance.managers)
    journaliser_relation(
        instance, action, pk_set or set(), ChangeLog.Models.COUNTRY,
        champ="managers", accessor=instance.managers, country=instance,
    )


# Le décorateur ``@receiver`` ne dissocie pas un *sender* qui est un tuple :
# on enregistre donc chaque handler individuellement pour chaque modèle.
# Enregistrer un receiver ``post_delete`` désactive au passage le « fast
# delete » de Django, ce qui garantit qu'une suppression en cascade est bien
# journalisée ligne par ligne.
for _model in ALL_MODELS:
    receiver(pre_save, sender=_model)(_track_creation_update)
    receiver(post_save, sender=_model)(_log_creation)
    receiver(post_delete, sender=_model)(_log_deletion)

# Libère la variable de boucle de l'espace de noms du module.
del _model