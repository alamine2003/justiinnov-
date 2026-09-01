"""Historisation automatique des changements et des rattachements de pays.

La détection des modifications s'effectue en ``pre_save``, au moment où
l'instance en mémoire diffère encore de l'état en base de données.
"""

import threading

from django.db.models.signals import post_save, pre_save
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


def _log(instance, action, model_name, from_value=""):
    """Crée une entrée d'historique pour une instance."""
    user = get_current_user()
    if callable(user):
        user = user()
    performed_by = user.username if user and user.is_authenticated else ""
    country = getattr(instance, "country", None)
    ChangeLog.objects.create(
        model_name=model_name,
        object_id=instance.pk,
        label=str(instance),
        action=action,
        country=country,
        from_value=from_value,
        to_value=str(instance),
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

    # 1. Rattachement de pays modifié (sous-ressources rattachées à un pays).
    if not is_country and hasattr(instance, "country_id"):
        if previous.country_id != instance.country_id:
            _log(
                instance,
                ChangeLog.Actions.REASSIGNED,
                model_name,
                from_value=f"{previous.country.name} ({previous.country.code})",
            )
            return

    # 2. Activation / désactivation d'un pays.
    if is_country and previous.is_active != instance.is_active:
        action = (
            ChangeLog.Actions.REACTIVATED
            if instance.is_active
            else ChangeLog.Actions.DEACTIVATED
        )
        _log(instance, action, model_name)
        return

    # 3. Mise à jour générique.
    if changes:
        _log(instance, ChangeLog.Actions.UPDATED, model_name)


def _log_creation(sender, instance, created, **kwargs):
    if created:
        _log(instance, ChangeLog.Actions.CREATED, _MODEL_NAME[sender.__name__])


# Le décorateur ``@receiver`` ne dissocie pas un *sender* qui est un tuple :
# on enregistre donc chaque handler individuellement pour chaque modèle.
for _model in ALL_MODELS:
    receiver(pre_save, sender=_model)(_track_creation_update)
    receiver(post_save, sender=_model)(_log_creation)

# Libère la variable de boucle de l'espace de noms du module.
del _model