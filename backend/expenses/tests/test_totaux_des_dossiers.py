"""Totaux d'un dossier : sous-requêtes, jamais de GROUP BY (décision 130).

Un ``Count("proofs")`` par jointure ajoutait un GROUP BY où Django range
toutes les sous-requêtes des totaux : Postgres les recalculait alors pour
chaque pièce jointe au lieu d'une fois par dossier. Sur le banc à 60 000
lignes, la liste des dossiers et le tableau de bord dépassaient le délai de
15 s de la base ; une base de test, minuscule, ne le voyait pas.
"""

from decimal import Decimal

from expenses.models import Dossier, Proof

from .base import ExpenseTestCase


class TotauxDesDossiersTests(ExpenseTestCase):
    def _piece(self, statut, ligne=None):
        return Proof.objects.create(
            dossier=self.dossier, expense=ligne, file="justificatifs/f.pdf",
            original_name="facture.pdf", sha256=f"{statut[:1]}{Proof.objects.count():063d}",
            status=statut,
        )

    def test_les_totaux_ne_regroupent_pas(self):
        """Aucun agrégat sur la requête principale : rien à regrouper."""
        self.assertIsNone(Dossier.objects.with_totals().query.group_by)

    def test_les_pieces_se_comptent_sans_multiplier_les_montants(self):
        premiere = self.make_expense(amount="1000.00")
        self.make_expense(amount="500.00")
        self._piece(Proof.ProofStatus.RECEIVED, premiere)
        self._piece(Proof.ProofStatus.REJECTED, premiere)
        self._piece(Proof.ProofStatus.INCOMPLETE)

        dossier = Dossier.objects.with_totals().get(pk=self.dossier.pk)

        self.assertEqual(dossier.total_amount, Decimal("1500.00"))
        self.assertEqual(dossier.total_lines, 2)
        self.assertEqual(dossier.total_proofs, 3)
        self.assertEqual(dossier.usable_proofs, 2)

    def test_un_dossier_sans_piece_compte_zero(self):
        dossier = Dossier.objects.with_totals().get(pk=self.dossier.pk)

        self.assertEqual((dossier.total_proofs, dossier.usable_proofs), (0, 0))
