"""L'exercice budgétaire se lit dans le fuseau du pays, pas en UTC."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import TestCase

from budget.models import Budget
from core.models import Country
from expenses.models import Dossier, Expense
from expenses.services import exercice, resolve_budget


class ExerciceTests(TestCase):
    def setUp(self):
        self.kenya = Country.objects.create(
            name="Djibouti", code="DJ", currency="DJF", timezone="Africa/Djibouti"
        )
        self.dossier = Dossier.objects.create(
            number="KE-1", label="Réveillon", country=self.kenya, date=date(2026, 1, 1)
        )
        self.enveloppe_2025 = Budget.objects.create(
            country=self.kenya, year=2025, amount=Decimal("1000.00")
        )
        self.enveloppe_2026 = Budget.objects.create(
            country=self.kenya, year=2026, amount=Decimal("1000.00")
        )

    def ligne(self, quand):
        return Expense.objects.create(
            dossier=self.dossier, country=self.kenya, date=quand,
            title="Taxi", amount=Decimal("10.00"),
        )

    def test_le_premier_janvier_a_une_heure_a_nairobi_est_dans_l_annee_en_cours(self):
        """Régression : la date est conservée en UTC ; à Djibouti (UTC+3), le
        1er janvier à 01:00 est encore le 31 décembre en UTC, et la dépense
        pesait sur l'exercice précédent, déjà clos."""
        depense = self.ligne(datetime(2026, 1, 1, 1, 0, tzinfo=ZoneInfo("Africa/Djibouti")))

        self.assertEqual(depense.date.astimezone(ZoneInfo("UTC")).year, 2025)
        self.assertEqual(exercice(depense), 2026)
        self.assertEqual(resolve_budget(depense), self.enveloppe_2026)

    def test_la_veille_au_soir_reste_dans_l_exercice_precedent(self):
        depense = self.ligne(datetime(2025, 12, 31, 23, 30, tzinfo=ZoneInfo("Africa/Djibouti")))

        self.assertEqual(resolve_budget(depense), self.enveloppe_2025)

    def test_un_fuseau_inconnu_retombe_sur_utc(self):
        """Le fuseau est un texte libre : une faute de frappe ne doit pas
        empêcher de soumettre."""
        self.kenya.timezone = "Afrique/Nulle-Part"
        self.kenya.save()
        depense = self.ligne(datetime(2026, 1, 1, 1, 0, tzinfo=ZoneInfo("Africa/Djibouti")))

        self.assertEqual(exercice(depense), 2025)
