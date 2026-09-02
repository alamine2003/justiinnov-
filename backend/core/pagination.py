"""Pagination commune à l'API."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Pagination dont la taille de page est réglable, mais bornée.

    Sans ``page_size_query_param``, DRF **ignore silencieusement** la taille
    demandée : l'interface calculerait ses pages sur un nombre de lignes que le
    serveur n'applique pas, et afficherait « page 1 sur 3 » là où il y en a 6.

    Le plafond empêche à l'inverse qu'une requête réclame la table entière.
    """

    page_size_query_param = "page_size"
    max_page_size = 200
