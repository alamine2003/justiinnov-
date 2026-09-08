"""Aucun justificatif ne se perd : rien ne s'efface tant que la transaction
peut être annulée, un dépôt refusé ne laisse pas d'orphelin, et une trace de
téléchargement n'atteste que d'un fichier réellement servi.

Audit du 8 septembre 2026, §4.4.
"""

import hashlib
from unittest import mock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import status

from accounts.permissions import get_access
from core.journal import Trace
from expenses import transitions
from expenses.models import AuditLog, Dossier, Proof
from expenses.serializers import ProofSerializer

from .base import ExpenseTestCase, in_memory_storage

PDF = b"%PDF-1.4 recu de mission"


@in_memory_storage
class StockageTestCase(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)

    def deposer(self, nom="recu.pdf", contenu=PDF, dossier=None):
        response = self.client.post(
            "/api/proofs/",
            {
                "dossier": (dossier or self.dossier).pk,
                "file": SimpleUploadedFile(nom, contenu, content_type="application/pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Proof.objects.get(pk=response.data["id"])

    def retirer(self):
        return self.client.delete(f"/api/dossiers/{self.dossier.pk}/")

    def assert_piece_intacte(self, piece, chemin):
        """La fiche est là, le fichier aussi, avec la même empreinte."""
        self.assertTrue(Proof.objects.filter(pk=piece.pk).exists())
        self.assertTrue(default_storage.exists(chemin))
        with default_storage.open(chemin, "rb") as contenu:
            self.assertEqual(hashlib.sha256(contenu.read()).hexdigest(), piece.sha256)


class RetraitTests(StockageTestCase):
    def test_une_transaction_annulee_apres_le_retrait_garde_la_piece_et_son_fichier(self):
        piece = self.deposer()
        chemin = piece.file.name

        with self.captureOnCommitCallbacks(execute=True), \
                self.assertRaises(RuntimeError), transaction.atomic():
            transitions.retirer_brouillon(
                self.dossier, get_access(self.owner), Trace.depuis_compte(self.owner)
            )
            self.assertFalse(Proof.objects.filter(pk=piece.pk).exists())
            raise RuntimeError("annulation après le retrait")

        self.assert_piece_intacte(piece, chemin)
        self.assertTrue(Dossier.objects.filter(pk=self.dossier.pk).exists())

    def test_une_ligne_arrivee_pendant_le_retrait_annule_tout_sans_500(self):
        """``ProtectedError`` : la base refuse, la transaction est défaite,
        la pièce et son fichier restent, la réponse est un refus lisible."""
        piece = self.deposer()
        chemin = piece.file.name

        with mock.patch.object(
            Dossier, "delete", side_effect=ProtectedError("ligne ajoutée entre-temps", set())
        ), self.captureOnCommitCallbacks(execute=True):
            response = self.retirer()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_piece_intacte(piece, chemin)
        self.assertTrue(Dossier.objects.filter(pk=self.dossier.pk).exists())
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.DELETED).exists())


class DepotRefuseTests(StockageTestCase):
    def test_un_doublon_refuse_par_la_base_ne_laisse_pas_de_fichier(self):
        """Deux dépôts simultanés du même contenu passent tous deux la
        validation ; la contrainte refuse le second. Son fichier, écrit avant
        l'insertion, ne doit pas rester."""
        premiere = self.deposer()

        with mock.patch.object(ProofSerializer, "_check_duplicate"):
            response = self.client.post(
                "/api/proofs/",
                {
                    "dossier": self.dossier.pk,
                    "file": SimpleUploadedFile("recu.pdf", PDF, content_type="application/pdf"),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Proof.objects.count(), 1)
        _, fichiers = default_storage.listdir(f"justificatifs/{self.togo.pk}/{self.dossier.pk}")
        self.assertEqual(fichiers, [premiere.file.name.rsplit("/", 1)[-1]])


class TelechargementTests(StockageTestCase):
    def test_un_fichier_absent_ne_produit_pas_de_fausse_attestation(self):
        piece = self.deposer()
        default_storage.delete(piece.file.name)
        self.login(self.controller)

        response = self.client.get(f"/api/proofs/{piece.pk}/download/")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.DOWNLOADED).exists())
