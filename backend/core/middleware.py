"""Middleware qui expose la requête courante à l'historisation et au journal.

Les signaux d'historisation (``core.signals``) n'ont pas accès à la requête :
ce middleware la pose dans une variable de contexte (``core.requetes``), d'où
la façade ``core.journal`` lit l'auteur et son adresse. L'utilisateur n'est pas résolu ici mais au
moment de l'écriture : pour une requête par jeton, ``request.user`` n'est
forcé par DRF qu'à l'entrée de la vue, bien après ce middleware.
"""

from .journalisation import ENTETE, poser_identifiant, retirer_identifiant
from .requetes import reset_current_request, set_current_request


class CurrentRequestMiddleware:
    """Pose la requête courante et son identifiant, les retire à la sortie.

    L'identifiant sert à relier entre elles les lignes de journal d'une même
    requête, et repart en en-tête de réponse : un utilisateur qui signale un
    incident peut le citer, et on retrouve sa trace.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        jeton = set_current_request(request)
        identifiant, jeton_identifiant = poser_identifiant(request)
        try:
            reponse = self.get_response(request)
            reponse[ENTETE] = identifiant
            return reponse
        finally:
            retirer_identifiant(jeton_identifiant)
            reset_current_request(jeton)
