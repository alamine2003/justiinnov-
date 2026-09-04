"""Validateurs de champs partagés par les modèles de ``core``."""

import zoneinfo

from django.core.exceptions import ValidationError


def validate_timezone(value):
    """Refuse un fuseau que la bibliothèque standard ne connaît pas.

    Le fuseau sert à afficher l'heure locale des dépenses ; une faute de
    frappe (« Africa/Abijan ») ne se remarquerait qu'au premier affichage,
    par une erreur au lieu d'une heure.
    """
    if value not in zoneinfo.available_timezones():
        raise ValidationError(
            "Fuseau horaire inconnu : %(value)s (identifiant IANA attendu, "
            "ex. Africa/Abidjan).",
            code="fuseau_inconnu",
            params={"value": value},
        )
