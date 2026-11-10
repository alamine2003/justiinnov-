"""Décaissement fait dans une autre devise que celle du pays (§5.3).

Une mission au Togo peut payer un hôtel en euros : la pièce porte 120 EUR.
Le montant d'origine est conservé pour que le siège retrouve le chiffre du
justificatif, et le montant de la ligne reçoit sa conversion dans la devise
du pays — c'est elle qui pèse sur l'enveloppe, et elle qui garde les
agrégats monodevise. Le taux est celui du jour de la dépense, figé à la
saisie : un rapport tiré l'an prochain doit donner le même chiffre
qu'aujourd'hui.

La règle vit ici, une fois, pour les deux portes de la déclaration : la
saisie (``ExpenseSerializer``) et l'import d'un classeur
(``reporting.imports``). Chacune garde ses messages, qui ne disent pas la
même chose — l'import nomme la date de la ligne, la saisie renvoie à la page
des taux —, et sa façon de refuser.
"""

from dataclasses import dataclass
from decimal import Decimal

from budget.aggregates import convert


@dataclass(frozen=True)
class Decaissement:
    """Ce que la ligne retient du décaissement.

    ``amount`` est le montant dans la devise du pays. Les trois champs
    d'origine restent vides quand le décaissement est dans cette devise :
    conserver un « montant d'origine » laisserait croire à un décaissement
    étranger.
    """

    amount: Decimal
    original_currency: str = ""
    original_amount: Decimal | None = None
    original_rate: Decimal | None = None


class TauxInconnu(Exception):
    """Aucun taux publié ne convertit ``devise`` en ``cible`` au ``jour`` dit."""

    def __init__(self, devise, cible, jour):
        super().__init__(devise, cible, jour)
        self.devise = devise
        self.cible = cible
        self.jour = jour


def decaissement_incomplet(devise, montant):
    """La règle « les deux ou aucun » : une devise sans montant, ou l'inverse."""
    return bool(devise) != (montant is not None)


def convertir_le_decaissement(devise, montant, devise_du_pays, jour):
    """Convertit ``montant`` décaissé en ``devise`` dans la devise du pays.

    ``devise`` et ``montant`` sont tous deux donnés (voir
    :func:`decaissement_incomplet`) ; ``jour`` est le jour de la dépense
    dans le fuseau du pays, ``None`` pour le taux du jour. Dans la devise du
    pays, la conversion serait l'identité : le montant est repris tel quel,
    sans origine. Sinon, la conversion au taux de ce jour-là, que la ligne
    fige. Lève :class:`TauxInconnu` faute de taux, jamais un montant nul qui
    ferait disparaître la dépense d'un total.
    """
    devise = devise.strip().upper()
    if devise == devise_du_pays:
        return Decaissement(amount=montant)
    converti, taux = convert(montant, devise, devise_du_pays, jour)
    if converti is None:
        raise TauxInconnu(devise, devise_du_pays, jour)
    return Decaissement(
        amount=converti,
        original_currency=devise,
        original_amount=montant,
        original_rate=taux,
    )
