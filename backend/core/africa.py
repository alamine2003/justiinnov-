"""Périmètre géographique de la plateforme : les filiales de Generic Healthcare (GH).

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

# Devise officielle de chaque filiale (ISO 4217), proposée d'office à
# l'ouverture du pays (décision 121). Le franc CFA de l'UEMOA (XOF) et celui
# de la CEMAC (XAF) sont à parité : une filiale peut tenir ses comptes dans
# l'un ou l'autre, ou en dollar, en euro — d'où la liste autorisée
# ci-dessous plutôt qu'une devise imposée.
DEVISES_OFFICIELLES = {
    "BF": "XOF",
    "BJ": "XOF",
    "CD": "CDF",
    "CG": "XAF",
    "CI": "XOF",
    "CM": "XAF",
    "DJ": "DJF",
    "GA": "XAF",
    "GM": "GMD",
    "GN": "GNF",
    "MG": "MGA",
    "ML": "XOF",
    "MR": "MRU",
    "NE": "XOF",
    "SN": "XOF",
    "TD": "XAF",
    "TG": "XOF",
}

# Les devises qu'un pays peut porter : celles des filiales, plus le dollar et
# l'euro. Un code qui n'existe pas — « XFO » pour « XOF », vu en production
# le 12 octobre 2026 — sortait le pays de la consolidation sans rien dire :
# aucun taux ne le convertit, et la devise se fige dès la première dépense.
DEVISES_AUTORISEES = frozenset(DEVISES_OFFICIELLES.values()) | {"USD", "EUR"}


def validate_devise(devise):
    """Refuse une devise hors de la liste autorisée, en la nommant."""
    if (devise or "").strip().upper() not in DEVISES_AUTORISEES:
        raise ValidationError(
            _(
                "« %(devise)s » n'est pas une devise des filiales. Devises "
                "acceptées : %(liste)s."
            ),
            params={"devise": devise, "liste": ", ".join(sorted(DEVISES_AUTORISEES))},
            code="devise_inconnue",
        )


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
