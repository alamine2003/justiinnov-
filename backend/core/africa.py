"""Périmètre géographique de la plateforme : les filiales d'INNOV PHARMA.

Le contrôle budgétaire porte sur dix-sept pays d'Afrique, ni plus ni moins :
ce sont les filiales du groupe. Rien dans le modèle ne l'empêchait : la base
a déjà contenu la France et la Belgique, restes de jeux d'essai, qui
apparaissaient dans les listes et faussaient les consolidations.

La liste ci-dessous est celle des filiales, en codes ISO 3166-1 alpha-2. Elle
sert de garde-fou à la création d'un pays : ouvrir une nouvelle filiale
demande de modifier ce fichier, donc une décision explicite, pas une faute de
frappe dans un formulaire. Au démarrage, seuls la Côte d'Ivoire et le Togo
sont créés ; les autres le seront à leur entrée dans le dispositif.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Filiales : code ISO 3166-1 alpha-2 → nom français.
AFRICAN_COUNTRIES = {
    "BF": "Burkina Faso",
    "BJ": "Bénin",
    "CD": "République démocratique du Congo",
    "CG": "Congo",
    "CI": "Côte d'Ivoire",
    "CM": "Cameroun",
    "DJ": "Djibouti",
    "GA": "Gabon",
    "GM": "Gambie",
    "GN": "Guinée",
    "MG": "Madagascar",
    "ML": "Mali",
    "MR": "Mauritanie",
    "NE": "Niger",
    "SN": "Sénégal",
    "TD": "Tchad",
    "TG": "Togo",
}

# Vue ensembliste, pour les tests d'appartenance.
AFRICAN_COUNTRY_CODES = frozenset(AFRICAN_COUNTRIES)


def validate_african_country(code):
    """Refuse un code ISO hors des filiales.

    Le message nomme le périmètre plutôt que le code fautif : l'utilisateur
    n'a pas à deviner qu'une liste existe quelque part.
    """
    if not code:
        return
    if code.strip().upper() not in AFRICAN_COUNTRY_CODES:
        raise ValidationError(
            _(
                "La plateforme ne suit que les filiales africaines du groupe ; "
                "« %(code)s » n'en fait pas partie."
            ),
            params={"code": code},
            code="hors_perimetre",
        )
