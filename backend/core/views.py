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
from rest_framework.views import APIView

from .serializers import HealthSerializer


class HealthView(APIView):
    """État de la plateforme, pour Docker et la livraison continue.

    Ni compte, ni jeton, ni limitation de débit : le contrôle de santé du
    conteneur l'interroge toutes les trente secondes, et un déploiement n'est
    déclaré réussi que lorsqu'il répond. Il ne dit que deux choses — le
    serveur répond, la base est joignable — et rien sur ce qu'elle contient.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(responses={200: HealthSerializer, 503: HealthSerializer}, auth=[])
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except OperationalError:
            return Response(
                {"status": "indisponible", "database": "ko"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "ok"})
