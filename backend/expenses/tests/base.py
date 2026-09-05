"""Socle commun aux tests des dépenses."""

from datetime import date
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.models import Budget
from core.models import Country, Manager, Team
from expenses.models import Dossier, Expense
from expenses.services import resolve_budget
from expenses.workflow import Status

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
    """Deux pays, une enveloppe par pays, un dossier au Togo.

    Le décor est planté une fois par classe (``setUpTestData``) : Django en
    rend à chaque test une copie, et annule la transaction derrière lui. Ce
    qu'un test mute — enveloppe, ligne, compte — reste dans sa copie. Une
    sous-classe qui doit ajouter au décor le fait dans son propre
    ``setUpTestData`` ; ce qui passe par ``self.client`` reste dans ``setUp``.
    """

    #: État du dossier au démarrage. Les tests du circuit d'une ligne partent
    #: d'un dossier déjà déclaré : côté pays, déclarer tient en une action, et
    #: une ligne ne se soumet jamais avant son dossier. Ceux qui portent sur
    #: le dossier lui-même gardent le brouillon.
    dossier_status = Status.DRAFT

    @classmethod
    def setUpTestData(cls):
        cls.ivoire = Country.objects.create(
            name="Côte d'Ivoire", code="CI", country_ref="CT-01",
            currency="XOF", timezone="Africa/Abidjan",
        )
        cls.togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        cls.team = Team.objects.create(country=cls.togo, name="Équipe Lomé")
        cls.manager = Manager.objects.create(name="Kodjo Mensah")

        cls.year = timezone.now().year
        cls.budget = Budget.objects.create(
            country=cls.togo, year=cls.year, amount=Decimal("1000000.00")
        )
        cls.budget_ivoire = Budget.objects.create(
            country=cls.ivoire, year=cls.year, amount=Decimal("500000.00")
        )

        # Le pays : un manager par pays. Le siège : le DF qui tranche et la
        # direction. Le DM, qui met en contrôle, est créé par les tests qui
        # en ont besoin — un destinataire de plus changerait les décomptes
        # de notifications et d'e-mails des autres.
        cls.owner = make_user("owner.togo", Role.MANAGER, [cls.togo])
        cls.controller = make_user("rh.innov", Role.DF)
        cls.doo = make_user("do.innov", Role.SUPER_ADMIN)
        cls.rep_ivoire = make_user("cote-ivoire.innov", Role.MANAGER, [cls.ivoire])

        cls.manager.countries.add(cls.togo)

        cls.dossier = Dossier.objects.create(
            number="N-0001", label="Mission Lomé", country=cls.togo,
            team=cls.team, owner=cls.manager, date=date(cls.year, 3, 15),
            status=cls.dossier_status, created_by=cls.owner.username,
        )

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def make_expense(self, amount="100000.00", **kwargs):
        """Ligne créée directement en base, comme l'aurait fait le pays.

        Elle porte un auteur : sans lui, la règle des quatre yeux ne peut pas
        être vérifiée et la ligne ne se contrôle pas. Une ligne créée dans un
        état déclaré est imputée sur son enveloppe, comme l'exige la base.

        Depuis ``setUpTestData``, s'appelle avec la classe pour ``self`` :
        ``cls.make_expense(cls, ...)``. Ce n'est pas une ``classmethod`` à
        dessein — appelée depuis un test, elle doit lire les copies du test
        (``self.dossier``), jamais les objets partagés de la classe.
        """
        defaults = {
            "dossier": self.dossier,
            "country": self.togo,
            "team": self.team,
            "owner": self.manager,
            "date": timezone.now(),
            "title": "Carburant",
            "amount": Decimal(amount),
            "created_by": self.owner.username,
        }
        defaults.update(kwargs)
        expense = Expense(**defaults)
        if expense.status != Status.DRAFT and expense.budget_id is None:
            expense.budget = resolve_budget(expense)
        expense.save()
        return expense

    def submit_dossier(self, dossier=None, user=None):
        """Le chemin réel du pays : le dossier emporte ses lignes."""
        self.login(user or self.owner)
        return self.client.post(
            f"/api/dossiers/{(dossier or self.dossier).pk}/submit/"
        )
