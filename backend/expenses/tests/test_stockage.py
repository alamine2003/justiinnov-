"""Aucun justificatif ne se perd : rien ne s'efface tant que la transaction
peut être annulée, un dépôt refusé ne laisse pas d'orphelin, et une trace de
téléchargement n'atteste que d'un fichier réellement servi.

Audit du 8 septembre 2026, §4.4.
"""

import hashlib
from datetime import timedelta
from unittest import mock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework import status

from accounts.permissions import get_access
from core.journal import Trace
from expenses import stockage, transitions
from expenses.models import AuditLog, Dossier, FichierASupprimer, Proof
from expenses.serializers import ProofSerializer
from expenses.stockage import DELAI_DE_REPRISE, ESSAIS_MAX

from .base import ExpenseTestCase, in_memory_storage

PDF = b"%PDF-1.4 recu de mission"


@in_memory_storage
class StockageTestCase(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        # Un stockage vide par test. Le stockage en mémoire n'est pas
        # transactionnel : la base est rendue à chaque test, pas lui, et ce
        # qu'un test y écrit restait pour les suivants de la même classe —
        # ``recu.pdf`` déposé par un test « nominal » réapparaissait dans
        # l'inventaire des orphelins du test d'après, un second
        # ``egare.pdf`` devenait ``egare_XXXXXXX.pdf`` (CI #25, trois échecs
        # pour une seule cause). Réappliquer le réglage recrée le stockage :
        # c'est ce que Django fait lui-même sur ``setting_changed``.
        stockage_vide = self.settings(**in_memory_storage.options)
        stockage_vide.enable()
        self.addCleanup(stockage_vide.disable)
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
    def test_le_fichier_s_efface_apres_le_commit_et_la_demande_le_dit(self):
        piece = self.deposer()
        chemin = piece.file.name

        with self.captureOnCommitCallbacks(execute=True):
            response = self.retirer()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Proof.objects.filter(pk=piece.pk).exists())
        self.assertFalse(default_storage.exists(chemin))
        demande = FichierASupprimer.objects.get(name=chemin)
        self.assertIsNotNone(demande.deleted_at)
        self.assertEqual(demande.sha256, piece.sha256)
        self.assertEqual(demande.dossier_number, "N-0001")
        self.assertEqual(demande.requested_by, "owner.togo")

    def test_le_fichier_ne_s_efface_pas_avant_le_commit(self):
        """Tant que la transaction n'est pas validée, l'objet reste dans le
        stockage — un retour arrière doit pouvoir le retrouver."""
        piece = self.deposer()
        chemin = piece.file.name

        # Sous TestCase, rien n'est jamais validé : les rappels après commit
        # ne sont pas joués, comme si la transaction était encore ouverte.
        response = self.retirer()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(default_storage.exists(chemin))
        self.assertIsNone(FichierASupprimer.objects.get(name=chemin).deleted_at)

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
        self.assertFalse(FichierASupprimer.objects.filter(name=chemin).exists())

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
        self.assertIn("rien n'a été supprimé", str(response.data))
        self.assert_piece_intacte(piece, chemin)
        self.assertTrue(Dossier.objects.filter(pk=self.dossier.pk).exists())
        self.assertFalse(FichierASupprimer.objects.filter(name=chemin).exists())
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.DELETED).exists())

    def test_une_panne_du_stockage_est_reprise_plus_tard(self):
        piece = self.deposer()
        chemin = piece.file.name

        with mock.patch.object(
            default_storage, "delete", side_effect=OSError("MinIO injoignable")
        ), self.assertLogs("expenses.stockage", level="ERROR"), \
                self.captureOnCommitCallbacks(execute=True):
            response = self.retirer()

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(default_storage.exists(chemin))
        demande = FichierASupprimer.objects.get(name=chemin)
        self.assertIsNone(demande.deleted_at)
        self.assertEqual(demande.attempts, 1)
        self.assertIn("MinIO injoignable", demande.last_error)

        # Trop tôt : l'essai précédent pourrait encore être en cours.
        call_command("supprimer_fichiers", verbosity=0)
        self.assertTrue(default_storage.exists(chemin))

        FichierASupprimer.objects.filter(pk=demande.pk).update(
            attempted_at=timezone.now() - DELAI_DE_REPRISE - timedelta(seconds=1)
        )
        call_command("supprimer_fichiers", verbosity=0)

        self.assertFalse(default_storage.exists(chemin))
        demande.refresh_from_db()
        self.assertIsNotNone(demande.deleted_at)
        self.assertEqual(demande.attempts, 2)
        self.assertEqual(demande.last_error, "")

    def test_un_redemarrage_entre_le_commit_et_l_effacement_est_rattrape(self):
        """Le processus meurt après le commit, avant le rappel : la demande
        est en base, l'ordonnanceur l'exécute."""
        piece = self.deposer()
        chemin = piece.file.name
        self.retirer()  # rappels après commit non joués : le processus est « mort »
        self.assertTrue(default_storage.exists(chemin))

        call_command("supprimer_fichiers", verbosity=0)

        self.assertFalse(default_storage.exists(chemin))

    def test_les_essais_sont_bornes(self):
        piece = self.deposer()
        self.retirer()
        FichierASupprimer.objects.update(
            attempts=ESSAIS_MAX,
            attempted_at=timezone.now() - DELAI_DE_REPRISE - timedelta(seconds=1),
        )

        call_command("supprimer_fichiers", verbosity=0)

        self.assertTrue(default_storage.exists(piece.file.name))

    def test_un_fichier_encore_reference_n_est_jamais_efface(self):
        """Une demande qui viserait le fichier d'une fiche vivante est refusée
        et le dit : la fiche a raison sur la demande."""
        piece = self.deposer()
        FichierASupprimer.objects.create(name=piece.file.name)

        effaces, echecs = stockage.supprimer_les_fichiers()

        self.assertEqual((effaces, echecs), (0, 1))
        self.assertTrue(default_storage.exists(piece.file.name))
        self.assertIn("référence encore", FichierASupprimer.objects.get().last_error)


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


