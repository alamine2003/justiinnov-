"""Un dossier s'ouvre dans un projet typé, sous un type de ce projet (décision 102)."""

from datetime import date

from rest_framework import status

from core.models import DossierKind, Project, ProjectKind
from expenses.models import AuditLog, Dossier, Expense

from .base import ExpenseTestCase


class OuvertureDansUnProjetTests(ExpenseTestCase):
    def ouvrir(self, user=None, **charge):
        self.login(user or self.owner)
        return self.client.post(
            "/api/dossiers/",
            {
                "project": self.projet.pk, "kind": self.stands.pk,
                "team": self.team.pk, "date": f"{self.year}-04-01", **charge,
            },
            format="json",
        )

    def test_le_dossier_est_numerote_dans_son_projet(self):
        premier = self.ouvrir()
        second = self.ouvrir(label="Stands du hall B")

        self.assertEqual(premier.status_code, status.HTTP_201_CREATED, premier.data)
        self.assertEqual(premier.data["number"], f"{self.projet.reference}-D001")
        self.assertEqual(second.data["number"], f"{self.projet.reference}-D002")
        # Pays du projet, titre par défaut : le nom du type.
        self.assertEqual(premier.data["country"], self.togo.pk)
        self.assertEqual(premier.data["label"], "Stands")
        self.assertEqual(second.data["label"], "Stands du hall B")
        self.assertEqual(premier.data["project_reference"], self.projet.reference)
        self.assertEqual(premier.data["kind_name"], "Stands")
        self.assertFalse(premier.data["project_is_historical"])
        self.assertTrue(
            AuditLog.objects.filter(
                object_type="Dossier", object_id=premier.data["id"], action=AuditLog.Action.CREATED
            ).exists()
        )

    def test_sans_projet_ni_type_le_dossier_ne_s_ouvre_pas(self):
        sans_projet = self.ouvrir(project=None)
        sans_type = self.ouvrir(kind=None)

        self.assertEqual(sans_projet.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", sans_projet.data)
        self.assertEqual(sans_type.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("kind", sans_type.data)

    def test_un_type_d_un_autre_type_de_projet_est_refuse(self):
        billets = DossierKind.objects.get_or_create(project_kind=ProjectKind.VOYAGE, name="Billets")[0]

        reponse = self.ouvrir(kind=billets.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("kind", reponse.data)

    def test_un_type_desactive_est_refuse(self):
        self.stands.is_active = False
        self.stands.save()

        self.assertEqual(self.ouvrir().status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_projet_inactif_non_type_ou_historique_est_refuse(self):
        a_typer = Project.objects.create(country=self.togo, name="À typer", reference="TG-P-2025-001")
        historique = Project.objects.create(
            country=self.togo, name="Historique (avant 2.0)", is_historical=True, reference="TG-P-HIST",
        )
        self.projet.is_active = False
        self.projet.save()

        for projet in (self.projet, a_typer, historique):
            with self.subTest(projet=projet.name):
                reponse = self.ouvrir(project=projet.pk)
                self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("project", reponse.data)

    def test_un_projet_du_voisin_est_inconnu(self):
        reponse = self.ouvrir(project=self.projet_ivoire.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("Abidjan", str(reponse.data))
        self.assertEqual(Dossier.objects.filter(project=self.projet_ivoire).count(), 0)

    def test_le_projet_et_le_type_ne_changent_plus(self):
        autre = Project.objects.create(
            country=self.togo, name="Autre congrès", kind=ProjectKind.CONGRES, reference="TG-P-X",
        )
        self.dossier.created_by = self.owner.username
        self.dossier.save()
        self.login(self.owner)

        reponse = self.client.patch(
            f"/api/dossiers/{self.dossier.pk}/", {"project": autre.pk}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.project, self.projet)

    def test_la_liste_se_filtre_par_projet_et_par_type(self):
        self.ouvrir()
        self.login(self.owner)

        par_projet = self.client.get("/api/dossiers/", {"project": self.projet.pk})
        par_type = self.client.get("/api/dossiers/", {"kind": self.stands.pk})
        par_type_de_projet = self.client.get("/api/dossiers/", {"project__kind": "voyage"})

        self.assertEqual(par_projet.data["count"], 2)
        self.assertEqual(par_type.data["count"], 2)
        self.assertEqual(par_type_de_projet.data["count"], 0)


class LignesQuiSuiventLeProjetTests(ExpenseTestCase):
    """Une ligne porte le projet de son dossier : c'est lui qui l'impute."""

    def payload(self, **extra):
        return {
            "dossier": self.dossier.pk, "country": self.togo.pk, "team": self.team.pk,
            "owner": self.manager.pk, "date": f"{self.year}-03-15T10:00:00Z",
            "title": "Moquette du stand", "amount": "50000.00", **extra,
        }

    def setUp(self):
        super().setUp()
        self.dossier.created_by = self.owner.username
        self.dossier.save()
        self.manager.countries.add(self.togo)

    def test_la_ligne_recoit_le_projet_de_son_dossier(self):
        self.login(self.owner)

        reponse = self.client.post("/api/expenses/", self.payload(), format="json")

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertEqual(Expense.objects.get(pk=reponse.data["id"]).project, self.projet)

    def test_un_autre_projet_est_refuse(self):
        autre = Project.objects.create(
            country=self.togo, name="Autre", kind=ProjectKind.CONGRES, reference="TG-P-Y",
        )
        self.login(self.owner)

        reponse = self.client.post("/api/expenses/", self.payload(project=autre.pk), format="json")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", reponse.data)

    def test_une_ligne_d_un_dossier_historique_garde_son_projet(self):
        historique = Project.objects.create(
            country=self.togo, name="Historique (avant 2.0)", is_historical=True, reference="TG-P-HIST",
        )
        ancien = Dossier.objects.create(
            number="N-ANCIEN", label="Ancien", country=self.togo, project=historique,
            date=date(self.year, 2, 1), created_by=self.owner.username,
        )
        self.login(self.owner)

        reponse = self.client.post(
            "/api/expenses/", self.payload(dossier=ancien.pk, project=self.projet.pk), format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertEqual(Expense.objects.get(pk=reponse.data["id"]).project, self.projet)
        # L'interface le lit pour garder le choix du projet sur la ligne.
        self.assertTrue(self.client.get(f"/api/dossiers/{ancien.pk}/").data["project_is_historical"])
