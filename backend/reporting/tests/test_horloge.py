"""Une seule horloge : celle du pays dont on lit les lignes.

Une dépense faite à Djibouti (UTC+3) le 1er janvier à 01:00 est encore au
31 décembre en UTC. Elle relève du nouvel exercice — c'est là qu'elle est
imputée — et doit se lire ainsi dans l'export, la répartition et l'import.
"""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from rest_framework import status

from accounts.models import Role
from accounts.permissions import Access
from budget.models import Budget
from core.models import Country, Team
from expenses.models import Dossier, Expense
from expenses.tests.base import ExpenseTestCase
from expenses.workflow import Status
from reporting.exports import EXPENSE_COLUMNS, XLSX
from reporting.scope import UTC, bornes_periode, fuseau_du_perimetre

DJIBOUTI = ZoneInfo("Africa/Djibouti")


class HorlogeTestCase(ExpenseTestCase):
    """Un dossier ouvert le 31 décembre, dont la ligne est datée du 1er janvier
    à 01:00, heure de Djibouti."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.djibouti = Country.objects.create(
            name="Djibouti", code="DJ", country_ref="DJ-03",
            currency="DJF", timezone="Africa/Djibouti",
        )
        cls.suivant = cls.year + 1
        cls.budget_dj = Budget.objects.create(
            country=cls.djibouti, year=cls.suivant, amount=Decimal("1000000.00")
        )
        cls.equipe_dj = Team.objects.create(country=cls.djibouti, name="Équipe Djibouti")
        cls.dossier_dj = Dossier.objects.create(
            number="DJ-0001", label="Nuit de la Saint-Sylvestre", country=cls.djibouti,
            team=cls.equipe_dj, owner=cls.manager, date=date(cls.year, 12, 31),
            status=Status.SUBMITTED, created_by=cls.owner.username,
        )
        cls.ligne = cls.make_expense(
            cls, dossier=cls.dossier_dj, country=cls.djibouti, team=cls.equipe_dj,
            status=Status.SUBMITTED, budget=cls.budget_dj, title="Taxi de nuit",
            date=datetime(cls.suivant, 1, 1, 1, 0, tzinfo=DJIBOUTI),
        )


class BornesTests(HorlogeTestCase):
    def test_les_bornes_suivent_le_fuseau_recu(self):
        _, (debut, fin) = bornes_periode(self.suivant, tz=DJIBOUTI)

        self.assertEqual(debut, datetime(self.suivant, 1, 1, 0, 0, tzinfo=DJIBOUTI))
        self.assertEqual(
            debut.astimezone(UTC), datetime(self.year, 12, 31, 21, 0, tzinfo=UTC)
        )
        self.assertEqual(fin.year, self.suivant)

    def test_sans_fuseau_les_bornes_sont_en_utc(self):
        _, (debut, _fin) = bornes_periode(self.suivant)

        self.assertEqual(debut.utcoffset().total_seconds(), 0)

    def test_le_fuseau_du_perimetre(self):
        siege = Access(role=Role.SUPER_ADMIN, country_ids=None)
        djiboutien = Access(role=Role.MANAGER, country_ids=[self.djibouti.pk])
        deux_pays = Access(role=Role.DF, country_ids=[self.togo.pk, self.djibouti.pk])

        # Plusieurs pays lus ensemble : aucune horloge nationale ne s'impose.
        self.assertIs(fuseau_du_perimetre(siege), UTC)
        self.assertIs(fuseau_du_perimetre(deux_pays), UTC)
        # Un seul pays visé, nommé ou seul du périmètre : son heure.
        self.assertEqual(fuseau_du_perimetre(siege, self.djibouti.pk), DJIBOUTI)
        self.assertEqual(fuseau_du_perimetre(djiboutien), DJIBOUTI)


class ExportTests(HorlogeTestCase):
    def _csv(self, year):
        self.login(self.doo)
        response = self.client.get(
            "/api/exports/expenses.csv", {"year": year, "country": self.djibouti.pk}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.content.decode("utf-8-sig")

    def test_l_export_de_l_exercice_suivant_porte_la_ligne_a_l_heure_du_pays(self):
        contenu = self._csv(self.suivant)

        self.assertIn("DJ-0001", contenu)
        self.assertIn(f"01/01/{self.suivant} 01:00", contenu)

    def test_l_export_de_l_exercice_ecoule_ne_la_porte_pas(self):
        """La ligne se classe par sa date, pas par celle du dossier."""
        self.assertNotIn("DJ-0001", self._csv(self.year))


class RepartitionTests(HorlogeTestCase):
    def _mois(self, year):
        self.login(self.doo)
        response = self.client.get(
            "/api/dashboard/breakdown/", {"year": year, "country": self.djibouti.pk}
        )
        return [row["label"] for row in response.data["by_month"]]

    def test_la_ligne_tombe_en_janvier(self):
        self.assertEqual(self._mois(self.suivant), [f"{self.suivant}-01"])
        self.assertEqual(self._mois(self.year), [])


class ImportTests(HorlogeTestCase):
    def test_la_date_importee_est_lue_dans_le_fuseau_du_pays(self):
        workbook = Workbook()
        sheet = workbook.active
        entetes = [title for title, _ in EXPENSE_COLUMNS]
        sheet.append(entetes)
        ligne = {
            "N°ORDRE": "DJ-IMPORT", "DATE": f"01/01/{self.suivant} 01:00",
            "PAYS": "Djibouti", "TEAM": "Équipe Djibouti", "OWNER": "Kodjo Mensah",
            "LIBELLE DES TRANSACTIONS": "Taxi importé", "DEPENSES": 5000,
        }
        sheet.append([ligne.get(entete) for entete in entetes])
        contenu = BytesIO()
        workbook.save(contenu)
        contenu.seek(0)
        self.login(self.doo)

        response = self.client.post(
            "/api/imports/expenses.xlsx",
            {"file": ("depenses.xlsx", contenu, XLSX)}, format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        importee = Expense.objects.get(title="Taxi importé")
        self.assertEqual(importee.date, datetime(self.suivant, 1, 1, 1, 0, tzinfo=DJIBOUTI))
        self.assertEqual(importee.date.astimezone(UTC).hour, 22)
