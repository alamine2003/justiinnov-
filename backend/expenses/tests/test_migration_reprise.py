"""Reprise des données par la migration 0007, avant la pose des contraintes.

Une base en service peut porter des lignes que les nouvelles contraintes
refusent : une dépense déclarée sans enveloppe, une devise d'origine sans
taux. Sans reprise, la migration échoue et bloque tout déploiement. Le test
remonte la base à l'état précédent, y dépose ces lignes, puis rejoue la
migration.
"""

from datetime import date, datetime, timezone as tz
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

AVANT = [("expenses", "0006_auditlog_imported"), ("budget", "0004_controle_et_integrite")]
APRES = [("expenses", "0007_controle_et_integrite")]


class RepriseDesDonneesTests(TransactionTestCase):
    def _migrer(self, cible):
        executor = MigrationExecutor(connection)
        executor.migrate(cible)
        executor.loader.build_graph()
        return executor.loader.project_state(cible).apps

    def _peupler(self, apps):
        Country = apps.get_model("core", "Country")
        Dossier = apps.get_model("expenses", "Dossier")
        Expense = apps.get_model("expenses", "Expense")
        Budget = apps.get_model("budget", "Budget")

        togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-01", currency="XOF",
            timezone="Africa/Lome",
        )
        kenya = Country.objects.create(
            name="Djibouti", code="DJ", country_ref="DJ-01", currency="DJF",
            timezone="Africa/Djibouti",
        )
        Budget.objects.create(country=togo, year=2026, amount=Decimal("1000.00"))
        dossier_togo = Dossier.objects.create(
            number="N-1", label="Mission", country=togo, date=date(2026, 3, 1),
            status="submitted",
        )
        dossier_kenya = Dossier.objects.create(
            number="N-2", label="Mission", country=kenya, date=date(2026, 3, 1),
            status="submitted",
        )
        quand = datetime(2026, 3, 1, 12, tzinfo=tz.utc)
        sans_enveloppe = Expense.objects.create(
            dossier=dossier_togo, country=togo, date=quand, title="Taxi",
            amount=Decimal("100.00"), status="submitted",
        )
        sans_aucune_enveloppe = Expense.objects.create(
            dossier=dossier_kenya, country=kenya, date=quand, title="Hôtel",
            amount=Decimal("300.00"), status="justified",
        )
        sans_taux = Expense.objects.create(
            dossier=dossier_togo, country=togo, date=quand, title="Billet",
            amount=Decimal("655.96"), status="draft",
            original_currency="EUR", original_amount=Decimal("1.00"),
        )
        sans_montant = Expense.objects.create(
            dossier=dossier_togo, country=togo, date=quand, title="Repas",
            amount=Decimal("50.00"), status="draft", original_currency="EUR",
        )
        return sans_enveloppe.pk, sans_aucune_enveloppe.pk, sans_taux.pk, sans_montant.pk

    def test_la_migration_rattache_et_complete_avant_de_contraindre(self):
        apps = self._migrer(AVANT)
        try:
            pk_togo, pk_kenya, pk_taux, pk_montant = self._peupler(apps)
            apps = self._migrer(APRES)
            Expense = apps.get_model("expenses", "Expense")
            Budget = apps.get_model("budget", "Budget")

            togo = Expense.objects.get(pk=pk_togo)
            self.assertEqual(togo.budget.amount, Decimal("1000.00"))

            kenya = Expense.objects.get(pk=pk_kenya)
            self.assertIsNotNone(kenya.budget_id)
            self.assertEqual(kenya.budget.amount, Decimal("0.00"))
            self.assertEqual(Budget.objects.filter(country__code="DJ").count(), 1)

            taux = Expense.objects.get(pk=pk_taux)
            self.assertEqual(taux.original_rate, Decimal("655.960000"))

            montant = Expense.objects.get(pk=pk_montant)
            self.assertEqual(montant.original_currency, "")
            self.assertIn("EUR", montant.note)
        finally:
            # Les autres tests attendent la base au dernier état.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
