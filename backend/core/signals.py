"""Historisation automatique des changements et des rattachements de pays.

La détection des modifications s'effectue en ``pre_save``, au moment où
l'instance en mémoire diffère encore de l'état en base de données. L'écriture
elle-même passe par la façade ``core.journal`` (décision 38).
"""

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
from .journal import serialisable, tracer  # noqa: F401 — ``serialisable`` ré-exporté
from .requetes import (  # noqa: F401 — ré-exportés pour les commandes et les tests
    get_current_request,
    get_current_user,
    reset_current_request,
    set_current_request,
)

ALL_MODELS = (Country, Manager, Team, CostCenter, Project, ExpenseTitle, MarketingCategory)

_MODEL_NAME = {
    "Country": ChangeLog.Models.COUNTRY,
    "Manager": ChangeLog.Models.MANAGER,
    "Team": ChangeLog.Models.TEAM,
    "CostCenter": ChangeLog.Models.COST_CENTER,
    "Project": ChangeLog.Models.PROJECT,
    "ExpenseTitle": ChangeLog.Models.EXPENSE_TITLE,
    "MarketingCategory": ChangeLog.Models.MARKETING_CATEGORY,
}


def journaliser(instance, action, model_name, *, label=None, country=None,
                from_value="", to_value=None, changed_fields=None, diff=None,
                performed_by=None, request=None):
    """Écrit une entrée d'historique signée par la requête courante.

    Couche d'adaptation de :func:`core.journal.tracer` pour les écritures
    qui nomment l'entité : les signaux ci-dessous, la configuration du
    workflow et les comptes passent par ici, et la façade remplit « qui,
    depuis quelle adresse » de la même façon partout.
    """
    if model_name == ChangeLog.Models.USER:
        famille = "session" if action in _ACTIONS_DE_SESSION else "compte"
    elif model_name == ChangeLog.Models.WORKFLOW_CONFIGURATION:
        famille = "configuration"
    else:
        famille = "referentiel"
    return tracer(
        request,
        action,
        instance,
        famille=famille,
        label=(label if label is not None else str(instance))[:250],
        country=country,
        entite=model_name,
        from_value=from_value,
        to_value=str(instance) if to_value is None else to_value,
        changed_fields=changed_fields,
        diff=diff,
        performed_by=performed_by,
    )


#: Actions d'un compte qui relèvent de la session, pas de sa gestion.
_ACTIONS_DE_SESSION = frozenset(
    {ChangeLog.Actions.LOGIN, ChangeLog.Actions.LOGIN_FAILED, ChangeLog.Actions.LOGOUT}
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
    # Un pays qui a laissé des traces ne se supprime pas : ``ChangeLog.country``
    # est en ``PROTECT`` et le journal est immuable en base. Il n'y a donc
    # rien à détacher ici — la suppression échoue avant d'arriver là.


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