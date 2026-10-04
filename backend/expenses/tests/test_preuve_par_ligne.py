"""Le serveur dit quelle ligne est prouvée (décision 107).

``has_proof`` sur chaque ligne, ``lignes_sans_preuve`` sur le dossier :
l'interface affiche « sans justificatif » sans connaître la règle — une
pièce rejetée ou archivée ne prouve rien, une pièce d'avant la 2.0 prouve
encore tout son dossier.
"""

from rest_framework import status

from expenses.models import Proof
from expenses.workflow import Status

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

    def test_une_piece_archivee_ne_prouve_rien(self):
        ligne = self.make_expense(title="Taxi")
        self._piece(ligne, Proof.ProofStatus.ARCHIVED)

        detail = self._detail()

        self.assertFalse(detail["expenses"][0]["has_proof"])
        self.assertEqual(detail["lignes_sans_preuve"], 1)

    def test_la_reponse_a_une_modification_dit_aussi_la_preuve(self):
        """Sans l'annotation de la liste, le sérialiseur relit la règle."""
        ligne = self.make_expense(title="Taxi")
        self._piece(ligne)
        self.login(self.owner)

        reponse = self.client.patch(f"/api/expenses/{ligne.pk}/", {"title": "Taxi aéroport"}, format="json")

        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        self.assertTrue(reponse.data["has_proof"])


class ClotureSansPreuveTests(ExpenseTestCase):
    """Un dossier ne se clôt pas sur une ligne sans pièce exploitable
    (décisions 107 et 115) : la pièce rejetée après la justification
    laissait clôturer un constat que plus rien ne soutenait."""

    def setUp(self):
        super().setUp()
        self.ligne = self.make_expense(
            title="Taxi", status=Status.JUSTIFIED, justified_amount="100000.00"
        )
        self.dossier.status = Status.JUSTIFIED
        self.dossier.save()
        self.piece = Proof.objects.create(
            dossier=self.dossier, expense=self.ligne, file="justificatifs/f.pdf",
            original_name="facture.pdf", sha256="a" * 64,
        )
        self.login(self.controller)

    def _actions(self):
        return self.client.get(f"/api/dossiers/{self.dossier.pk}/").data["allowed_actions"]

    def test_la_piece_rejetee_bloque_la_cloture(self):
        rejet = self.client.post(
            f"/api/proofs/{self.piece.pk}/review/",
            {"status": Proof.ProofStatus.REJECTED, "reason": "illisible"}, format="json",
        )

        self.assertEqual(rejet.status_code, status.HTTP_200_OK, rejet.data)
        self.assertNotIn("close", self._actions())
        cloture = self.client.post(f"/api/dossiers/{self.dossier.pk}/close/", {}, format="json")
        self.assertEqual(cloture.status_code, status.HTTP_400_BAD_REQUEST, cloture.data)
        self.assertIn("proofs", cloture.data)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.JUSTIFIED)

    def test_avec_sa_piece_le_dossier_se_clot(self):
        self.assertIn("close", self._actions())

        cloture = self.client.post(f"/api/dossiers/{self.dossier.pk}/close/", {}, format="json")

        self.assertEqual(cloture.status_code, status.HTTP_200_OK, cloture.data)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.CLOSED)
