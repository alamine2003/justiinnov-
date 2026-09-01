"""Historisation automatique des changements et des rattachements de pays.

La détection des modifications s'effectue en ``pre_save``, au moment où
l'instance en mémoire diffère encore de l'état en base de données.
"""

import threading

from django.db.models.signals import post_delete, post_save, pre_save
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

ALL_MODELS = (Country, Manager, Team, CostCenter, Project, ExpenseTitle, MarketingCategory)

# État du serveur : enregistre l'utilisateur courant (rempli par CurrentUserMiddleware)
_thread_local = threading.local()

_MODEL_NAME = {
    "Country": ChangeLog.Models.COUNTRY,
    "Manager": ChangeLog.Models.MANAGER,
    "Team": ChangeLog.Models.TEAM,
    "CostCenter": ChangeLog.Models.COST_CENTER,
    "Project": ChangeLog.Models.PROJECT,
    "ExpenseTitle": ChangeLog.Models.EXPENSE_TITLE,
    "MarketingCategory": ChangeLog.Models.MARKETING_CATEGORY,
}


def get_current_user():
    return getattr(_thread_local, "user", None)


def set_current_user(user):
    _thread_local.user = user


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


def _log(instance, action, model_name, from_value="", changed_fields=None):
    """Crée une entrée d'historique pour une instance."""
    user = get_current_user()
    if callable(user):
        user = user()
    performed_by = user.username if user and user.is_authenticated else ""
    deleted = action == ChangeLog.Actions.DELETED
    ChangeLog.objects.create(
        model_name=model_name,
        object_id=instance.pk,
        label=str(instance),
        action=action,
        country=_resolve_country(instance, verify_exists=deleted),
        from_value=from_value,
        to_value="" if deleted else str(instance),
        changed_fields=changed_fields or [],
        performed_by=performed_by,
    )


def _previous(instance):
    """Retourne l'état en base d'une instance existante, ou None."""
    if instance.pk is None:
        return None
    return instance.__class__.objects.filter(pk=instance.pk).first()


def _plain_changes(instance, previous):
    """Champs simples modifiés (exclut updated_at et les relations M2M)."""
    changes = []
    for field in instance._meta.concrete_fields:
        if field.attname == "updated_at":
            continue
        if getattr(previous, field.attname) != getattr(instance, field.attname):
            changes.append(field.name)
    return changes


def _track_creation_update(sender, instance, **kwargs):
    """Journalise toute modification d'une entité existante.

    Couvre la mise à jour générique (``updated``), l'activation /
    désactivation (``deactivated`` / ``reactivated``) et le changement de
    rattachement de pays (``reassigned``).
    """
    previous = _previous(instance)
    model_name = _MODEL_NAME.get(sender.__name__, ChangeLog.Models.COUNTRY)
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
        )
        changes.remove("country")

    # 2. Activation / désactivation d'un pays.
    if is_country and "is_active" in changes:
        action = (
            ChangeLog.Actions.REACTIVATED
            if instance.is_active
            else ChangeLog.Actions.DEACTIVATED
        )
        _log(instance, action, model_name, changed_fields=["is_active"])
        changes.remove("is_active")

    # 3. Mise à jour générique des champs restants.
    if changes:
        _log(
            instance,
            ChangeLog.Actions.UPDATED,
            model_name,
            from_value=str(previous),
            changed_fields=changes,
        )


def _log_creation(sender, instance, created, **kwargs):
    if created:
        _log(instance, ChangeLog.Actions.CREATED, _MODEL_NAME[sender.__name__])


def _log_deletion(sender, instance, **kwargs):
    """Journalise les suppressions restantes (admin Django, shell, cascade).

    L'API n'expose plus ``DELETE`` (cf. :class:`core.mixins.NoDestroyModelViewSet`),
    mais une suppression par un autre canal ne doit jamais passer sous silence.
    """
    _log(
        instance,
        ChangeLog.Actions.DELETED,
        _MODEL_NAME[sender.__name__],
        from_value=str(instance),
    )
    if isinstance(instance, Country):
        # Les entités filles sont supprimées *avant* leur pays : leurs entrées
        # d'historique, créées quelques instants plus tôt, y font encore
        # référence. Le pays n'existant plus, ces liens doivent être coupés
        # avant la fin de la transaction (contrainte de clé étrangère).
        ChangeLog.objects.filter(country_id=instance.pk).update(country=None)


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