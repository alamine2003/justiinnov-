"""Les services de saisie et de dépôt, sans HTTP (décision 125).

Les vues ne portent plus que le HTTP : ces services sont ce qu'un import ou
une commande appelleraient. On les éprouve directement — refus métier, et
non réponses DRF.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from rest_framework.exceptions import ValidationError

from accounts.models import Role
from accounts.permissions import get_access
from accounts.tests.test_scoping import make_user
from core.regles import PermissionRefusee, RegleViolee, traduire_les_regles
from core.statuts import Status
from expenses import pieces, transitions
from expenses.models import Dossier, Proof

from .base import ExpenseTestCase, in_memory_storage

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"


@in_memory_storage
class ServicesDeSaisieTests(ExpenseTestCase):
    def setUp(self):
        self.auteur = get_access(self.owner)
        self.collegue = get_access(
            make_user("collegue.togo", Role.MANAGER, [self.togo])
        )

    def test_l_ajout_verrouille_et_rend_le_dossier(self):
        with transaction.atomic():
            dossier = transitions.preparer_l_ajout(self.dossier, self.auteur)
        self.assertEqual(dossier.pk, self.dossier.pk)

    def test_l_ajout_dans_le_brouillon_d_un_collegue_est_refuse(self):
        with transaction.atomic(), self.assertRaises(PermissionRefusee):
            transitions.preparer_l_ajout(self.dossier, self.collegue)

    def test_l_ajout_dans_un_dossier_declare_est_refuse(self):
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.SUBMITTED)
        with transaction.atomic(), self.assertRaises(RegleViolee):
            transitions.preparer_l_ajout(self.dossier, self.auteur)

    def test_une_ligne_qui_porte_une_piece_ne_change_plus_de_dossier(self):
        ligne = self.ligne_de_preuve()
        Proof.objects.create(
            dossier=self.dossier, expense=ligne, kind="invoice", sha256="a" * 64,
            file=SimpleUploadedFile("recu.pdf", PDF), original_name="recu.pdf",
        )
        autre = Dossier.objects.create(
            number="N-0002", label="Autre", country=self.togo, project=self.projet,
            team=self.team, date=self.dossier.date, created_by=self.owner.username,
        )
        with transaction.atomic(), self.assertRaises(RegleViolee) as refus:
            transitions.preparer_la_modification(ligne, autre, self.auteur)
        self.assertEqual(refus.exception.champ, "dossier")

    def test_la_modification_rend_la_ligne_relue_sous_verrou(self):
        ligne = self.ligne_de_preuve()
        with transaction.atomic():
            relue = transitions.preparer_la_modification(ligne, None, self.auteur)
        self.assertEqual(relue.pk, ligne.pk)

    def test_le_depot_dans_un_dossier_cloture_est_refuse_sans_champ(self):
        ligne = self.ligne_de_preuve()
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.CLOSED)
        with transaction.atomic(), self.assertRaises(RegleViolee) as refus:
            pieces.preparer_le_depot(self.dossier, ligne)
        self.assertIsNone(refus.exception.champ)

    def test_le_depot_rend_la_version_suivante_d_une_piece_remplacee(self):
        ligne = self.ligne_de_preuve()
        ancienne = Proof.objects.create(
            dossier=self.dossier, expense=ligne, kind="invoice", sha256="b" * 64,
            file=SimpleUploadedFile("recu.pdf", PDF), original_name="recu.pdf", version=2,
        )
        with transaction.atomic():
            depot = pieces.preparer_le_depot(self.dossier, ligne, ancienne)
        self.assertEqual(depot.version, 3)

    def test_une_piece_d_une_autre_ligne_ne_se_remplace_pas_ici(self):
        ligne = self.ligne_de_preuve()
        autre_ligne = self.make_expense()
        ancienne = Proof.objects.create(
            dossier=self.dossier, expense=autre_ligne, kind="invoice", sha256="c" * 64,
            file=SimpleUploadedFile("recu.pdf", PDF), original_name="recu.pdf",
        )
        with self.assertRaises(RegleViolee) as refus:
            pieces.verifier_le_remplacement(ancienne, self.dossier, ligne)
        self.assertEqual(refus.exception.champ, "replaces")


class TraductionDesReglesTests(ExpenseTestCase):
    def test_un_refus_sans_champ_rend_la_liste_nue(self):
        """La forme d'une erreur de validation DRF sans champ."""
        with self.assertRaises(ValidationError) as erreur, traduire_les_regles():
            raise RegleViolee(None, "Refusé.")
        self.assertEqual(erreur.exception.detail, ["Refusé."])

    def test_un_refus_sur_un_champ_le_nomme(self):
        with self.assertRaises(ValidationError) as erreur, traduire_les_regles():
            raise RegleViolee("dossier", "Refusé.")
        self.assertEqual(erreur.exception.detail, {"dossier": ["Refusé."]})