class TransactionExterieureTests(StockageTestCase):
    """Le fichier est écrit avant l'``INSERT`` et n'a pas de retour arrière :
    une transaction de vue annulée **après** la création réussie de la fiche
    ne doit pas laisser l'objet dans le stockage."""

    def _fichiers_du_dossier(self):
        try:
            _, fichiers = default_storage.listdir(
                f"justificatifs/{self.togo.pk}/{self.dossier.pk}"
            )
        except FileNotFoundError:
            return []
        return fichiers

    def test_une_trace_impossible_n_emporte_ni_la_fiche_ni_le_fichier(self):
        """La fiche est créée, puis la trace d'audit échoue : la transaction
        de la vue est annulée, la fiche disparaît — le fichier aussi."""
        with mock.patch(
            "expenses.views.record", side_effect=OSError("journal indisponible")
        ), self.assertRaises(OSError):
            self.client.post(
                "/api/proofs/",
                {"dossier": self.dossier.pk,
                 "file": SimpleUploadedFile("recu.pdf", PDF, content_type="application/pdf")},
                format="multipart",
            )

        self.assertEqual(Proof.objects.count(), 0)
        self.assertEqual(self._fichiers_du_dossier(), [])

    def test_un_depot_reussi_garde_son_fichier(self):
        """Le contraire : le chemin nominal ne doit rien effacer."""
        piece = self.deposer()

        self.assertTrue(default_storage.exists(piece.file.name))
        self.assertEqual(len(self._fichiers_du_dossier()), 1)


class RepriseObservableTests(StockageTestCase):
    def test_un_effacement_abandonne_est_signale(self):
        """Après ``ESSAIS_MAX``, la demande n'est plus reprise : la commande
        doit le dire — sinon le fichier reste et personne ne le sait."""
        from io import StringIO

        piece = self.deposer()
        self.retirer()
        FichierASupprimer.objects.update(attempts=ESSAIS_MAX)
        erreurs = StringIO()

        with self.assertLogs("expenses.management.commands.supprimer_fichiers", level="ERROR"):
            call_command("supprimer_fichiers", stderr=erreurs, verbosity=0)

        self.assertIn("n'ont pas pu être effacés", erreurs.getvalue())
        self.assertTrue(default_storage.exists(piece.file.name))


class TelechargementTests(StockageTestCase):
    def test_un_fichier_absent_ne_produit_pas_de_fausse_attestation(self):
        piece = self.deposer()
        default_storage.delete(piece.file.name)
        self.login(self.controller)

        with self.assertLogs("expenses.views", level="ERROR"):
            response = self.client.get(f"/api/proofs/{piece.pk}/download/")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["detail"].code, "fichier_introuvable")
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.DOWNLOADED).exists())

    def test_un_stockage_en_panne_ne_produit_pas_de_fausse_attestation(self):
        piece = self.deposer()
        self.login(self.controller)

        with mock.patch.object(
            default_storage, "open", side_effect=OSError("MinIO injoignable")
        ), self.assertLogs("expenses.views", level="ERROR"):
            response = self.client.get(f"/api/proofs/{piece.pk}/download/")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["detail"].code, "stockage_indisponible")
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.DOWNLOADED).exists())

    def test_un_fichier_servi_est_trace(self):
        piece = self.deposer()
        self.login(self.controller)

        response = self.client.get(f"/api/proofs/{piece.pk}/download/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), PDF)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.DOWNLOADED).exists())


class InventaireTests(StockageTestCase):
    def test_un_objet_sans_fiche_est_inventorie_sans_etre_efface(self):
        piece = self.deposer()
        egare = default_storage.save(
            f"justificatifs/{self.togo.pk}/{self.dossier.pk}/egare.pdf",
            SimpleUploadedFile("egare.pdf", PDF),
        )

        orphelins = stockage.pieces_orphelines(age_minimal=timedelta(0))

        self.assertEqual([chemin for chemin, _ in orphelins], [egare])
        self.assertTrue(default_storage.exists(egare))
        self.assertTrue(default_storage.exists(piece.file.name))

    def test_un_depot_en_cours_n_est_pas_un_orphelin(self):
        default_storage.save(
            f"justificatifs/{self.togo.pk}/{self.dossier.pk}/en-cours.pdf",
            SimpleUploadedFile("en-cours.pdf", PDF),
        )

        self.assertEqual(stockage.pieces_orphelines(age_minimal=timedelta(hours=24)), [])

    def test_une_demande_d_effacement_en_attente_n_est_pas_un_orphelin(self):
        piece = self.deposer()
        self.retirer()  # demande enregistrée, rappel non joué

        self.assertEqual(stockage.pieces_orphelines(age_minimal=timedelta(0)), [])
        self.assertTrue(default_storage.exists(piece.file.name))

    def test_la_commande_liste_sans_effacer(self):
        from io import StringIO

        egare = default_storage.save(
            f"justificatifs/{self.togo.pk}/{self.dossier.pk}/egare.pdf",
            SimpleUploadedFile("egare.pdf", PDF),
        )
        sortie = StringIO()

        call_command("pieces_orphelines", age=0, stdout=sortie)

        self.assertIn(egare, sortie.getvalue())
        self.assertIn("1 objet(s) sans fiche", sortie.getvalue())
        self.assertTrue(default_storage.exists(egare))
