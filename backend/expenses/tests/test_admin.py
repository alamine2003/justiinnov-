"""L'admin Django ne permet pas ce que l'API interdit."""

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from expenses.models import AuditLog, Dossier, Expense, Proof


class AdminTests(TestCase):
    def setUp(self):
        self.requete = RequestFactory().get("/admin/")
        self.requete.user = User.objects.create_superuser(
            "root", "root@example.org", "Motdepasse-2026-test"
        )

    def test_rien_ne_se_supprime_depuis_l_admin(self):
        """Même un superutilisateur : l'admin effacerait sans trace ce que
        l'API sait retirer en journalisant."""
        for modele in (Expense, Dossier, Proof, AuditLog):
            with self.subTest(modele=modele.__name__):
                self.assertFalse(
                    admin.site._registry[modele].has_delete_permission(self.requete)
                )

    def test_ce_que_le_circuit_fixe_ne_se_retouche_pas(self):
        readonly = admin.site._registry[Expense].get_readonly_fields(self.requete)

        for champ in ("status", "amount", "justified_amount", "budget", "created_by"):
            with self.subTest(champ=champ):
                self.assertIn(champ, readonly)

    def test_une_ligne_declaree_ne_se_retouche_pas_depuis_l_admin(self):
        """L'API refuse de modifier une ligne soumise ; l'admin laissait
        changer sa date, son équipe ou son dossier sans trace."""
        from datetime import date
        from decimal import Decimal

        from django.utils import timezone

        from budget.models import Budget
        from core.models import Country
        from core.statuts import Status

        togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02", currency="XOF", timezone="Africa/Lome",
        )
        dossier = Dossier.objects.create(number="N-1", label="Mission", country=togo, date=date(2026, 3, 1))
        brouillon = Expense.objects.create(
            dossier=dossier, country=togo, date=timezone.now(), title="Carburant", amount=Decimal("10"),
        )
        piece = Proof.objects.create(dossier=dossier, file="justificatifs/f.pdf", original_name="f.pdf", sha256="a" * 64)
        lignes, dossiers, pieces = (admin.site._registry[m] for m in (Expense, Dossier, Proof))

        self.assertTrue(lignes.has_change_permission(self.requete, brouillon))
        self.assertTrue(dossiers.has_change_permission(self.requete, dossier))
        self.assertTrue(pieces.has_change_permission(self.requete, piece))
        for champ in ("file", "dossier", "original_name", "sha256"):
            self.assertIn(champ, pieces.get_readonly_fields(self.requete, piece), champ)

        enveloppe = Budget.objects.create(country=togo, year=2026, amount=Decimal("1000"))
        Dossier.objects.filter(pk=dossier.pk).update(status=Status.SUBMITTED)
        Expense.objects.filter(pk=brouillon.pk).update(status=Status.SUBMITTED, budget=enveloppe)
        dossier.refresh_from_db(); brouillon.refresh_from_db(); piece.refresh_from_db()

        self.assertFalse(lignes.has_change_permission(self.requete, brouillon))
        self.assertFalse(dossiers.has_change_permission(self.requete, dossier))
        self.assertFalse(pieces.has_change_permission(self.requete, piece))
        # La liste, elle, reste consultable.
        self.assertTrue(lignes.has_change_permission(self.requete))

    def test_un_beneficiaire_ne_se_supprime_pas_depuis_l_admin(self):
        from expenses.models import Beneficiary

        self.assertFalse(admin.site._registry[Beneficiary].has_delete_permission(self.requete))

    def test_le_journal_se_lit_sans_s_ecrire(self):
        journal = admin.site._registry[AuditLog]

        self.assertFalse(journal.has_add_permission(self.requete))
        self.assertFalse(journal.has_change_permission(self.requete))
        self.assertFalse(journal.has_delete_permission(self.requete))
        self.assertEqual(
            set(journal.get_readonly_fields(self.requete)),
            {f.name for f in AuditLog._meta.fields},
        )
