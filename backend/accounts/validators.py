"""Règles de validation partagées par l'API et les commandes d'administration."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


def normaliser_email(value):
    """Adresse en minuscules, sans espaces parasites.

    Les serveurs de messagerie ne distinguent pas la casse en pratique, mais
    une base l'a fait pour nous : deux comptes « Prenom@… » et « prenom@… »
    passaient l'unicité. Une seule forme, la plus simple.
    """
    return (value or "").strip().lower()


def valider_email_professionnel(value):
    """Refuse toute adresse hors des domaines de l'entreprise.

    La plateforme signe des justifications au nom de personnes : un compte
    rattaché à une adresse personnelle ne prouverait pas qui est derrière.
    Les domaines admis viennent de ``ALLOWED_EMAIL_DOMAINS`` ; la valeur
    rendue est normalisée (minuscules).
    """
    email = normaliser_email(value)
    if not email:
        raise ValidationError(_("Une adresse e-mail professionnelle est requise."))
    domaines = list(settings.ALLOWED_EMAIL_DOMAINS)
    _local, sep, domaine = email.rpartition("@")
    if not sep or domaine not in domaines:
        raise ValidationError(
            _(
                "L'adresse e-mail doit appartenir à un domaine de l'entreprise "
                "(%(domaines)s)."
            ),
            params={"domaines": ", ".join(domaines)},
            code="domaine_refuse",
        )
    return email
