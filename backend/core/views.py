"""Vue de santé de la plateforme.

L'API du référentiel, l'authentification et le back-office vivent dans
``accounts`` : ils s'appuient sur les rôles, que ``core`` ne connaît pas
(décision 40). Ne reste ici que ce qui ne demande aucun compte.
"""

from django.db import OperationalError, connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .requetes import client_ip
from .serializers import HealthSerializer


class HealthRateThrottle(SimpleRateThrottle):
    """Le contrôle de santé interroge la base : il se compte par adresse.

    Sans limite, n'importe qui pouvait faire exécuter un ``SELECT`` par
    requête, sans compte ; et la limite nginx se contournait par un en-tête
    ``Authorization`` arbitraire (audit du 8 septembre 2026, §4.6). Le
    contrôle du conteneur, toutes les trente secondes, et celui de la
    livraison restent loin de la limite.
    """

    scope = "health"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": client_ip(request) or self.get_ident(request),
        }


class HealthView(APIView):
    """État de la plateforme, pour Docker, la livraison et le répartiteur.

    Ni compte, ni jeton : le contrôle de santé du conteneur l'interroge
    toutes les trente secondes, un déploiement n'est déclaré réussi que
    lorsqu'il répond, et le répartiteur de charge s'en sert pour choisir
    **vers quelle machine envoyer les gens**. Il ne dit rien du contenu de
    la base.

    Il dit trois choses, et la troisième a été ajoutée pour le répartiteur :

    1. le serveur répond ;
    2. la base est joignable ;
    3. **elle accepte les écritures**.

    Le troisième point n'est pas un détail. Une réplique en attente chaude
    (décision 75) répond parfaitement au ``SELECT 1`` : sa base est vivante,
    simplement en lecture seule. Sans ce contrôle, un répartiteur y
    enverrait des gens qui ne pourraient plus rien enregistrer — et, le jour
    où l'ancienne primaire redémarre après une bascule, il lui rendrait le
    trafic alors qu'elle sert une base **périmée**, arrêtée à l'instant de sa
    perte. C'est ce contrôle qui rend le basculement sûr : une machine qui
    n'est pas la primaire se déclare indisponible, et le répartiteur cesse
    de la choisir.

    ``pg_is_in_recovery()`` est vrai sur une réplique, et pendant une
    reprise à un instant donné (décision 74) tant que la base n'est pas
    ouverte : dans les deux cas, envoyer du monde ici serait une erreur.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [HealthRateThrottle]

    @extend_schema(responses={200: HealthSerializer, 503: HealthSerializer}, auth=[])
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_is_in_recovery()")
                en_reprise = cursor.fetchone()[0]
        except OperationalError:
            return Response(
                {"status": "indisponible", "database": "ko", "writable": False},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if en_reprise:
            return Response(
                {"status": "replique", "database": "ok", "writable": False},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "ok", "writable": True})
