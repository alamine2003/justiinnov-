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
