"""Historique des mouvements budgétaires (§5.7)."""

from decimal import Decimal

from django.db.models import Max

from core.models import ChangeLog

from .test_budgets import BudgetTestCase


class BudgetHistoryTests(BudgetTestCase):
    def setUp(self):
        super().setUp()
        # Le journal est en ajout seul, jusque dans la base : on ignore ce
        # qui précède le test au lieu de l'effacer.
        self.repere = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
        self.login(self.doo)

    def entries(self, **filters):
        return ChangeLog.objects.filter(pk__gt=self.repere, **filters).order_by("id")

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

        # Celui qui a demandé ne décide pas : le siège tranche.
        self.login(self.siege)
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

        # Les enveloppes du décor ont déjà laissé leur création dans le
        # journal : seule l'entrée écrite par ce test compte.
        recentes = [e for e in response.data["results"] if e["id"] > self.repere]
        self.assertEqual(len(recentes), 1)
        self.assertEqual(recentes[0]["model_name_display"], "Enveloppe budgétaire")
        self.assertEqual(recentes[0]["action"], ChangeLog.Actions.UPDATED)


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
        repere = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
        self.login(self.doo)

        self.client.patch(
            f"/api/budgets/{self.budget_togo.pk}/", {"amount": "123456.00"}
        )

        entry = ChangeLog.objects.filter(
            pk__gt=repere, model_name=ChangeLog.Models.BUDGET
        ).get()
        self.assertEqual(entry.action, ChangeLog.Actions.UPDATED)
        self.assertEqual(entry.changed_fields, ["amount"])
        self.assertEqual(entry.performed_by, "do.innov")
