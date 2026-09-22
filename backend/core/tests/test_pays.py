"""Le modèle ``Country`` : normalisation du code et validité du fuseau."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status

from core.models import Country
from core.tests.test_api import ApiTestCase


class CodePaysTests(TestCase):
    def test_le_code_est_normalise_a_l_enregistrement(self):
        """L'admin, le shell et ``seed_users`` ne passent pas par le
        sérialiseur : la normalisation doit vivre dans le modèle."""
        pays = Country.objects.create(
            name="Bénin", code=" bj ", currency="XOF", timezone="Africa/Porto-Novo"
        )

        pays.refresh_from_db()
        self.assertEqual(pays.code, "BJ")

    def test_un_doublon_de_casse_est_refuse(self):
        Country.objects.create(name="Bénin", code="BJ", currency="XOF")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Country.objects.create(name="Benin bis", code="bj", currency="XOF")


class FuseauHoraireTests(TestCase):
    def test_un_fuseau_inconnu_est_refuse(self):
        pays = Country(name="Bénin", code="BJ", currency="XOF", timezone="Africa/Cotonu")

        with self.assertRaises(ValidationError) as ctx:
            pays.full_clean()

        self.assertIn("timezone", ctx.exception.message_dict)

    def test_un_fuseau_iana_est_accepte(self):
        pays = Country(name="Bénin", code="BJ", currency="XOF", timezone="Africa/Porto-Novo")

        pays.full_clean()


class FuseauHoraireApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()

    def test_l_api_refuse_un_fuseau_inconnu(self):
        response = self.client.post(
            "/api/countries/",
            {"name": "Bénin", "code": "BJ", "currency": "XOF", "timezone": "Africa/Cotonu"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timezone", response.data)
        self.assertFalse(Country.objects.filter(code="BJ").exists())


class ChampsFigesDuPaysTests(ApiTestCase):
    """Le code et la devise d'un pays qui porte de l'argent ne bougent plus.

    Les montants sont stockés dans la devise du pays : la changer ferait
    lire des francs comme des dirhams. Le code nomme le pays dans les traces
    et les exports.
    """

    def setUp(self):
        super().setUp()
        self.authenticate()

    def _modifier(self, **champs):
        return self.client.patch(f"/api/countries/{self.country.pk}/", champs, format="json")

    def test_un_pays_sans_argent_change_encore(self):
        response = self._modifier(currency="EUR", code="BJ")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_une_enveloppe_fige_le_code_et_la_devise(self):
        from budget.models import Budget

        Budget.objects.create(country=self.country, year=2026, amount=1000)

        for champ, valeur in (("currency", "EUR"), ("code", "BJ")):
            with self.subTest(champ=champ):
                response = self._modifier(**{champ: valeur})

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(champ, response.data)
        self.country.refresh_from_db()
        self.assertEqual((self.country.code, self.country.currency), ("TG", "XOF"))

    def test_une_depense_fige_aussi(self):
        from datetime import date

        from django.utils import timezone

        from expenses.models import Dossier, Expense

        dossier = Dossier.objects.create(
            number="N-1", label="Mission", country=self.country, date=date(2026, 1, 1)
        )
        Expense.objects.create(
            dossier=dossier, country=self.country, date=timezone.now(),
            title="Taxi", amount=1000,
        )

        response = self._modifier(currency="EUR")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("currency", response.data)

    def test_le_reste_se_modifie(self):
        from budget.models import Budget

        Budget.objects.create(country=self.country, year=2026, amount=1000)

        response = self._modifier(name="Togo (siège Lomé)", currency="XOF")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
