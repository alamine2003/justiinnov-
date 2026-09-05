"""Mixins propres aux dépenses."""

from rest_framework import status as http
from rest_framework.response import Response

from accounts.permissions import get_access
from core.journal import Trace
from core.mixins import NoDestroyModelViewSet
from core.regles import traduire_les_regles

from .transitions import retirer_brouillon


class DraftDeletableViewSet(NoDestroyModelViewSet):
    """CRUD où seul un brouillon peut encore être retiré, par son auteur.

    La règle — et ses refus — vit dans :func:`expenses.transitions.retirer_brouillon` ;
    la vue ne fait que trouver l'objet dans le périmètre (404 sinon) et
    traduire le refus en réponse. ``NoDestroyModelViewSet`` n'inclut pas
    ``DestroyModelMixin``, puisque la suppression est justement l'exception.
    """

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        with traduire_les_regles():
            retirer_brouillon(
                instance, get_access(request.user), Trace.depuis_requete(request)
            )
        return Response(status=http.HTTP_204_NO_CONTENT)
