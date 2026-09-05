"""Messages bilingues des budgets : l'anglais suit ``Accept-Language``.

Lit le catalogue unique compilé ``backend/locale/en/LC_MESSAGES/django.mo`` (produit
par ``django-admin compilemessages``, non versionné).
"""

from decimal import Decimal

from rest_framework import status

from budget.models import BudgetReallocation

from .test_budgets import BudgetTestCase


class MessagesEnAnglaisTests(BudgetTestCase):
    def test_un_refus_sans_motif_est_refuse_en_anglais(self):
        reallocation = BudgetReallocation.objects.create(
            source=self.budget_togo, target=self.budget_ivoire,
            amount=Decimal("1000.00"), reason="Renfort", requested_by="ceo.innov",
        )
        self.login(self.doo)

        response = self.client.post(
            f"/api/reallocations/{reallocation.pk}/reject/", {"note": ""},
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["note"], ["A refusal must state a reason."])

    def test_la_politique_de_depassement_s_affiche_en_anglais(self):
        self.login(self.siege)

        anglais = self.client.get(
            f"/api/budgets/{self.budget_togo.pk}/", HTTP_ACCEPT_LANGUAGE="en"
        )
        francais = self.client.get(f"/api/budgets/{self.budget_togo.pk}/")

        self.assertEqual(anglais.data["overrun_policy_display"], "Block")
        self.assertEqual(francais.data["overrun_policy_display"], "Bloquer")

    def test_une_dimension_de_trop_est_expliquee_en_anglais(self):
        self.login(self.siege)

        response = self.client.post(
            "/api/budgets/",
            {"country": self.togo.pk, "year": 2027, "amount": "1.00",
             "overrun_policy": "warn", "team": "", "project": ""},
            HTTP_ACCEPT_LANGUAGE="en",
        )
        # Sans dimension, l'enveloppe se crée : le contrôle vise seulement
        # la langue de la réponse sur une erreur de validation ; on force
        # donc une erreur en refaisant la même enveloppe.
        doublon = self.client.post(
            "/api/budgets/",
            {"country": self.togo.pk, "year": 2027, "amount": "1.00"},
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(doublon.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "An envelope already exists", str(doublon.data["non_field_errors"])
        )
