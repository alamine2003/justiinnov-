"""Le coût des listes ne doit pas croître avec le nombre de lignes."""

from datetime import date
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from budget.models import Budget
from core.models import Project
from expenses.models import Dossier, Expense

from .base import ExpenseTestCase, in_memory_storage


@in_memory_storage
class QueryCountTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.doo)

    def _make_dossiers(self, count, offset=0):
        for index in range(offset, offset + count):
            dossier = Dossier.objects.create(
                number=f"Q-{index:03d}",
                label=f"Dossier {index}",
                country=self.togo,
                date=date(self.year, 2, 1),
            )
            for line in range(2):
                Expense.objects.create(
                    dossier=dossier,
                    country=self.togo,
                    date=f"{self.year}-02-01T10:00:00Z",
                    title=f"Ligne {line}",
                    amount=Decimal("1000.00"),
                )

    def _count_queries(self, url):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(captured.captured_queries)

    def test_la_liste_des_dossiers_ne_depend_pas_du_nombre_de_dossiers(self):
        """Sans annotations préparées, chaque dossier coûtait trois requêtes
        supplémentaires (totaux, lignes, preuves)."""
        self._make_dossiers(3)
        few = self._count_queries("/api/dossiers/")

        self._make_dossiers(12, offset=3)
        many = self._count_queries("/api/dossiers/")

        self.assertEqual(few, many)

    def test_la_liste_des_budgets_ne_depend_pas_du_nombre_d_enveloppes(self):
        few = self._count_queries("/api/budgets/")

        for index in range(10):
            projet = Project.objects.create(country=self.togo, name=f"Projet {index}")
            Budget.objects.create(
                country=self.togo,
                year=self.year,
                project=projet,
                amount=Decimal("1000.00"),
            )
        many = self._count_queries("/api/budgets/")

        self.assertEqual(few, many)

    def test_le_detail_ne_depend_pas_du_nombre_de_lignes(self):
        for index in range(2):
            Expense.objects.create(
                dossier=self.dossier, country=self.togo, team=self.team,
                owner=self.manager, date=f"{self.year}-02-01T10:00:00Z",
                title=f"Ligne {index}", amount=Decimal("100.00"),
            )
        few = self._count_queries(f"/api/dossiers/{self.dossier.pk}/")

        for index in range(2, 12):
            Expense.objects.create(
                dossier=self.dossier, country=self.togo, team=self.team,
                owner=self.manager, date=f"{self.year}-02-01T10:00:00Z",
                title=f"Ligne {index}", amount=Decimal("100.00"),
            )
        many = self._count_queries(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(few, many)

    def test_les_totaux_restent_justes_avec_plusieurs_preuves(self):
        """Régression : agréger les montants en joignant aussi les preuves
        les multiplierait par le nombre de preuves du dossier."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from expenses.models import Proof

        Expense.objects.create(
            dossier=self.dossier, country=self.togo,
            date=f"{self.year}-02-01T10:00:00Z", title="Unique",
            amount=Decimal("100.00"), justified_amount=Decimal("60.00"),
        )
        for index in range(3):
            Proof.objects.create(
                dossier=self.dossier,
                file=SimpleUploadedFile(f"p{index}.pdf", b"x"),
                sha256=f"{index:064d}",
            )

        response = self.client.get(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.data["totals"]["amount"], "100.00")
        self.assertEqual(response.data["totals"]["gap"], "40.00")
        self.assertEqual(response.data["proof_count"], 3)
        self.assertEqual(response.data["expense_count"], 1)
