"""Exceptions des règles métier, et leur traduction HTTP (décision 41).

Les services de transition (``expenses.transitions``, ``budget.transitions``)
ne connaissent ni DRF ni la requête : quand une règle refuse, ils lèvent
l'une des classes ci-dessous. La vue les traduit en réponse — 400, 403,
404 — avec :func:`traduire_les_regles` ; une commande ou un import les
attrape tels quels. Les messages sont ceux que l'API renvoyait déjà : le
chemin change, pas le contrat.

Trois refus, trois codes :

- :class:`RegleViolee` — la demande est recevable mais la règle la refuse
  (état de départ, motif manquant, ligne en suspens, dépassement) ; elle
  nomme le champ que l'interface doit signaler → 400 ;
- :class:`PermissionRefusee` — le demandeur n'est pas la bonne personne
  (rôle, quatre yeux, auteur d'un brouillon) → 403 ;
- :class:`HorsPerimetre` — l'objet visé n'existe pas pour lui → 404, sans
  rien révéler.
"""

from contextlib import contextmanager

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError


class RegleViolee(Exception):
    """Une règle du circuit refuse l'opération sur un champ nommé."""

    def __init__(self, champ, message):
        super().__init__(message)
        self.champ = champ
        self.message = message

    def __str__(self):
        return str(self.message)


class PermissionRefusee(Exception):
    """Le demandeur n'est pas habilité à cette opération."""


class HorsPerimetre(Exception):
    """L'objet visé n'est pas dans le périmètre du demandeur."""


@contextmanager
def traduire_les_regles():
    """Traduit un refus métier en réponse HTTP, dans une vue.

    La forme est celle des erreurs de validation de DRF, que l'interface
    sait déjà lire : ``{champ: [message]}`` pour un 400, le message seul
    pour un 403, rien pour un 404 — un objet hors périmètre est un objet
    qui n'existe pas, quoi que le service en sache.
    """
    try:
        yield
    except RegleViolee as exc:
        raise ValidationError({exc.champ: [str(exc.message)]}) from exc
    except PermissionRefusee as exc:
        raise PermissionDenied(str(exc)) from exc
    except HorsPerimetre as exc:
        raise NotFound() from exc
