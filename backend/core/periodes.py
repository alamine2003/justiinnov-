"""Une période en jours, sur une colonne horodatée, sans perdre son index.

Décision 123. ``created_at__date__gte=jour`` est juste, mais Postgres ne
peut pas s'en servir avec un index : Django écrit
``(created_at AT TIME ZONE '…')::date >= jour``, une expression que la base
doit calculer ligne par ligne. Sur 600 000 entrées du journal, un filtre de
trente jours parcourait toute la table (33 ms) ; écrit en bornes, il lit
l'index ``audit_date`` (0,8 ms) et donne exactement les mêmes lignes.

Les bornes sont prises dans le fuseau courant, celui que ``__date``
appliquerait : « du 3 au 5 » veut dire du 3 à 0 h au 6 à 0 h, heure locale.
"""

from datetime import date, datetime, time, timedelta

import django_filters
from django_filters.constants import EMPTY_VALUES
from django.db.models import Q
from django.utils import timezone


def debut_du_jour(jour):
    """Le premier instant de ``jour``, dans le fuseau courant."""
    return timezone.make_aware(datetime.combine(jour, time.min))


def lendemain(jour):
    """Le premier instant du lendemain de ``jour`` — borne exclue — ou
    ``None`` pour le dernier jour du calendrier, qui n'en a pas."""
    if jour >= date.max:
        return None
    return debut_du_jour(jour + timedelta(days=1))


def entre_les_jours(champ, debut=None, fin=None):
    """``Q`` des lignes dont ``champ`` tombe du jour ``debut`` au jour
    ``fin``, inclus, comme ``champ__date__gte`` et ``champ__date__lte``."""
    condition = Q()
    if debut is not None:
        condition &= Q(**{f"{champ}__gte": debut_du_jour(debut)})
    if fin is not None and (borne := lendemain(fin)) is not None:
        condition &= Q(**{f"{champ}__lt": borne})
    return condition


class DepuisLeJour(django_filters.DateFilter):
    """Filtre d'API : à partir du jour donné, inclus (``?debut=``)."""

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        return self.get_method(qs)(entre_les_jours(self.field_name, debut=value))


class JusquAuJour(django_filters.DateFilter):
    """Filtre d'API : jusqu'au jour donné, inclus (``?fin=``)."""

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        return self.get_method(qs)(entre_les_jours(self.field_name, fin=value))
