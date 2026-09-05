"""Cloisonnement par équipe des rapports, des alertes et de leurs notifications.

Un manager rattaché à des équipes ne voit que les leurs dans l'application ;
la répartition, le tableau de bord et les alertes notifiées doivent suivre
la même règle, sans quoi le rapport laisse fuir ce que la liste cache.
"""

from datetime import date
from decimal import Decimal

from django.core.management import call_command
from rest_framework import status

from accounts.models import Role
from accounts.permissions import get_access
from accounts.tests.test_scoping import make_user
from core.models import Team
from expenses.models import Dossier
from expenses.tests.base import ExpenseTestCase
from expenses.workflow import Status
from notifications.models import Notification
from reporting.scope import querysets_pour


class EquipeTestCase(ExpenseTestCase):
    """Deux équipes au Togo, un manager restreint à Lomé, un dossier par équipe.

    Les deux dossiers sont engagés sans preuve ; celui de Kara fait déborder
    l'enveloppe du pays, qui se lit par pays entier.
    """

    dossier_status = Status.SUBMITTED

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.kara = Team.objects.create(country=cls.togo, name="Équipe Kara")
        cls.manager_lome = make_user(
            "lome.togo", Role.MANAGER, [cls.togo], teams=[cls.team]
        )
        cls.ligne_lome = cls.make_expense(
            cls, amount="100000.00", status=Status.SUBMITTED, budget=cls.budget
        )
        cls.dossier_kara = Dossier.objects.create(
            number="N-KARA", label="Tournée de Kara", country=cls.togo,
            team=cls.kara, owner=cls.manager, date=date(cls.year, 4, 1),
            status=Status.SUBMITTED, created_by=cls.owner.username,
        )
        cls.ligne_kara = cls.make_expense(
            cls, dossier=cls.dossier_kara, team=cls.kara, amount="950000.00",
            status=Status.SUBMITTED, budget=cls.budget,
        )


class QuerysetsTests(EquipeTestCase):
    def test_dossiers_et_lignes_sont_restreints_aux_equipes(self):
        budgets, dossiers, expenses = querysets_pour(
            get_access(self.manager_lome), self.year
        )

        self.assertEqual(set(dossiers.values_list("number", flat=True)), {"N-0001"})
        self.assertEqual(set(expenses.values_list("team__name", flat=True)), {"Équipe Lomé"})
        # L'enveloppe reste celle du pays : le manager doit savoir où elle en est.
        self.assertIn(self.budget, budgets)

    def test_un_manager_sans_equipe_voit_tout_son_pays(self):
        _, dossiers, _ = querysets_pour(get_access(self.owner), self.year)

        self.assertEqual(
            set(dossiers.values_list("number", flat=True)), {"N-0001", "N-KARA"}
        )


class RepartitionTests(EquipeTestCase):
    def test_la_repartition_par_equipe_ne_montre_que_les_siennes(self):
        self.login(self.manager_lome)

        response = self.client.get("/api/dashboard/breakdown/", {"year": self.year})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        equipes = {row["label"] for row in response.data["by_team"]}
        self.assertEqual(equipes, {"Équipe Lomé"})


class TableauDeBordTests(EquipeTestCase):
    def test_les_alertes_et_la_charge_suivent_les_equipes(self):
        self.login(self.manager_lome)

        response = self.client.get("/api/dashboard/", {"year": self.year})

        liens = {alerte["link"] for alerte in response.data["alerts"]}
        self.assertIn(f"/dossiers/{self.dossier.pk}", liens)
        self.assertNotIn(f"/dossiers/{self.dossier_kara.pk}", liens)
        # L'enveloppe déborde à cause de Kara : l'alerte se lit quand même,
        # elle porte sur le pays.
        self.assertIn("budget_overrun", {a["kind"] for a in response.data["alerts"]})
        self.assertEqual(response.data["workload"]["expenses_to_review"], 1)
        self.assertEqual(response.data["workload"]["dossiers_open"], 1)


class NotificationsTests(EquipeTestCase):
    def _liens(self, user):
        return set(
            Notification.objects.filter(recipient=user).values_list("link", flat=True)
        )

    def test_un_manager_cloisonne_n_est_pas_prevenu_pour_kara(self):
        call_command("notify_alerts", year=self.year, verbosity=0)

        liens = self._liens(self.manager_lome)
        self.assertIn(f"/dossiers/{self.dossier.pk}", liens)
        self.assertNotIn(f"/dossiers/{self.dossier_kara.pk}", liens)
        # L'alerte d'enveloppe reste par pays : il la reçoit.
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.manager_lome, kind=Notification.Kind.BUDGET_OVERRUN
            ).exists()
        )

    def test_un_manager_sans_equipe_est_prevenu_de_tout_son_pays(self):
        call_command("notify_alerts", year=self.year, verbosity=0)

        liens = self._liens(self.owner)
        self.assertIn(f"/dossiers/{self.dossier.pk}", liens)
        self.assertIn(f"/dossiers/{self.dossier_kara.pk}", liens)

    def test_le_siege_est_prevenu_de_tout(self):
        call_command("notify_alerts", year=self.year, verbosity=0)

        self.assertIn(f"/dossiers/{self.dossier_kara.pk}", self._liens(self.controller))

    def test_les_montants_restent_ceux_du_pays(self):
        """Le cloisonnement ne change pas les chiffres de l'enveloppe."""
        budgets = querysets_pour(get_access(self.manager_lome), self.year)[0]

        self.assertEqual(budgets.get(pk=self.budget.pk).amount, Decimal("1000000.00"))
