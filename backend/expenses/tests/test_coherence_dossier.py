"""Cohérence entre un dossier et ses lignes.

Un dossier est l'unité de déclaration : ses lignes ne doivent ni le rejoindre
après coup, ni rester en suspens quand il se clôture.
"""

from datetime import date, datetime

from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile
from budget.models import Budget
from core.models import Country
from expenses.models import Dossier, Expense
from expenses.workflow import Status


class DossierCoherenceTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.pays = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        self.budget = Budget.objects.create(
            country=self.pays, year=2026, amount="10000000"
        )

        self.rep = self._compte("togo.innov", Role.COUNTRY_MANAGER, [self.pays])
        self.siege = self._compte("ceo.innov", Role.SUPER_ADMIN)
        self.login(self.rep)

    def _compte(self, username, role, pays=()):
        user = User.objects.create_user(username, password="Motdepasse-2026-test")
        profil = UserProfile.objects.create(
            user=user, role=role, must_change_password=False
        )
        profil.countries.set(pays)
        return user

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def dossier(self, numero, statut=Status.DRAFT):
        return Dossier.objects.create(
            number=numero, label="Mission", country=self.pays,
            date=date(2026, 1, 1), status=statut, created_by=self.rep.username,
        )

    def ligne(self, dossier, statut=Status.DRAFT, titre="Carburant"):
        return Expense.objects.create(
            dossier=dossier, country=self.pays, title=titre,
            amount="50000", date=timezone.make_aware(datetime(2026, 1, 2)), place="Lomé",
            status=statut, created_by=self.rep.username,
            # Une ligne déclarée est imputée, la base l'exige.
            budget=None if statut == Status.DRAFT else self.budget,
        )

    # --- ajout d'une ligne -------------------------------------------------
    def payload(self, dossier):
        return {
            "dossier": dossier.pk, "country": self.pays.pk,
            "title": "Ligne tardive", "amount": "50000",
            "date": "2026-01-02", "place": "Lomé",
        }

    def test_une_ligne_rejoint_un_dossier_en_brouillon(self):
        response = self.client.post("/api/expenses/", self.payload(self.dossier("N-1")))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_une_ligne_ne_rejoint_pas_un_dossier_declare(self):
        """Régression : la ligne arrivait en brouillon dans un dossier déjà
        passé, donc plus rien ne pouvait la soumettre — la dépense
        disparaissait du circuit."""
        for statut in (
            Status.SUBMITTED, Status.IN_REVIEW,
            Status.JUSTIFIED, Status.UNJUSTIFIED, Status.CLOSED,
        ):
            with self.subTest(statut=statut):
                dossier = self.dossier(f"N-{statut}", statut)

                response = self.client.post("/api/expenses/", self.payload(dossier))

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("dossier", response.data)
                self.assertEqual(dossier.expenses.count(), 0)

    # --- clôture -----------------------------------------------------------
    def test_la_cloture_refuse_une_ligne_en_suspens(self):
        dossier = self.dossier("N-2", Status.JUSTIFIED)
        self.ligne(dossier, Status.JUSTIFIED, "Traitée")
        self.ligne(dossier, Status.SUBMITTED, "En attente")
        self.login(self.siege)

        response = self.client.post(f"/api/dossiers/{dossier.pk}/close/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("En attente", str(response.data))
        dossier.refresh_from_db()
        self.assertEqual(dossier.status, Status.JUSTIFIED)

    def test_la_cloture_accepte_une_ligne_non_justifiee(self):
        """Non justifié est une décision : l'argent est sorti sans preuve, et
        c'est précisément ce que l'écart doit montrer. Rien ne l'empêche de
        clore."""
        dossier = self.dossier("N-3", Status.JUSTIFIED)
        self.ligne(dossier, Status.JUSTIFIED, "Avec preuve")
        self.ligne(dossier, Status.UNJUSTIFIED, "Sans preuve")
        self.login(self.siege)

        response = self.client.post(f"/api/dossiers/{dossier.pk}/close/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dossier.refresh_from_db()
        self.assertEqual(dossier.status, Status.CLOSED)

    # --- une ligne ne devance pas son dossier ------------------------------
    def test_une_ligne_ne_se_soumet_pas_seule(self):
        """Régression : la ligne partait seule, puis se faisait justifier,
        pendant que le dossier restait un brouillon jamais déclaré. L'action
        n'existe plus sur une ligne."""
        dossier = self.dossier("N-4")
        ligne = self.ligne(dossier)

        response = self.client.post(f"/api/expenses/{ligne.pk}/submit/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        ligne.refresh_from_db()
        self.assertEqual(ligne.status, Status.DRAFT)

    def test_le_dossier_emporte_ses_lignes(self):
        """Le chemin normal : le pays soumet le dossier, les lignes suivent."""
        dossier = self.dossier("N-5")
        ligne = self.ligne(dossier)

        response = self.client.post(f"/api/dossiers/{dossier.pk}/submit/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ligne.refresh_from_db()
        self.assertEqual(ligne.status, Status.SUBMITTED)
        self.assertEqual(ligne.budget, self.budget)
