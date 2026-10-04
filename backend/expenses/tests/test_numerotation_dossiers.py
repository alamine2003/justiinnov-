"""Numéros calculés des dossiers (décision 102, ``expenses.numerotation``)."""

from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import Country, DossierKind, Project, ProjectKind
from core.numerotation import creer_projet
from expenses.models import Dossier
from expenses.numerotation import creer_dossier


class NumerotationDesDossiersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.togo = Country.objects.create(
            name="Togo", code="TG", currency="XOF", timezone="Africa/Lome",
        )
        cls.stands = DossierKind.objects.get(project_kind=ProjectKind.CONGRES, name="Stands")
        cls.t_shirts = DossierKind.objects.get(project_kind=ProjectKind.CONGRES, name="T-shirts")

    def projet(self, nom):
        return creer_projet(Project(country=self.togo, name=nom, kind=ProjectKind.CONGRES))

    def dossier(self, projet, titre="Stands", kind=None, predefini=False):
        return creer_dossier(Dossier(
            project=projet, kind=kind or self.stands, country=self.togo, label=titre,
            predefini=predefini,
            date=date(2026, 10, 1),
        ))

    def test_les_dossiers_d_un_projet_se_suivent(self):
        projet = self.projet("Congrès de pédiatrie")
        premier = self.dossier(projet)
        second = self.dossier(projet, "T-shirts", self.t_shirts)
        self.assertEqual(premier.number, f"{projet.reference}-D001")
        self.assertEqual(second.number, f"{projet.reference}-D002")
        self.assertEqual(second.sequence, 2)

    def test_un_seul_dossier_predefini_par_type_dans_un_projet(self):
        """Les dossiers prédéfinis d'un projet, un par type (décision 106) :
        la base refuse le second."""
        projet = self.projet("Congrès de cardiologie")
        self.dossier(projet, predefini=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.dossier(projet, "Stands du hall B", predefini=True)

    def test_les_dossiers_ouverts_a_la_main_avant_coexistent(self):
        """Avant la décision 106, plusieurs dossiers s'ouvraient sous un même
        type : ils ne bloquent ni la contrainte ni le dossier prédéfini."""
        projet = self.projet("Congrès de neurologie")
        self.dossier(projet)
        self.dossier(projet, "Stands du hall B")

        self.dossier(projet, "Stands", predefini=True)

        self.assertEqual(projet.dossiers.filter(kind=self.stands).count(), 3)

    def test_chaque_projet_repart_de_un(self):
        self.dossier(self.projet("Congrès A"))
        autre = self.projet("Congrès B")
        self.assertEqual(self.dossier(autre).number, f"{autre.reference}-D001")

    def test_un_projet_sans_reference_ne_numerote_pas(self):
        historique = Project.objects.create(
            country=self.togo, name="Historique (avant 2.0)", is_historical=True,
        )
        with self.assertRaises(ValueError):
            self.dossier(historique)
