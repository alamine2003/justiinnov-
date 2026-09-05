"""Le même code TOTP présenté deux fois au même instant ne sert qu'une fois.

La mise à jour conditionnelle du compteur (``accounts.totp.consommer_code``)
tranche en base : pas de verrou à attendre, mais une seule des deux
requêtes voit sa mise à jour aboutir.
"""

import threading

import pyotp
from django.db import connection
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Role
from accounts.tests.test_scoping import make_user


class RejeuSimultaneTests(TransactionTestCase):
    def test_deux_connexions_avec_le_meme_code(self):
        user = make_user("rejeu.innov", Role.DF)
        user.set_password("Motdepasse-2026-test")
        user.save()
        secret = user.profile.totp_secret
        code = pyotp.TOTP(secret).now()
        reponses = []

        def connexion():
            try:
                reponses.append(APIClient().post(
                    "/api/token-auth/",
                    {"username": "rejeu.innov", "password": "Motdepasse-2026-test", "code": code},
                    format="json",
                ))
            finally:
                connection.close()

        fils = [threading.Thread(target=connexion) for _ in range(2)]
        for f in fils: f.start()
        for f in fils: f.join(timeout=10)

        codes = sorted(r.status_code for r in reponses)
        self.assertEqual(codes, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST], [r.data for r in reponses])
