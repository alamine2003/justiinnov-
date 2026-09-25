"""Coordonnées d'un bénéficiaire : ce qui compte pour un téléphone ou un e-mail.

Une seule définition, partagée par le sérialiseur (qui refuse une saisie
mal formée) et par la migration de reprise (qui range les anciens contacts
en texte libre là où ils vont) : les deux disent la même chose d'une même
valeur.
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

#: Chiffres, espaces, points, tirets, parenthèses, un « + » en tête : ce
#: qu'on écrit d'un numéro dans les dix-sept pays. Le nombre de chiffres
#: est vérifié à part.
_TELEPHONE = re.compile(r"^\+?[0-9 ().\-]+$")
CHIFFRES_MIN, CHIFFRES_MAX = 6, 15


def est_un_telephone(valeur):
    """``valeur`` s'écrit-elle comme un numéro de téléphone ?

    De six à quinze chiffres (le maximum de la norme E.164), en ignorant les
    séparateurs usuels.
    """
    valeur = (valeur or "").strip()
    if not _TELEPHONE.match(valeur):
        return False
    chiffres = sum(c.isdigit() for c in valeur)
    return CHIFFRES_MIN <= chiffres <= CHIFFRES_MAX


def est_un_email(valeur):
    """``valeur`` est-elle une adresse e-mail valide ?"""
    try:
        validate_email((valeur or "").strip())
    except ValidationError:
        return False
    return True


def normaliser_telephone(valeur):
    """Espaces réduits à un seul, bords retirés : le numéro tel qu'on le lit."""
    return " ".join((valeur or "").split())
