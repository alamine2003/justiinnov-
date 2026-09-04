"""Champs obligatoires à la soumission (cahier des charges §7).

Une dépense déclarée dit qui l'a engagée : équipe et manager sont exigés au
moment où le dossier part, et seulement là. En brouillon, la ligne peut
rester incomplète — l'import du classeur historique en crée sans référentiel
connu, et une saisie se fait en plusieurs fois. Lieu, projet et intitulé
restent facultatifs (décision consignée dans ``docs/model-de-donnees.md``).
"""

from rest_framework import status

from expenses.workflow import Status

from .base import ExpenseTestCase


class SoumissionCompleteTests(ExpenseTestCase):
    def test_une_ligne_sans_equipe_bloque_la_soumission(self):
        ligne = self.make_expense(team=None, title="Taxi aéroport")

        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        message = str(response.data["expenses"])
        self.assertIn("Taxi aéroport", message)
        self.assertIn("sans équipe", message)
        ligne.refresh_from_db()
        self.assertEqual(ligne.status, Status.DRAFT)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.DRAFT)

    def test_une_ligne_sans_owner_bloque_la_soumission(self):
        self.make_expense(owner=None, title="Hôtel")

        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Hôtel", str(response.data["expenses"]))
        self.assertIn("sans manager", str(response.data["expenses"]))

    def test_le_message_nomme_chaque_ligne_incomplete(self):
        self.make_expense(title="Complète")
        self.make_expense(team=None, owner=None, title="Vide")
        self.make_expense(owner=None, title="Sans manager")

        response = self.submit_dossier()

        message = str(response.data["expenses"])
        self.assertIn("2 ligne(s) incomplète(s)", message)
        self.assertIn("« Vide » (sans équipe, sans manager)", message)
        self.assertIn("« Sans manager » (sans manager)", message)
        self.assertNotIn("Complète", message)

    def test_lieu_projet_et_intitule_restent_facultatifs(self):
        self.make_expense(place="", project=None, expense_title=None)

        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], Status.SUBMITTED)

    def test_un_brouillon_incomplet_se_cree_quand_meme(self):
        """Le contrôle vaut à la soumission : un brouillon reste une matière
        de travail, et l'import en crée sans équipe ni manager."""
        self.login(self.owner)

        response = self.client.post(
            "/api/expenses/",
            {
                "dossier": self.dossier.pk, "country": self.togo.pk,
                "date": f"{self.year}-03-15T10:00:00Z", "title": "Brouillon",
                "amount": "1000.00",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNone(response.data["team"])
        self.assertIsNone(response.data["owner"])
