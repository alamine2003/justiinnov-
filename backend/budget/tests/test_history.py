"""Historique des mouvements budgétaires (§5.7)."""

from decimal import Decimal

from core.models import ChangeLog

from .test_budgets import BudgetTestCase


class BudgetHistoryTests(BudgetTestCase):
    def setUp(self):
        super().setUp()
        ChangeLog.objects.all().delete()
        self.login(self.doo)

    def entries(self, **filters):
        return ChangeLog.objects.filter(**filters).order_by("id")

    def test_reduire_une_enveloppe_laisse_une_trace(self):
        """Régression : une enveloppe pouvait passer de 8 M à 400 000 sans que
        rien ne l'enregistre."""
        self.client.patch(
            f"/api/budgets/{self.budget_togo.pk}/", {"amount": "400000.00"}
        )

        entry = self.entries(model_name=ChangeLog.Models.BUDGET).get()
        self.assertEqual(entry.action, ChangeLog.Actions.UPDATED)
        self.assertEqual(entry.changed_fields, ["amount"])
        self.assertEqual(entry.performed_by, "do.innov")
        self.assertEqual(entry.country, self.togo)

    def test_creation_d_enveloppe_journalisee(self):
        self.client.post(
            "/api/budgets/",
            {"country": self.togo.pk, "year": 2030, "amount": "1000.00"},
        )

        entry = self.entries(
            model_name=ChangeLog.Models.BUDGET,
            action=ChangeLog.Actions.CREATED,
        ).get()
        self.assertEqual(entry.country, self.togo)

    def test_reallocation_rattachee_au_pays_de_la_source(self):
        """Une réallocation n'a pas de champ « pays » : sans résolveur, elle
        serait invisible dans l'historique du pays."""
        from core.models import Project

        projet = Project.objects.create(country=self.togo, name="Projet")
        cible = self.client.post(
            "/api/budgets/",
            {
                "country": self.togo.pk, "year": self.budget_togo.year,
                "project": projet.pk, "amount": "0.00",
            },
        ).data["id"]

        self.client.post(
            "/api/reallocations/",
            {
                "source": self.budget_togo.pk, "target": cible,
                "amount": "1000.00", "reason": "Renfort",
            },
        )

        entry = self.entries(model_name=ChangeLog.Models.REALLOCATION).first()
        self.assertEqual(entry.country, self.togo)
        self.assertEqual(entry.action, ChangeLog.Actions.CREATED)

    def test_approbation_journalise_le_transfert(self):
        from core.models import Project

        projet = Project.objects.create(country=self.togo, name="Projet")
        cible = self.client.post(
            "/api/budgets/",
            {
                "country": self.togo.pk, "year": self.budget_togo.year,
                "project": projet.pk, "amount": "0.00",
            },
        ).data["id"]
        realloc = self.client.post(
            "/api/reallocations/",
            {
                "source": self.budget_togo.pk, "target": cible,
                "amount": "1000000.00", "reason": "Renfort",
            },
        ).data["id"]

        self.client.post(f"/api/reallocations/{realloc}/approve/")

        montants = self.entries(
            model_name=ChangeLog.Models.BUDGET,
            action=ChangeLog.Actions.UPDATED,
        )
        # Les deux enveloppes touchées par le transfert sont tracées.
        self.assertEqual(montants.count(), 2)
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("9000000.00"))

    def test_historique_visible_dans_l_api(self):
        self.client.patch(
            f"/api/budgets/{self.budget_togo.pk}/", {"amount": "400000.00"}
        )

        response = self.client.get("/api/history/", {"model_name": "budget"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["model_name_display"], "Enveloppe budgétaire"
        )


class SignalDurabilityTests(BudgetTestCase):
    """Les journaux ne doivent pas dépendre du ramasse-miettes.

    Django ne garde qu'une référence faible sur ses receivers. Les journaux
    des applications branchées par ``core.signals.register`` étaient posés
    avec des ``partial`` que rien d'autre ne référençait : le GC les
    emportait, et une enveloppe pouvait être réduite de plusieurs millions
    sans laisser la moindre trace. Le défaut était intermittent — il ne se
    voyait qu'en intégration continue.
    """

    def test_le_journal_survit_a_un_ramasse_miettes(self):
        import gc

        gc.collect()
        ChangeLog.objects.all().delete()
        self.login(self.doo)

        self.client.patch(
            f"/api/budgets/{self.budget_togo.pk}/", {"amount": "123456.00"}
        )

        entry = ChangeLog.objects.filter(model_name=ChangeLog.Models.BUDGET).get()
        self.assertEqual(entry.action, ChangeLog.Actions.UPDATED)
        self.assertEqual(entry.changed_fields, ["amount"])
        self.assertEqual(entry.performed_by, "do.innov")
