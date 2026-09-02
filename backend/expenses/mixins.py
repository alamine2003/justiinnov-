"""Mixins propres aux dépenses."""

from rest_framework import status as http
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core.mixins import NoDestroyModelViewSet

from .workflow import DELETABLE_STATUSES


class DraftDeletableViewSet(NoDestroyModelViewSet):
    """CRUD où seul un brouillon peut encore être retiré, par son auteur.

    Une fois la dépense déclarée, l'effacer reviendrait à perdre la trace de
    l'argent : c'est précisément ce que l'application doit empêcher. Un
    brouillon jamais soumis n'a en revanche aucune valeur probante — le
    conserver encombrerait les listes sans rien documenter.
    """

    #: Champ portant le nom de l'auteur, comparé au demandeur.
    #: ``None`` pour une ressource sans auteur : le périmètre pays fait foi.
    author_field = "created_by"

    def perform_destroy(self, instance):
        """Effacement effectif.

        Défini ici et non hérité : ``NoDestroyModelViewSet`` n'inclut pas
        ``DestroyModelMixin``, puisque la suppression est justement
        l'exception.
        """
        instance.delete()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.status not in DELETABLE_STATUSES:
            raise ValidationError(
                {
                    "status": (
                        "Cet élément est déclaré : il ne peut plus être "
                        "supprimé. Seul un brouillon peut l'être."
                    )
                }
            )

        author = (
            getattr(instance, self.author_field, "") if self.author_field else ""
        )
        if author and author != request.user.username:
            raise PermissionDenied("Seul l'auteur d'un brouillon peut le supprimer.")

        self.perform_destroy(instance)
        return Response(status=http.HTTP_204_NO_CONTENT)
