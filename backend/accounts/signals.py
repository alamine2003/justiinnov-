"""Historisation du périmètre des comptes.

``UserProfile.save()`` ne voit pas sa relation ``countries``, modifiée après
coup par ``countries.set()`` : sans ce receveur, élargir le périmètre d'un
compte — lui donner accès aux dépenses d'un autre pays — ne laissait aucune
trace. Le mécanisme est celui de ``core.signals`` ; seul l'objet journalisé
change : le compte, pas le profil, pour que l'entrée se lise avec les autres
événements du compte.
"""

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from core.models import ChangeLog
from core.signals import journaliser_relation, memoriser_avant_clear

from .models import UserProfile


def _libelle(country):
    return f"{country.name} ({country.code})"


@receiver(m2m_changed, sender=UserProfile.countries.through)
def _track_profile_countries(sender, instance, action, pk_set, reverse, **kwargs):
    if reverse:
        # ``country.profiles.set(...)`` : on journalise compte par compte.
        for profile in UserProfile.objects.filter(pk__in=pk_set or []).select_related("user"):
            _track_profile_countries(
                sender, profile, action, {instance.pk}, False, **kwargs
            )
        return
    memoriser_avant_clear(instance, action, "countries", instance.countries, _libelle)
    journaliser_relation(
        instance.user, action, pk_set or set(), ChangeLog.Models.USER,
        champ="countries", accessor=instance.countries, libelle=_libelle,
        porteur=instance,
    )
