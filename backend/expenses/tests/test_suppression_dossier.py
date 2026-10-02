"""Un dossier ne se retire pas ; une ligne en brouillon, si — avec ses pièces.

Depuis la 2.0, un dossier naît avec son projet, un par type de dossier
(décision 106) : l'API n'en retire aucun. Une ligne en brouillon se retire
encore par son auteur, et ses pièces partent avec elle, chacune tracée
(décision 107).
"""

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from expenses.models import AuditLog, Dossier, Expense, Proof
from expenses.workflow import Status

from .base import ExpenseTestCase, in_memory_storage

#: Un fichier n'est une pièce que si son contenu confirme son extension.
PDF = b"%PDF-1.4 "


@in_memory_storage
class SuppressionTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)

    def _piece(self, ligne, nom="recu.pdf", contenu=b"recu", replaces=None):
        charge = {
            "expense": ligne.pk,
            "file": SimpleUploadedFile(nom, PDF + contenu, content_type="application/pdf"),
        }
        if replaces is not None:
            charge["replaces"] = replaces.pk
        response = self.client.post("/api/proofs/", charge, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Proof.objects.get(pk=response.data["id"])

    def test_un_dossier_ne_se_retire_pas(self):
        response = self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Dossier.objects.filter(pk=self.dossier.pk).exists())
        self.assertNotIn(
            "delete", self.client.get(f"/api/dossiers/{self.dossier.pk}/").data["allowed_actions"]
        )

    def test_un_dossier_ne_se_cree_pas(self):
        response = self.client.post(
            "/api/dossiers/",
            {"project": self.projet.pk, "kind": self.stands.pk, "date": f"{self.year}-04-01"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_la_ligne_part_avec_ses_pieces_et_leurs_fichiers(self):
        ligne = self.make_expense(amount="1234.00")
        piece = self._piece(ligne)
        chemin = piece.file.name

        # Le fichier s'efface après la validation de la transaction
        # (``expenses.stockage``) : les rappels après commit sont joués ici.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(f"/api/expenses/{ligne.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Expense.objects.filter(pk=ligne.pk).exists())
        self.assertFalse(Proof.objects.filter(pk=piece.pk).exists())
        self.assertFalse(default_storage.exists(chemin))
        traces = {t.object_type: t for t in AuditLog.objects.filter(action=AuditLog.Action.DELETED)}
        self.assertEqual(set(traces), {"Expense", "Proof"})
        self.assertEqual(traces["Expense"].detail["amount"], "1234.00")
        self.assertEqual(traces["Proof"].detail["sha256"], piece.sha256)

    def test_les_versions_successives_partent_dans_l_ordre(self):
        """Une nouvelle version référence celle qu'elle remplace, et cette
        référence est protégée : la plus récente doit partir la première."""
        ligne = self.make_expense()
        premiere = self._piece(ligne)
        self._piece(ligne, "v2.pdf", b"v2", replaces=premiere)

        response = self.client.delete(f"/api/expenses/{ligne.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Proof.objects.count(), 0)

    def test_une_ligne_declaree_ne_se_retire_pas(self):
        ligne = self.make_expense(status=Status.SUBMITTED)

        response = self.client.delete(f"/api/expenses/{ligne.pk}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Expense.objects.filter(pk=ligne.pk).exists())

    def test_une_ligne_qui_porte_une_piece_ne_change_plus_de_dossier(self):
        ligne = self.make_expense()
        self._piece(ligne)
        autre = Dossier.objects.create(
            number="N-0002", label="Autre", country=self.togo, team=self.team,
            date=self.dossier.date, created_by=self.owner.username,
        )

        response = self.client.patch(
            f"/api/expenses/{ligne.pk}/", {"dossier": autre.pk}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", response.data)
        ligne.refresh_from_db()
        self.assertEqual(ligne.dossier, self.dossier)
