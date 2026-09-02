"""Périmètre géographique de la plateforme : l'Afrique.

Le contrôle budgétaire porte sur les filiales africaines du groupe. Rien dans
le modèle ne l'empêchait : la base contenait la France et la Belgique, restes
des jeux d'essai, qui apparaissaient dans les listes et faussaient les
consolidations — leur devise n'avait aucun taux publié.

La liste ci-dessous est celle des 54 États d'Afrique reconnus par l'ONU, plus
les territoires insulaires rattachés au continent, en codes ISO 3166-1
alpha-2. Elle sert de garde-fou à la création d'un pays : ajouter une filiale
hors d'Afrique demanderait de modifier ce fichier, donc une décision explicite,
pas une faute de frappe dans un formulaire.
"""

from django.core.exceptions import ValidationError

# Pays et territoires africains : code ISO 3166-1 alpha-2 → nom français.
AFRICAN_COUNTRIES = {
    "AO": "Angola",
    "BF": "Burkina Faso",
    "BI": "Burundi",
    "BJ": "Bénin",
    "BW": "Botswana",
    "CD": "République démocratique du Congo",
    "CF": "République centrafricaine",
    "CG": "Congo",
    "CI": "Côte d'Ivoire",
    "CM": "Cameroun",
    "CV": "Cabo Verde",
    "DJ": "Djibouti",
    "DZ": "Algérie",
    "EG": "Égypte",
    "EH": "Sahara occidental",
    "ER": "Érythrée",
    "ET": "Éthiopie",
    "GA": "Gabon",
    "GH": "Ghana",
    "GM": "Gambie",
    "GN": "Guinée",
    "GQ": "Guinée équatoriale",
    "GW": "Guinée-Bissau",
    "IO": "Territoire britannique de l'océan Indien",
    "KE": "Kenya",
    "KM": "Comores",
    "LR": "Liberia",
    "LS": "Lesotho",
    "LY": "Libye",
    "MA": "Maroc",
    "MG": "Madagascar",
    "ML": "Mali",
    "MR": "Mauritanie",
    "MU": "Maurice",
    "MW": "Malawi",
    "MZ": "Mozambique",
    "NA": "Namibie",
    "NE": "Niger",
    "NG": "Nigeria",
    "RE": "La Réunion",
    "RW": "Rwanda",
    "SC": "Seychelles",
    "SD": "Soudan",
    "SH": "Sainte-Hélène",
    "SL": "Sierra Leone",
    "SN": "Sénégal",
    "SO": "Somalie",
    "SS": "Soudan du Sud",
    "ST": "Sao Tomé-et-Principe",
    "SZ": "Eswatini",
    "TD": "Tchad",
    "TG": "Togo",
    "TN": "Tunisie",
    "TZ": "Tanzanie",
    "UG": "Ouganda",
    "YT": "Mayotte",
    "ZA": "Afrique du Sud",
    "ZM": "Zambie",
    "ZW": "Zimbabwe",
}

# Vue ensembliste, pour les tests d'appartenance.
AFRICAN_COUNTRY_CODES = frozenset(AFRICAN_COUNTRIES)


def validate_african_country(code):
    """Refuse un code ISO hors d'Afrique.

    Le message nomme le périmètre plutôt que le code fautif : l'utilisateur
    n'a pas à deviner qu'une liste existe quelque part.
    """
    if not code:
        return
    if code.strip().upper() not in AFRICAN_COUNTRY_CODES:
        raise ValidationError(
            "La plateforme ne suit que des pays africains ; "
            "« %(code)s » n'est pas un code ISO d'un pays d'Afrique.",
            params={"code": code},
            code="hors_afrique",
        )
