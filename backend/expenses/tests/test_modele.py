"""Invariants posés en base : ce que les sérialiseurs garantissent, la base
le garantit aussi — un script ou l'admin ne passent pas par l'API."""

from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from budget.models import Budget
from core.models import Country, Manager, Team
from expenses.models import AuditLog, Dossier, Expense, Proof
from expenses.workflow import Status


class ContraintesTests(TestCase):
    def setUp(self):
        self.togo = Country.objects.create(
            name="Togo", code="TG", currency="XOF", timezone="Africa/Lome"
        )
        self.dossier = Dossier.objects.create(
            number="N-1", label="Mission", country=self.togo, date=date(2026, 3, 1)
        )
        self.budget = Budget.objects.create(
            country=self.togo, year=2026, amount=Decimal("1000.00")
        )

    def ligne(self, **kwargs):
        defaults = {
            "dossier": self.dossier, "country": self.togo,
            "date": timezone.now(), "title": "Carburant",
            "amount": Decimal("100.00"),
        }
        defaults.update(kwargs)
        with transaction.atomic():
            return Expense.objects.create(**defaults)

    def test_le_montant_justifie_ne_depasse_pas_la_depense(self):
        with self.assertRaises(IntegrityError):
            self.ligne(justified_amount=Decimal("100.01"))

    def test_les_montants_sont_positifs(self):
        with self.assertRaises(IntegrityError):
            self.ligne(amount=Decimal("-1.00"))
        with self.assertRaises(IntegrityError):
            self.ligne(justified_amount=Decimal("-1.00"))

    def test_la_devise_d_origine_est_tout_ou_rien(self):
        """Un montant sans devise, ou une conversion sans taux, ne se
        rapproche d'aucune pièce."""
        incoherents = (
            {"original_currency": "EUR"},
            {"original_amount": Decimal("10.00")},
            {"original_currency": "EUR", "original_amount": Decimal("10.00")},
            {"original_currency": "EUR", "original_rate": Decimal("655.957")},
        )
        for champs in incoherents:
            with self.subTest(champs=champs), self.assertRaises(IntegrityError):
                self.ligne(**champs)

        complete = self.ligne(
            original_currency="EUR", original_amount=Decimal("10.00"),
            original_rate=Decimal("655.957"),
        )
        self.assertIsNotNone(complete.pk)

    def test_une_depense_declaree_est_imputee(self):
        for statut in (
            Status.SUBMITTED, Status.IN_REVIEW, Status.JUSTIFIED,
            Status.UNJUSTIFIED, Status.CLOSED,
        ):
            with self.subTest(statut=statut), self.assertRaises(IntegrityError):
                self.ligne(status=statut)

        self.assertIsNotNone(self.ligne(status=Status.SUBMITTED, budget=self.budget).pk)
        self.assertIsNotNone(self.ligne(status=Status.DRAFT).pk)


class ProtectionTests(TestCase):
    """Rien ne se supprime : les clés étrangères protègent, elles ne
    cascadent pas et ne s'effacent pas en silence."""

    def setUp(self):
        self.togo = Country.objects.create(
            name="Togo", code="TG", currency="XOF", timezone="Africa/Lome"
        )
        self.equipe = Team.objects.create(country=self.togo, name="Lomé")
        self.manager = Manager.objects.create(name="Kodjo")
        self.dossier = Dossier.objects.create(
            number="N-1", label="Mission", country=self.togo,
            date=date(2026, 3, 1), team=self.equipe, owner=self.manager,
        )
        self.ligne = Expense.objects.create(
            dossier=self.dossier, country=self.togo, team=self.equipe,
            owner=self.manager, date=timezone.now(), title="Carburant",
            amount=Decimal("100.00"),
        )
        self.piece = Proof.objects.create(
            dossier=self.dossier, file="justificatifs/a.pdf", sha256="a" * 64
        )

    def test_un_dossier_ne_supprime_pas_ses_lignes_en_cascade(self):
        with self.assertRaises(ProtectedError):
            self.dossier.delete()
        self.assertTrue(Expense.objects.filter(pk=self.ligne.pk).exists())

    def test_le_referentiel_ne_s_efface_pas_sous_une_depense(self):
        with self.assertRaises(ProtectedError):
            self.equipe.delete()
        with self.assertRaises(ProtectedError):
            self.manager.delete()
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.team, self.equipe)

    def test_la_chaine_des_versions_ne_se_rompt_pas(self):
        Proof.objects.create(
            dossier=self.dossier, file="justificatifs/b.pdf", sha256="b" * 64,
            version=2, replaces=self.piece,
        )

        with self.assertRaises(ProtectedError):
            self.piece.delete()


class JournalTests(TestCase):
    def test_une_entree_sans_objet_est_acceptee(self):
        """Un export ne porte sur aucun objet précis : l'identifiant est nul.
        Les modules qui écrivent encore ``0`` restent acceptés."""
        nulle = AuditLog.objects.create(
            action=AuditLog.Action.DOWNLOADED, object_type="Export", object_id=None
        )
        zero = AuditLog.objects.create(
            action=AuditLog.Action.IMPORTED, object_type="ExpenseImport", object_id=0
        )

        self.assertIsNone(AuditLog.objects.get(pk=nulle.pk).object_id)
        self.assertEqual(AuditLog.objects.get(pk=zero.pk).object_id, 0)

    def test_l_ordre_est_stable(self):
        """Deux entrées écrites dans la même milliseconde n'auraient sinon pas
        d'ordre défini entre deux pages."""
        for modele in (AuditLog, Dossier, Expense, Proof):
            with self.subTest(modele=modele.__name__):
                self.assertEqual(modele._meta.ordering[-1], "-pk")
