"""Suppression d'une enveloppe qui n'a jamais servi (décision 91).

Rien ne se supprime, hors brouillon — et hors enveloppe jamais servie, qui
n'a pas plus de valeur probante qu'un brouillon jamais soumis. Dès qu'une
dépense y est imputée, qu'une réallocation la touche ou qu'une
sous-enveloppe la découpe, elle se désactive et ne disparaît pas. Seule la
direction supprime, comme elle seule attribue.
"""

from decimal import Decimal

from django.utils import timezone
from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.models import Budget, BudgetReallocation
from core.models import ChangeLog, Team

from .test_budgets import BudgetTestCase


class SuppressionTests(BudgetTestCase):
    def setUp(self):
        super().setUp()
        self.equipe = Team.objects.create(country=self.togo, name="Équipe Lomé")
        self.vierge = Budget.objects.create(
            country=self.togo, year=2027, amount=Decimal("1000.00")
        )

    def supprimer(self, budget, user=None):
        self.login(user or self.siege)
        return self.client.delete(f"/api/budgets/{budget.pk}/")

    def can_delete(self, budget, user=None):
        self.login(user or self.siege)
        return self.client.get(f"/api/budgets/{budget.pk}/").data["can_delete"]

    def test_la_direction_supprime_une_enveloppe_vierge_et_la_trace_reste(self):
        self.assertTrue(self.can_delete(self.vierge))

        response = self.supprimer(self.vierge)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Budget.objects.filter(pk=self.vierge.pk).exists())
        trace = ChangeLog.objects.get(
            model_name=ChangeLog.Models.BUDGET, object_id=self.vierge.pk,
            action=ChangeLog.Actions.DELETED,
        )
        self.assertEqual(trace.performed_by, self.siege.username)
        self.assertEqual(trace.country, self.togo)

    def test_ni_l_administrateur_ni_le_pays_ne_suppriment(self):
        """L'administrateur lit les enveloppes, le pays ne fixe pas les
        siennes : aucun des deux ne les retire."""
        for compte in (make_user("rh.innov", Role.ADMIN), self.rep_togo):
            with self.subTest(role=compte.profile.role):
                self.assertFalse(self.can_delete(self.vierge, compte))
                response = self.supprimer(self.vierge, compte)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Budget.objects.filter(pk=self.vierge.pk).exists())

    def test_une_enveloppe_qui_porte_une_depense_se_garde(self):
        self.imputer(self.vierge, "100.00")

        self.assertFalse(self.can_delete(self.vierge))
        response = self.supprimer(self.vierge)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("désactive", str(response.data["budget"]))
        self.assertTrue(Budget.objects.filter(pk=self.vierge.pk).exists())

    def test_une_enveloppe_touchee_par_une_reallocation_se_garde(self):
        """Même refusée, une réallocation dit qu'on a voulu bouger cet
        argent : sa trace pointe l'enveloppe, qui doit rester."""
        sous = Budget.objects.create(
            country=self.togo, year=2027, team=self.equipe, amount=Decimal("0.00")
        )
        BudgetReallocation.objects.create(
            source=self.vierge, target=sous, amount=Decimal("10.00"),
            reason="Renfort", requested_by=self.siege.username,
            status=BudgetReallocation.Status.REJECTED,
            decided_by=self.doo.username, decided_at=timezone.now(),
            decision_note="Pas maintenant.",
        )

        for budget in (self.vierge, sous):
            with self.subTest(budget=budget.scope_kind):
                self.assertFalse(self.can_delete(budget))
                response = self.supprimer(budget)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("réallocation", str(response.data["budget"]))

    def test_une_enveloppe_de_pays_garde_ses_sous_enveloppes(self):
        """On retire d'abord le détail, puis l'enveloppe du pays."""
        sous = Budget.objects.create(
            country=self.togo, year=2027, team=self.equipe, amount=Decimal("100.00")
        )

        refus = self.supprimer(self.vierge)
        self.assertEqual(refus.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sous-enveloppes", str(refus.data["budget"]))

        self.assertEqual(self.supprimer(sous).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.supprimer(self.vierge).status_code, status.HTTP_204_NO_CONTENT)

    def test_la_liste_dit_ce_qui_se_supprime(self):
        """Le même prédicat dans la liste que dans la route : l'interface
        n'affiche « Supprimer » que là où le serveur l'accepterait."""
        self.imputer(self.budget_togo, "100.00")
        self.login(self.siege)

        liste = self.client.get("/api/budgets/", {"country": self.togo.pk}).data["results"]

        par_id = {b["id"]: b["can_delete"] for b in liste}
        self.assertTrue(par_id[self.vierge.pk])
        self.assertFalse(par_id[self.budget_togo.pk])
