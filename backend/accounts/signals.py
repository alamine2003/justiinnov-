"""Historisation du périmètre, du rôle et de la langue des comptes.

``UserProfile.save()`` ne voit pas ses relations ``countries`` et ``teams``,
modifiées après coup par ``.set()`` : sans ces receveurs, élargir le
périmètre d'un compte — lui donner accès aux dépenses d'un autre pays, ou
d'une autre équipe — ne laissait aucune trace. Le rôle et la langue, eux,
sont journalisés à l'enregistrement du profil, quel que soit le chemin :
API, admin Django ou ``seed_users``. Un rôle changé depuis l'admin
réaligne au passage ``is_staff`` / ``is_superuser`` sur le compte, sans
quoi un super administrateur rétrogradé garderait le back-office.

Le mécanisme est celui de ``core.signals`` ; seul l'objet journalisé
change : le compte, pas le profil, pour que l'entrée se lise avec les autres
événements du compte.
"""

from django.db.models.signals import m2m_changed, pre_save
from django.dispatch import receiver

from core.models import ChangeLog
from core.signals import journaliser, journaliser_relation, memoriser_avant_clear

from .models import UserProfile, aligner_drapeaux

#: Champs du profil journalisés à l'enregistrement.
CHAMPS_DU_PROFIL = ("role", "language")


def _libelle(country):
    return f"{country.name} ({country.code})"


def _libelle_equipe(team):
    return f"{team.name} ({team.country.code})"


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


@receiver(m2m_changed, sender=UserProfile.teams.through)
def _track_profile_teams(sender, instance, action, pk_set, reverse, **kwargs):
    if reverse:
        # ``team.profiles.set(...)`` : on journalise compte par compte.
        for profile in UserProfile.objects.filter(pk__in=pk_set or []).select_related("user"):
            _track_profile_teams(
                sender, profile, action, {instance.pk}, False, **kwargs
            )
        return
    equipes = instance.teams.select_related("country")
    memoriser_avant_clear(instance, action, "teams", equipes, _libelle_equipe)
    journaliser_relation(
        instance.user, action, pk_set or set(), ChangeLog.Models.USER,
        champ="teams", accessor=equipes, libelle=_libelle_equipe,
        porteur=instance,
    )


@receiver(pre_save, sender=UserProfile)
def _track_profile_fields(sender, instance, **kwargs):
    """Rôle et langue : journalisés avant/après, drapeaux du compte réalignés.

    En ``pre_save``, l'état en base est encore l'ancien : c'est là que la
    différence se lit. La création n'est pas journalisée ici — c'est le
    chemin qui crée le compte qui la consigne, avec son auteur.
    """
    if instance.pk is None:
        return
    precedent = UserProfile.objects.filter(pk=instance.pk).only(*CHAMPS_DU_PROFIL).first()
    if precedent is None:
        return
    changements = {
        champ: [getattr(precedent, champ), getattr(instance, champ)]
        for champ in CHAMPS_DU_PROFIL
        if getattr(precedent, champ) != getattr(instance, champ)
    }
    if not changements:
        return
    user = instance.user
    if "role" in changements and aligner_drapeaux(user, instance.role):
        user.save(update_fields=["is_staff", "is_superuser"])
    journaliser(
        user,
        ChangeLog.Actions.UPDATED,
        ChangeLog.Models.USER,
        label=user.username,
        from_value=user.username,
        to_value=user.username,
        changed_fields=list(changements),
        diff=changements,
    )
