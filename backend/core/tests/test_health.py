"""Le point de santé, sur lequel repose le déploiement.

Docker ne déclare le backend prêt, et la livraison continue ne déclare un
déploiement réussi, que lorsque ``/api/health/`` répond. Il doit donc
répondre sans compte, sans jeton, et dire vrai sur la base.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import OperationalError
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile


class HealthTests(APITestCase):
    def test_repond_sans_authentification(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_signale_une_base_injoignable(self):
        with patch("core.views.connection") as connection:
            connection.cursor.side_effect = OperationalError("connexion refusée")
            response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["database"], "ko")

    def test_ne_revele_rien_et_ne_pose_pas_de_cookie(self):
        response = self.client.get("/api/health/")

        self.assertNotIn("Set-Cookie", response)
        self.assertEqual(set(response.json()), {"status", "database"})

    def test_reste_joignable_avec_un_mot_de_passe_provisoire(self):
        # Le verrou du mot de passe provisoire ferme toute l'API ; la santé de
        # la plateforme n'a rien à voir avec le compte qui la demande.
        user = User.objects.create_user(username="siege.test", password="Provisoire-2026")
        UserProfile.objects.create(user=user, role=Role.ADMIN, must_change_password=True)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
