"""Messages bilingues : le français est la référence, l'anglais suit
l'en-tête ``Accept-Language``.

Ces tests lisent le catalogue unique compilé (``backend/locale/en/LC_MESSAGES/django.mo``,
produit par ``django-admin compilemessages``, non versionné) : ils échouent
si la compilation n'a pas eu lieu, ce qui est voulu — une image livrée sans
catalogue servirait du français à qui demande l'anglais.
"""

from rest_framework import status

from expenses.workflow import Status

from .base import ExpenseTestCase


class MessagesEnAnglaisTests(ExpenseTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.expense = cls.make_expense(cls)

    def test_une_transition_refusee_repond_en_anglais(self):
        """On ne justifie pas un brouillon : le message, construit avec les
        libellés d'état, doit être entièrement anglais."""
        self.login(self.controller)

        response = self.client.post(
            f"/api/expenses/{self.expense.pk}/justify/", HTTP_ACCEPT_LANGUAGE="en"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        message = str(response.data["status"])
        self.assertIn("Action not possible", message)
        self.assertIn("Draft", message)
        self.assertIn("Submitted", message)
        self.assertNotIn("Brouillon", message)

    def test_le_francais_reste_la_langue_par_defaut(self):
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertIn("Action impossible", str(response.data["status"]))
        self.assertIn("Brouillon", str(response.data["status"]))

    def test_les_libelles_de_statut_suivent_la_langue(self):
        self.login(self.owner)

        anglais = self.client.get(
            f"/api/expenses/{self.expense.pk}/", HTTP_ACCEPT_LANGUAGE="en"
        )
        francais = self.client.get(
            f"/api/expenses/{self.expense.pk}/", HTTP_ACCEPT_LANGUAGE="fr"
        )

        self.assertEqual(anglais.data["status_display"], "Draft")
        self.assertEqual(francais.data["status_display"], "Brouillon")
        self.assertEqual(anglais.data["payment_method_display"], "Cash")

    def test_un_rejet_sans_motif_est_refuse_en_anglais(self):
        self.submit_dossier()
        self.login(self.controller)

        response = self.client.post(
            f"/api/expenses/{self.expense.pk}/reject/", {"note": ""},
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", str(response.data["note"]))

    def test_le_depassement_reste_reconnaissable_dans_les_deux_langues(self):
        """Le message commence par « Dépassement » / « Overrun » : l'interface
        s'y repère, quelle que soit la langue."""
        self.budget.amount = 1
        self.budget.overrun_policy = "warn"
        self.budget.save()

        self.login(self.owner)
        response = self.client.post(
            f"/api/dossiers/{self.dossier.pk}/submit/", HTTP_ACCEPT_LANGUAGE="en"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["warning"].startswith("Overrun"))
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.SUBMITTED)
