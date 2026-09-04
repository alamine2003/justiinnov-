"""Course réelle entre deux approbations d'une même réallocation.

Deux connexions distinctes approuvent le même transfert « en même temps ».
La seconde doit attendre le verrou posé sur la réallocation par la première,
puis constater qu'elle est déjà approuvée — et non relire un statut
« en attente » et exécuter le transfert une seconde fois.

Un ``TransactionTestCase`` est nécessaire : les autres tests s'exécutent
dans une transaction jamais validée, invisible à une seconde connexion.
"""

import threading
import time
from decimal import Decimal

from django.core.cache import cache
from django.db import connection, transaction
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.models import Budget, BudgetReallocation
from core.models import Country, Project


class ApprobationConcurrenteTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        self.source = Budget.objects.create(
            country=self.togo, year=2026, amount=Decimal("10000000.00")
        )
        projet = Project.objects.create(country=self.togo, name="Projet TG")
        self.cible = Budget.objects.create(
            country=self.togo, year=2026, project=projet, amount=Decimal("0.00")
        )
        self.reallocation = BudgetReallocation.objects.create(
            source=self.source, target=self.cible,
            amount=Decimal("1000000.00"), reason="Renfort",
            requested_by="ceo.innov",
        )
        self.doo = make_user("do.innov", Role.DOO)
        self.doo_bis = make_user("do2.innov", Role.DOO)
        self.url = f"/api/reallocations/{self.reallocation.pk}/approve/"

    def _client(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def _attendre_une_session_bloquee(self, delai=10):
        """Attend qu'une autre session PostgreSQL attende un verrou.

        Sondé depuis une transaction ouverte, ``pg_stat_activity`` rend un
        instantané figé à sa première lecture : il faut le jeter à chaque
        tour (``pg_stat_clear_snapshot``) pour voir la session arriver.
        """
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
                if cursor.fetchone()[0]:
                    return True
            time.sleep(0.05)
        return False

    def test_la_seconde_approbation_attend_le_verrou_puis_echoue(self):
        resultats = {}

        def seconde_approbation():
            try:
                resultats["response"] = self._client(self.doo_bis).post(self.url)
            finally:
                # Connexion propre au fil : la fermer, sans quoi elle
                # survivrait à la destruction de la base de test.
                connection.close()

        concurrent = threading.Thread(target=seconde_approbation)
        with transaction.atomic():
            # Première approbation : verrous pris, transaction encore ouverte.
            premiere = self._client(self.doo).post(self.url)
            self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)

            concurrent.start()
            bloquee = self._attendre_une_session_bloquee()
            # La validation libère les verrous : la seconde relit alors la
            # réallocation, désormais approuvée.
        concurrent.join(timeout=10)

        self.assertTrue(bloquee, "la seconde approbation aurait dû attendre le verrou")
        self.assertFalse(concurrent.is_alive(), "la seconde approbation n'a pas abouti")
        seconde = resultats["response"]
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        self.assertIn("status", seconde.data)
        self.source.refresh_from_db()
        self.cible.refresh_from_db()
        # Le transfert n'a eu lieu qu'une fois.
        self.assertEqual(self.source.amount, Decimal("9000000.00"))
        self.assertEqual(self.cible.amount, Decimal("1000000.00"))
