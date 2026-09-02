"""Pièces justificatives : empreinte, doublons, versions, téléchargement."""

import hashlib

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from expenses.models import AuditLog, Proof

from .base import ExpenseTestCase, in_memory_storage

CONTENT = b"%PDF-1.4 recu de mission"


def pdf(name="recu.pdf", content=CONTENT):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@in_memory_storage
class ProofUploadTests(ExpenseTestCase):
    def upload(self, **extra):
        payload = {"dossier": self.dossier.pk, "kind": "receipt", "file": pdf()}
        payload.update(extra)
        return self.client.post("/api/proofs/", payload, format="multipart")

    def setUp(self):
        super().setUp()
        self.login(self.owner)

    def test_depot_calcule_l_empreinte_et_la_taille(self):
        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["sha256"], hashlib.sha256(CONTENT).hexdigest())
        self.assertEqual(response.data["size"], len(CONTENT))
        self.assertEqual(response.data["original_name"], "recu.pdf")
        self.assertEqual(response.data["uploaded_by"], "owner.togo")
        self.assertEqual(response.data["version"], 1)

    def test_le_fichier_n_est_pas_exposé_directement(self):
        """Le contenu passe par une vue authentifiée, jamais par une URL
        publique."""
        response = self.upload()

        self.assertNotIn("file", response.data)
        self.assertEqual(
            response.data["download_url"], f"/api/proofs/{response.data['id']}/download/"
        )

    def test_doublon_sur_le_meme_dossier_refuse(self):
        self.upload()

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_meme_fichier_sur_un_autre_dossier_autorise(self):
        """La détection de doublon vaut à l'intérieur d'un ensemble
        documentaire, pas entre dossiers distincts."""
        from expenses.models import Dossier

        autre = Dossier.objects.create(
            number="N-0002", label="Autre mission", country=self.togo,
            date=self.dossier.date,
        )
        self.upload()

        response = self.upload(dossier=autre.pk)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_fichier_trop_volumineux_refuse(self):
        with self.settings(MAX_PROOF_SIZE=10):
            response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_depot_journalise(self):
        response = self.upload()

        entry = AuditLog.objects.filter(
            action=AuditLog.Action.PROOF_UPLOADED
        ).first()
        self.assertEqual(entry.detail["sha256"], response.data["sha256"])
        self.assertEqual(entry.detail["dossier"], "N-0001")
        self.assertEqual(entry.country, self.togo)


@in_memory_storage
class ProofVersionTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)
        self.first = self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "kind": "receipt", "file": pdf()},
            format="multipart",
        ).data

    def test_remplacement_incremente_la_version_et_archive_l_ancienne(self):
        response = self.client.post(
            "/api/proofs/",
            {
                "dossier": self.dossier.pk,
                "kind": "receipt",
                "file": pdf("recu-v2.pdf", b"%PDF-1.4 recu corrige"),
                "replaces": self.first["id"],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["version"], 2)
        ancienne = Proof.objects.get(pk=self.first["id"])
        self.assertEqual(ancienne.status, Proof.ProofStatus.ARCHIVED)

    def test_double_remplacement_de_la_meme_piece_refuse(self):
        """La relation « remplace » est unique : une seconde tentative doit
        être refusée proprement, pas violer une contrainte en base."""
        self.client.post(
            "/api/proofs/",
            {
                "dossier": self.dossier.pk,
                "file": pdf("v2.pdf", b"version 2"),
                "replaces": self.first["id"],
            },
            format="multipart",
        )

        response = self.client.post(
            "/api/proofs/",
            {
                "dossier": self.dossier.pk,
                "file": pdf("v3.pdf", b"version 3"),
                "replaces": self.first["id"],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("replaces", response.data)

    def test_remplacement_journalise_comme_tel(self):
        self.client.post(
            "/api/proofs/",
            {
                "dossier": self.dossier.pk,
                "file": pdf("recu-v2.pdf", b"autre contenu"),
                "replaces": self.first["id"],
            },
            format="multipart",
        )

        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.PROOF_REPLACED).exists()
        )


@in_memory_storage
class ProofReviewTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)
        self.proof_id = self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "kind": "invoice", "file": pdf()},
            format="multipart",
        ).data["id"]

    def test_validation_documentaire(self):
        self.login(self.controller)

        response = self.client.post(
            f"/api/proofs/{self.proof_id}/review/", {"status": "validated"}
        )

        self.assertEqual(response.data["status"], "validated")
        self.assertTrue(response.data["is_complete"])

    def test_rejet_sans_motif_refuse(self):
        self.login(self.controller)

        response = self.client.post(
            f"/api/proofs/{self.proof_id}/review/", {"status": "rejected"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_marquer_incomplet(self):
        """Reprend la nuance « reçu (justif incomplet) » du fichier source."""
        self.login(self.controller)

        response = self.client.post(
            f"/api/proofs/{self.proof_id}/review/", {"status": "incomplete"}
        )

        self.assertFalse(response.data["is_complete"])

    def test_controle_reserve_aux_roles_habilites(self):
        response = self.client.post(
            f"/api/proofs/{self.proof_id}/review/", {"status": "validated"}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dossier_avec_justificatif_peut_etre_justifie(self):
        self.client.post(f"/api/dossiers/{self.dossier.pk}/submit/")
        self.login(self.controller)

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_une_preuve_reste_deposable_apres_soumission(self):
        """Rassembler la preuve est l'objet même de l'application : une
        dépense non justifiée doit pouvoir être couverte après coup."""
        self.client.post(f"/api/dossiers/{self.dossier.pk}/submit/")

        response = self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "file": pdf("complement.pdf", b"complement")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_dossier_cloture_refuse_un_nouveau_justificatif(self):
        self.client.post(f"/api/dossiers/{self.dossier.pk}/submit/")
        self.login(self.controller)
        self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")
        self.client.post(f"/api/dossiers/{self.dossier.pk}/close/")
        self.login(self.owner)

        response = self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "file": pdf("tardif.pdf", b"tardif")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@in_memory_storage
class ProofDownloadTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)
        self.proof_id = self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "file": pdf()},
            format="multipart",
        ).data["id"]

    def test_telechargement_renvoie_le_contenu(self):
        response = self.client.get(f"/api/proofs/{self.proof_id}/download/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), CONTENT)

    def test_telechargement_journalise(self):
        self.client.get(f"/api/proofs/{self.proof_id}/download/")

        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.DOWNLOADED).exists()
        )

    def test_telechargement_hors_perimetre_refuse(self):
        self.login(self.rep_ivoire)

        response = self.client.get(f"/api/proofs/{self.proof_id}/download/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
