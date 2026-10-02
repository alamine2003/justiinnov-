"""Le serveur dit quelle ligne est prouvée (décision 107).

``has_proof`` sur chaque ligne, ``lignes_sans_preuve`` sur le dossier :
l'interface affiche « sans justificatif » sans connaître la règle — une
pièce rejetée ou archivée ne prouve rien, une pièce d'avant la 2.0 prouve
encore tout son dossier.
"""

from rest_framework import status

from expenses.models import Proof

from .base import ExpenseTestCase


class PreuveParLigneTests(ExpenseTestCase):
    def _piece(self, ligne=None, statut=Proof.ProofStatus.RECEIVED, empreinte="a"):
        return Proof.objects.create(
            dossier=self.dossier, expense=ligne, file="justificatifs/f.pdf",
            original_name="facture.pdf", sha256=empreinte * 64, status=statut,
        )

    def _detail(self):
        self.login(self.owner)
        reponse = self.client.get(f"/api/dossiers/{self.dossier.pk}/")
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        return reponse.data

    def test_chaque_ligne_dit_si_elle_est_prouvee(self):
        prouvee = self.make_expense(title="Taxi")
        self.make_expense(title="Hôtel")
        rejetee = self.make_expense(title="Repas")
        self._piece(prouvee)
        self._piece(rejetee, Proof.ProofStatus.REJECTED, empreinte="b")

        detail = self._detail()

        self.assertEqual(
            {e["title"]: e["has_proof"] for e in detail["expenses"]},
            {"Taxi": True, "Hôtel": False, "Repas": False},
        )
        self.assertEqual(detail["lignes_sans_preuve"], 2)
        liste = self.client.get("/api/dossiers/").data["results"]
        self.assertEqual(
            next(d for d in liste if d["id"] == self.dossier.pk)["lignes_sans_preuve"], 2
        )
        ligne = self.client.get(f"/api/expenses/{prouvee.pk}/").data
        self.assertTrue(ligne["has_proof"])

    def test_une_piece_d_avant_la_2_0_prouve_tout_le_dossier(self):
        self.make_expense(title="Taxi")
        self._piece()

        detail = self._detail()

        self.assertTrue(detail["expenses"][0]["has_proof"])
        self.assertEqual(detail["lignes_sans_preuve"], 0)
