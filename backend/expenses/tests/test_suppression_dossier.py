"""Retrait d'un brouillon de dossier, avec ce qu'il contient."""

from datetime import date

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from expenses.models import AuditLog, Dossier, Expense, Proof
from expenses.workflow import Status

from .base import ExpenseTestCase, in_memory_storage


@in_memory_storage
class SuppressionDossierTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)

    def _piece(self, nom="recu.pdf", contenu=b"%PDF-1.4 recu"):
        response = self.client.post(
            "/api/proofs/",
            {
                "dossier": self.dossier.pk,
                "file": SimpleUploadedFile(nom, contenu, content_type="application/pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return Proof.objects.get(pk=response.data["id"])

    def test_l_auteur_retire_son_brouillon_avec_ses_lignes_et_ses_pieces(self):
        ligne = self.make_expense()
        piece = self._piece()
        chemin = piece.file.name
        self.assertTrue(default_storage.exists(chemin))

        response = self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Dossier.objects.filter(pk=self.dossier.pk).exists())
        self.assertFalse(Expense.objects.filter(pk=ligne.pk).exists())
        self.assertFalse(Proof.objects.filter(pk=piece.pk).exists())
        # Le fichier ne survit pas à sa fiche.
        self.assertFalse(default_storage.exists(chemin))

    def test_chaque_element_emporte_laisse_une_trace(self):
        ligne = self.make_expense(amount="1234.00")
        piece = self._piece()

        self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

        traces = AuditLog.objects.filter(action=AuditLog.Action.DELETED)
        par_type = {t.object_type: t for t in traces}
        self.assertEqual(set(par_type), {"Dossier", "Expense", "Proof"})
        self.assertEqual(par_type["Expense"].object_id, ligne.pk)
        self.assertEqual(par_type["Expense"].detail["amount"], "1234.00")
        self.assertEqual(par_type["Proof"].detail["sha256"], piece.sha256)
        self.assertEqual(par_type["Dossier"].detail["lines"], 1)
        self.assertEqual(par_type["Dossier"].user, "owner.togo")

    def test_les_versions_successives_partent_dans_l_ordre(self):
        """Une nouvelle version référence celle qu'elle remplace, et cette
        référence est protégée : la plus récente doit partir la première."""
        premiere = self._piece()
        self.client.post(
            "/api/proofs/",
            {
                "dossier": self.dossier.pk,
                "file": SimpleUploadedFile("v2.pdf", b"v2", content_type="application/pdf"),
                "replaces": premiere.pk,
            },
            format="multipart",
        )

        response = self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Proof.objects.count(), 0)

    def test_un_tiers_ne_retire_pas_le_brouillon_d_autrui(self):
        self.dossier.created_by = "quelqu-un-dautre"
        self.dossier.save()

        response = self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Dossier.objects.filter(pk=self.dossier.pk).exists())

    def test_un_dossier_portant_la_ligne_d_un_autre_auteur_reste(self):
        """Ranger son brouillon n'autorise pas à effacer le travail d'un
        collègue."""
        mienne = self.make_expense()
        sienne = self.make_expense(created_by="collegue.togo", title="Hôtel")

        response = self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("collegue.togo", str(response.data))
        self.assertTrue(Expense.objects.filter(pk__in=[mienne.pk, sienne.pk]).count() == 2)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.DELETED).exists())

    def test_un_dossier_declare_ne_se_retire_pas(self):
        self.make_expense()
        self.submit_dossier()

        response = self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Dossier.objects.filter(pk=self.dossier.pk).exists())

    def test_une_ligne_declaree_retient_le_dossier(self):
        """Cas de cohérence : un brouillon de dossier ne devrait pas porter
        de ligne déclarée, mais s'il en porte une, elle ne s'efface pas."""
        self.make_expense(status=Status.SUBMITTED)

        response = self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Expense.objects.count(), 1)

    def test_un_dossier_vide_se_retire(self):
        autre = Dossier.objects.create(
            number="N-0002", label="Vide", country=self.togo,
            date=date(self.year, 3, 1), created_by="owner.togo",
        )

        response = self.client.delete(f"/api/dossiers/{autre.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
