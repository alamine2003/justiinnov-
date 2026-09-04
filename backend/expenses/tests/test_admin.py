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

    def test_le_journal_se_lit_sans_s_ecrire(self):
        journal = admin.site._registry[AuditLog]

        self.assertFalse(journal.has_add_permission(self.requete))
        self.assertFalse(journal.has_change_permission(self.requete))
        self.assertFalse(journal.has_delete_permission(self.requete))
        self.assertEqual(
            set(journal.get_readonly_fields(self.requete)),
            {f.name for f in AuditLog._meta.fields},
        )
