"""Pièces justificatives : empreinte, doublons, versions, téléchargement."""

import hashlib
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from expenses.models import AuditLog, Dossier, Proof

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

    def test_le_fichier_est_range_par_cle_de_dossier(self):
        """Le numéro d'ordre est saisi par un humain et peut changer tant que
        le dossier est en brouillon : le chemin suit la clé, qui ne change
        pas."""
        response = self.upload()

        piece = Proof.objects.get(pk=response.data["id"])
        self.assertIn(f"/{self.dossier.pk}/", piece.file.name)
        self.assertNotIn(self.dossier.number, piece.file.name)

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

    def test_depot_sur_le_dossier_d_un_autre_pays_refuse(self):
        """Le dossier ivoirien n'existe pas pour le Togo : le refus est celui
        d'une clé inconnue, sans rien apprendre de plus."""
        ivoirien = Dossier.objects.create(
            number="CI-0001", label="Mission Abidjan", country=self.ivoire,
            date=self.dossier.date,
        )

        response = self.upload(dossier=ivoirien.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", response.data)
        self.assertEqual(ivoirien.proofs.count(), 0)

    def test_la_completude_ne_se_coche_pas_au_depot(self):
        """« Justificatif complet » est un constat du contrôleur."""
        response = self.upload(is_complete="false")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_complete"])


@in_memory_storage
class ProofImmutabilityTests(ExpenseTestCase):
    """Une pièce est une preuve : on n'en change ni le contenu, ni le
    rattachement. On en dépose une nouvelle version."""

    def setUp(self):
        super().setUp()
        self.login(self.owner)
        self.proof_id = self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "kind": "receipt", "file": pdf()},
            format="multipart",
        ).data["id"]
        self.autre = Dossier.objects.create(
            number="N-0002", label="Autre mission", country=self.togo,
            date=self.dossier.date,
        )

    def test_le_type_reste_modifiable(self):
        response = self.client.patch(
            f"/api/proofs/{self.proof_id}/", {"kind": "invoice"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["kind"], "invoice")
        trace = AuditLog.objects.get(action=AuditLog.Action.UPDATED)
        self.assertEqual(trace.detail["before"]["kind"], "receipt")
        self.assertEqual(trace.detail["after"]["kind"], "invoice")

    def test_le_fichier_le_dossier_et_la_filiation_sont_fixes_au_depot(self):
        for champ, valeur in (
            ("dossier", self.autre.pk),
            ("replaces", self.proof_id),
        ):
            with self.subTest(champ=champ):
                response = self.client.patch(
                    f"/api/proofs/{self.proof_id}/", {champ: valeur}
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(champ, response.data)

        fichier = self.client.patch(
            f"/api/proofs/{self.proof_id}/",
            {"file": pdf("autre.pdf", b"autre")},
            format="multipart",
        )
        self.assertEqual(fichier.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", fichier.data)
        piece = Proof.objects.get(pk=self.proof_id)
        self.assertEqual(piece.dossier, self.dossier)
        self.assertEqual(piece.sha256, hashlib.sha256(CONTENT).hexdigest())

    def test_la_completude_ne_se_modifie_que_par_le_controle(self):
        response = self.client.patch(
            f"/api/proofs/{self.proof_id}/", {"is_complete": False}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Proof.objects.get(pk=self.proof_id).is_complete)

    def test_une_piece_tranchee_ne_se_modifie_plus(self):
        for statut in (
            Proof.ProofStatus.VALIDATED, Proof.ProofStatus.REJECTED,
            Proof.ProofStatus.ARCHIVED,
        ):
            with self.subTest(statut=statut):
                Proof.objects.filter(pk=self.proof_id).update(status=statut)

                response = self.client.patch(
                    f"/api/proofs/{self.proof_id}/", {"kind": "invoice"}
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(Proof.objects.get(pk=self.proof_id).kind, "receipt")


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

    def test_remplacement_journalise_l_empreinte_avant_et_apres(self):
        self.client.post(
            "/api/proofs/",
            {
                "dossier": self.dossier.pk,
                "file": pdf("recu-v2.pdf", b"autre contenu"),
                "replaces": self.first["id"],
            },
            format="multipart",
        )

        trace = AuditLog.objects.get(action=AuditLog.Action.PROOF_REPLACED)
        self.assertEqual(trace.detail["before"]["sha256"], self.first["sha256"])
        self.assertEqual(
            trace.detail["after"]["sha256"], hashlib.sha256(b"autre contenu").hexdigest()
        )
        self.assertEqual(trace.detail["before"]["version"], 1)
        self.assertEqual(trace.detail["after"]["version"], 2)

    def test_un_remplacement_ne_traverse_pas_les_dossiers(self):
        """Remplacer archive la pièce remplacée : on ne remplace que dans le
        même dossier, sinon un dépôt anodin ferait disparaître une preuve
        d'ailleurs."""
        autre = Dossier.objects.create(
            number="N-0002", label="Autre mission", country=self.togo,
            date=self.dossier.date,
        )

        response = self.client.post(
            "/api/proofs/",
            {
                "dossier": autre.pk,
                "file": pdf("v2.pdf", b"version 2"),
                "replaces": self.first["id"],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("replaces", response.data)
        self.assertEqual(
            Proof.objects.get(pk=self.first["id"]).status, Proof.ProofStatus.RECEIVED
        )

    def test_un_manager_togolais_n_archive_pas_une_piece_ivoirienne(self):
        """Faille : ``replaces`` acceptait n'importe quelle pièce, y compris
        celle d'un pays qu'on n'a pas le droit de voir — et l'archivait."""
        ivoirien = Dossier.objects.create(
            number="CI-0001", label="Mission Abidjan", country=self.ivoire,
            date=date(self.year, 2, 1),
        )
        piece_ivoirienne = Proof.objects.create(
            dossier=ivoirien, file="justificatifs/ci.pdf",
            original_name="ci.pdf", sha256="c" * 64,
        )

        response = self.client.post(
            "/api/proofs/",
            {
                "dossier": self.dossier.pk,
                "file": pdf("v2.pdf", b"version 2"),
                "replaces": piece_ivoirienne.pk,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("replaces", response.data)
        piece_ivoirienne.refresh_from_db()
        self.assertEqual(piece_ivoirienne.status, Proof.ProofStatus.RECEIVED)


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

    def review(self, statut, **extra):
        return self.client.post(
            f"/api/proofs/{self.proof_id}/review/", {"status": statut, **extra}
        )

    def test_validation_documentaire(self):
        self.login(self.controller)

        response = self.review("validated")

        self.assertEqual(response.data["status"], "validated")
        self.assertTrue(response.data["is_complete"])

    def test_rejet_sans_motif_refuse(self):
        self.login(self.controller)

        response = self.review("rejected")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_marquer_incomplet(self):
        """Reprend la nuance « reçu (justif incomplet) » du fichier source."""
        self.login(self.controller)

        response = self.review("incomplete")

        self.assertFalse(response.data["is_complete"])

    def test_controle_reserve_aux_roles_habilites(self):
        response = self.review("validated")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_une_piece_tranchee_ne_bouge_plus(self):
        """Validée, rejetée ou archivée, la pièce est figée : seul un
        remplacement fait avancer le dossier. Sans cela, un contrôleur
        pouvait dévalider une pièce, voire ressusciter une pièce archivée."""
        self.login(self.controller)
        for depart in ("validated", "rejected", "archived"):
            for cible in ("received", "to_review", "incomplete", "validated", "rejected"):
                with self.subTest(depart=depart, cible=cible):
                    Proof.objects.filter(pk=self.proof_id).update(status=depart)

                    response = self.review(cible, reason="motif")

                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn("status", response.data)
                    self.assertEqual(Proof.objects.get(pk=self.proof_id).status, depart)

    def test_une_piece_ne_revient_pas_a_l_etat_recu(self):
        self.login(self.controller)

        response = self.review("received")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_une_piece_incomplete_attend_son_complement_puis_se_tranche(self):
        self.login(self.controller)
        self.review("incomplete")

        encore = self.review("incomplete")
        a_controler = self.review("to_review")
        validee = self.review("validated")

        self.assertEqual(encore.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(a_controler.data["status"], "to_review")
        self.assertTrue(a_controler.data["is_complete"])
        self.assertEqual(validee.data["status"], "validated")

    def test_l_audit_dit_ce_qui_s_est_passe(self):
        """Signaler incomplet n'est pas rejeter : le journal ne doit pas
        confondre les deux."""
        self.login(self.controller)

        self.review("incomplete")
        self.review("to_review")
        self.review("validated")

        actions = list(
            AuditLog.objects.filter(object_type="Proof")
            .exclude(action=AuditLog.Action.PROOF_UPLOADED)
            .order_by("pk")
            .values_list("action", flat=True)
        )
        self.assertEqual(
            actions,
            [
                AuditLog.Action.PROOF_INCOMPLETE,
                AuditLog.Action.PROOF_TO_REVIEW,
                AuditLog.Action.APPROVED,
            ],
        )

    def test_dossier_avec_justificatif_peut_etre_justifie(self):
        ligne = self.make_expense()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{ligne.pk}/justify/")

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_une_preuve_reste_deposable_apres_soumission(self):
        """Rassembler la preuve est l'objet même de l'application : une
        dépense non justifiée doit pouvoir être couverte après coup."""
        self.make_expense()
        self.submit_dossier()

        response = self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "file": pdf("complement.pdf", b"complement")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_dossier_cloture_refuse_un_nouveau_justificatif(self):
        depense = self.make_expense()
        self.submit_dossier()
        self.login(self.controller)
        # La ligne doit être tranchée avant la clôture : un dossier ne se
        # clôture pas en laissant une dépense en suspens.
        self.client.post(f"/api/expenses/{depense.pk}/justify/")
        self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")
        cloture = self.client.post(f"/api/dossiers/{self.dossier.pk}/close/")
        self.assertEqual(cloture.status_code, status.HTTP_200_OK)
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

    def test_telechargement_renvoie_le_contenu_en_flux(self):
        response = self.client.get(f"/api/proofs/{self.proof_id}/download/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Un flux, pas un corps chargé en mémoire.
        self.assertTrue(response.streaming)
        self.assertEqual(b"".join(response.streaming_content), CONTENT)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("recu.pdf", response["Content-Disposition"])

    def test_telechargement_journalise(self):
        self.client.get(f"/api/proofs/{self.proof_id}/download/")

        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.DOWNLOADED).exists()
        )

    def test_telechargement_hors_perimetre_refuse(self):
        self.login(self.rep_ivoire)

        response = self.client.get(f"/api/proofs/{self.proof_id}/download/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
