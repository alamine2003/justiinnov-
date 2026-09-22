"""Le point de santé, sur lequel repose le déploiement.

Docker ne déclare le backend prêt, et la livraison continue ne déclare un
déploiement réussi, que lorsque ``/api/health/`` répond. Il doit donc
répondre sans compte, sans jeton, et dire vrai sur la base.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.core.cache import cache
from django.db import OperationalError
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile


class HealthTests(APITestCase):
    def test_repond_sans_authentification(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(), {"status": "ok", "database": "ok", "writable": True}
        )

    def test_signale_une_base_injoignable(self):
        with patch("core.views.connection") as connection:
            connection.cursor.side_effect = OperationalError("connexion refusée")
            response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["database"], "ko")

    def test_ne_revele_rien_et_ne_pose_pas_de_cookie(self):
        response = self.client.get("/api/health/")

        self.assertNotIn("Set-Cookie", response)
        self.assertEqual(set(response.json()), {"status", "database", "writable"})

    def test_une_replique_se_declare_indisponible(self):
        """Une base en lecture seule répond parfaitement au ``SELECT 1``.

        C'est ce qui rend ce contrôle nécessaire : sans lui, le répartiteur
        enverrait des gens sur une réplique où ils ne pourraient plus rien
        enregistrer — et, une fois l'ancienne primaire redémarrée après une
        bascule, il lui rendrait le trafic alors qu'elle sert une base
        **périmée**, arrêtée à l'instant de sa perte.
        """
        with patch("core.views.connection") as connection:
            curseur = connection.cursor.return_value.__enter__.return_value
            curseur.fetchone.return_value = (True,)
            response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["status"], "replique")
        self.assertFalse(response.json()["writable"])
        # La base va bien : c'est la machine qui n'est pas la bonne.
        self.assertEqual(response.json()["database"], "ok")

    def test_une_primaire_se_declare_disponible(self):
        with patch("core.views.connection") as connection:
            curseur = connection.cursor.return_value.__enter__.return_value
            curseur.fetchone.return_value = (False,)
            response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["writable"])

    def test_une_base_injoignable_n_est_pas_dite_inscriptible(self):
        """Le répartiteur lit ce champ : il ne doit jamais valoir vrai quand
        on ne sait pas."""
        with patch("core.views.connection") as connection:
            connection.cursor.side_effect = OperationalError("connexion refusée")
            response = self.client.get("/api/health/")

        self.assertFalse(response.json()["writable"])

    def test_sans_nom_la_machine_ne_se_presente_pas(self):
        """Le défaut ne révèle rien de plus qu'avant : le champ est absent,
        pas vide."""
        with self.settings(SERVEUR_NOM=""):
            response = self.client.get("/api/health/")

        self.assertNotIn("machine", response.json())

    def test_avec_un_nom_la_machine_dit_qui_repond(self):
        """Derrière un aiguillage, deux machines rendent le même corps pour
        le même nom de domaine. Pendant une bascule, savoir laquelle a servi
        est la seule question — et c'est ainsi qu'on voit une ancienne
        primaire rallumée reprendre le trafic (audit de résilience §9)."""
        with self.settings(SERVEUR_NOM="2"):
            response = self.client.get("/api/health/")

        self.assertEqual(response.json()["machine"], "2")

    def test_une_replique_se_presente_aussi(self):
        """La machine qui refuse le trafic doit pouvoir dire que c'est elle :
        sinon le chronomètre ne distingue pas « 2 en réplique » de « 2 en
        panne »."""
        with self.settings(SERVEUR_NOM="2"), patch.object(connection, "cursor") as cursor:
            cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
            response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["status"], "replique")
        self.assertEqual(response.json()["machine"], "2")

    def test_reste_joignable_avec_un_mot_de_passe_provisoire(self):
        # Le verrou du mot de passe provisoire ferme toute l'API ; la santé de
        # la plateforme n'a rien à voir avec le compte qui la demande.
        user = User.objects.create_user(username="siege.test", password="Provisoire-2026")
        UserProfile.objects.create(user=user, role=Role.ADMIN, must_change_password=True)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_la_sonde_reste_loin_de_la_limite_et_l_abus_est_refuse(self):
        """Docker interroge toutes les trente secondes, la livraison quelques
        fois : jamais un 429 pour eux. Mais ce point fait un ``SELECT`` sans
        compte, et il se compte par adresse (audit du 8 septembre 2026,
        §4.6, ``HealthRateThrottle``, 60/min) : la soixante-et-unième requête
        de la minute est refusée — en JSON, comme toute réponse de l'API.

        Remplace « ne déclenche pas de limite anonyme » (70 requêtes, toutes
        en 200), écrit avant cette limite et contredit par elle.
        """
        cache.clear()
        for _ in range(60):
            self.assertEqual(self.client.get("/api/health/").status_code, status.HTTP_200_OK)

        refus = self.client.get("/api/health/")

        self.assertEqual(refus.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(refus["Content-Type"].split(";")[0], "application/json")

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_n_est_pas_redirige_vers_https(self):
        """Docker interroge le conteneur en clair, sur sa boucle locale : une
        redirection 301 le laisserait « unhealthy » et rien ne démarrerait."""
        sante = self.client.get("/api/health/", secure=False)
        autre = self.client.get("/api/countries/", secure=False)

        self.assertEqual(sante.status_code, status.HTTP_200_OK)
        self.assertEqual(autre.status_code, status.HTTP_301_MOVED_PERMANENTLY)
