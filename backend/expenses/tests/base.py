"""Socle commun aux tests des dépenses."""

from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.models import Budget
from core.models import Country, Manager, Team
from expenses.models import Dossier, Expense

#: Les tests ne doivent jamais écrire dans MinIO ni sur le disque.
in_memory_storage = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)


class ExpenseTestCase(APITestCase):
    """Deux pays, une enveloppe par pays, un dossier au Togo."""

    def setUp(self):
        cache.clear()
        self.ivoire = Country.objects.create(
            name="Côte d'Ivoire", code="CI", country_ref="CT-01",
            currency="XOF", timezone="Africa/Abidjan",
        )
        self.togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        self.team = Team.objects.create(country=self.togo, name="Équipe Lomé")
        self.manager = Manager.objects.create(name="Kodjo Mensah")

        self.year = timezone.now().year
        self.budget = Budget.objects.create(
            country=self.togo, year=self.year, amount=Decimal("1000000.00")
        )
        self.budget_ivoire = Budget.objects.create(
            country=self.ivoire, year=self.year, amount=Decimal("500000.00")
        )

        self.owner = make_user("owner.togo", Role.OWNER, [self.togo])
        self.controller = make_user("rh.innov", Role.CONTROLLER)
        self.doo = make_user("do.innov", Role.DOO)
        self.rep_ivoire = make_user("cote-ivoire.innov", Role.COUNTRY_MANAGER, [self.ivoire])

        self.dossier = Dossier.objects.create(
            number="N-0001", label="Mission Lomé", country=self.togo,
            team=self.team, owner=self.manager, date=date(self.year, 3, 15),
        )

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def make_expense(self, amount="100000.00", **kwargs):
        defaults = {
            "dossier": self.dossier,
            "country": self.togo,
            "team": self.team,
            "owner": self.manager,
            "date": timezone.now(),
            "title": "Carburant",
            "amount": Decimal(amount),
        }
        defaults.update(kwargs)
        return Expense.objects.create(**defaults)
