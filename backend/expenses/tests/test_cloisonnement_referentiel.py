"""Le référentiel du pays voisin n'existe pas pour le demandeur.

Un identifiant de projet, de bénéficiaire ou de manager d'un autre pays
répond exactement comme un identifiant inconnu : sans cela, un manager
énumérait le référentiel des autres filiales par leurs numéros.
"""

from rest_framework import status

from core.models import ExpenseTitle, Manager, MarketingCategory, Project
from expenses.models import Beneficiary

from .base import ExpenseTestCase


class CloisonnementDuReferentielTests(ExpenseTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.projet_ivoire = Project.objects.create(country=cls.ivoire, name="Projet CI")
        cls.intitule_ivoire = ExpenseTitle.objects.create(country=cls.ivoire, label="Intitulé CI")
        cls.categorie_ivoire = MarketingCategory.objects.create(country=cls.ivoire, name="Catégorie CI")
        cls.beneficiaire_ivoire = Beneficiary.objects.create(country=cls.ivoire, name="Pharmacie CI")
        cls.manager_ivoire = Manager.objects.create(name="Awa Koné")
        cls.manager_ivoire.countries.add(cls.ivoire)

    def _ligne(self, **champs):
        self.login(self.owner)
        charge = {
            "dossier": self.dossier.pk, "country": self.togo.pk, "team": self.team.pk,
            "date": "2026-03-15T10:00:00Z", "title": "Carburant", "amount": "1000.00",
        }
        charge.update(champs)
        return self.client.post("/api/expenses/", charge, format="json")

    def test_un_identifiant_voisin_repond_comme_un_identifiant_inconnu(self):
        inexistant = 987654
        for champ, voisin in (
            ("project", self.projet_ivoire.pk), ("expense_title", self.intitule_ivoire.pk),
            ("marketing_category", self.categorie_ivoire.pk), ("beneficiary", self.beneficiaire_ivoire.pk),
            ("owner", self.manager_ivoire.pk),
        ):
            with self.subTest(champ=champ):
                reponse_voisin = self._ligne(**{champ: voisin})
                reponse_inconnu = self._ligne(**{champ: inexistant})

                self.assertEqual(reponse_voisin.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(reponse_inconnu.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(champ, reponse_voisin.data)
                # Même forme de refus, sans « autre pays » qui trahirait l'existence.
                self.assertNotIn("autre pays", str(reponse_voisin.data[champ]))
                self.assertEqual(
                    str(reponse_voisin.data[champ]).replace(str(voisin), "N"),
                    str(reponse_inconnu.data[champ]).replace(str(inexistant), "N"),
                )

    def test_le_siege_garde_la_verification_de_coherence(self):
        """Pour le siège, qui voit tout, l'identifiant voisin existe : c'est
        alors l'incohérence pays qui est nommée."""
        self.login(self.doo)
        response = self.client.post("/api/expenses/", {
            "dossier": self.dossier.pk, "country": self.togo.pk, "team": self.team.pk,
            "date": "2026-03-15T10:00:00Z", "title": "Carburant", "amount": "1000.00",
            "project": self.projet_ivoire.pk,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", response.data)
