"""Projets typés et numérotés, types de dossiers (décisions 100 et 101)."""

from rest_framework import status

from core.models import ChangeLog, DossierKind, Project, ProjectKind
from expenses.tests.base import ExpenseTestCase
from expenses.tests.test_workflow import configurer


class ProjetsTests(ExpenseTestCase):
    """Le pays ouvre ses projets ; le siège les type, les modifie, les désactive."""

    def creer(self, user, **charge):
        self.login(user)
        return self.client.post(
            "/api/projects/",
            {"country": self.togo.pk, "name": "Congrès de cardiologie", "kind": "congres", **charge},
            format="json",
        )

    def test_le_manager_cree_un_projet_de_son_pays_avec_sa_reference(self):
        reponse = self.creer(self.owner)

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        projet = Project.objects.get(pk=reponse.data["id"])
        # Le socle a déjà ouvert « Congrès de Lomé » : celui-ci est le deuxième.
        self.assertEqual(projet.reference, f"TG-P-{projet.year}-002")
        self.assertEqual(reponse.data["reference"], projet.reference)
        self.assertEqual(reponse.data["kind_display"], "Congrès")
        self.assertFalse(reponse.data["a_typer"])
        self.assertTrue(reponse.data["accepte_des_dossiers"])
        self.assertTrue(
            ChangeLog.objects.filter(model_name="project", object_id=projet.pk, action="created").exists()
        )

    def test_la_reference_ne_se_saisit_pas(self):
        reponse = self.creer(self.owner, reference="TG-P-1999-999", sequence=999)

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertNotEqual(reponse.data["reference"], "TG-P-1999-999")

    def test_le_type_est_obligatoire(self):
        reponse = self.creer(self.owner, kind="")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("kind", reponse.data)

    def test_le_manager_n_ouvre_pas_de_projet_chez_le_voisin(self):
        reponse = self.creer(self.owner, country=self.ivoire.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Project.objects.filter(name="Congrès de cardiologie").exists())

    def test_le_manager_ne_modifie_pas_un_projet(self):
        """Créer est ouvert au pays ; modifier et désactiver restent au siège."""
        self.login(self.owner)
        reponse = self.client.patch(
            f"/api/projects/{self.projet.pk}/", {"name": "Autre nom"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_type_d_un_projet_ne_change_plus(self):
        self.login(self.controller)
        reponse = self.client.patch(
            f"/api/projects/{self.projet.pk}/", {"kind": "voyage"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.projet.refresh_from_db()
        self.assertEqual(self.projet.kind, ProjectKind.CONGRES)

    def test_un_projet_a_typer_se_type_une_fois(self):
        ancien = Project.objects.create(
            country=self.togo, name="Projet d'avant", reference="TG-P-2025-001",
        )
        self.login(self.controller)

        lu = self.client.get(f"/api/projects/{ancien.pk}/").data
        self.assertTrue(lu["a_typer"])
        self.assertFalse(lu["accepte_des_dossiers"])
        reponse = self.client.patch(
            f"/api/projects/{ancien.pk}/", {"kind": "voyage"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        self.assertFalse(reponse.data["a_typer"])
        self.assertEqual(
            self.client.patch(f"/api/projects/{ancien.pk}/", {"kind": "congres"}, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_le_projet_historique_ne_se_type_pas(self):
        historique = Project.objects.create(
            country=self.togo, name="Historique (avant 2.0)", is_historical=True,
            reference="TG-P-HIST",
        )
        self.login(self.controller)

        reponse = self.client.patch(
            f"/api/projects/{historique.pk}/", {"kind": "congres"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_la_liste_compte_les_dossiers_et_se_filtre_par_type(self):
        self.login(self.owner)

        reponse = self.client.get("/api/projects/", {"kind": "congres"})

        projets = {p["id"]: p for p in reponse.data["results"]}
        self.assertEqual(projets[self.projet.pk]["dossier_count"], 1)
        self.assertNotIn(self.projet_ivoire.pk, projets)

    def test_les_onglets_comptent_les_projets_par_pays(self):
        """Comme les dossiers (décision 99) : un onglet par pays du
        périmètre, avec le nombre de projets que la liste affichera."""
        self.login(self.controller)

        reponse = self.client.get("/api/projects/par-pays/", {"kind": "congres"})

        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        comptes = {p["id"]: p["count"] for p in reponse.data["pays"]}
        self.assertEqual(comptes[self.togo.pk], Project.objects.filter(country=self.togo, kind="congres").count())
        self.assertEqual(reponse.data["total"], Project.objects.filter(kind="congres").count())

    def test_le_manager_ne_voit_que_l_onglet_de_son_pays(self):
        self.login(self.owner)

        reponse = self.client.get("/api/projects/par-pays/")

        self.assertEqual([p["id"] for p in reponse.data["pays"]], [self.togo.pk])
        self.assertEqual(reponse.data["total"], Project.objects.filter(country=self.togo).count())

    def test_un_projet_d_un_autre_pays_est_introuvable(self):
        self.login(self.owner)

        reponse = self.client.get(f"/api/projects/{self.projet_ivoire.pk}/")

        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)


class TypesDeDossiersTests(ExpenseTestCase):
    """La liste commune, lue par tous, tenue par le siège (décision 101)."""

    def test_tout_compte_lit_la_liste(self):
        self.login(self.owner)

        reponse = self.client.get("/api/dossier-kinds/", {"project_kind": "voyage"})

        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {k["name"] for k in reponse.data["results"]},
            {"Billets", "Carburant", "Hôtellerie", "Repas", "Forfait"},
        )

    def test_le_siege_ajoute_un_type_et_c_est_trace(self):
        self.login(self.controller)

        reponse = self.client.post(
            "/api/dossier-kinds/",
            {"project_kind": "soutien_financier", "name": "Bourse"},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertTrue(
            ChangeLog.objects.filter(model_name="dossier_kind", object_id=reponse.data["id"]).exists()
        )

    def test_le_pays_ne_tient_pas_la_liste(self):
        self.login(self.owner)

        reponse = self.client.post(
            "/api/dossier-kinds/", {"project_kind": "congres", "name": "Goodies"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_pays_ne_la_tient_pas_meme_avec_le_referentiel_ouvert(self):
        """Le référentiel d'un pays peut s'ouvrir au pays ; la liste commune
        aux dix-sept filiales, non : elle se tient comme la configuration."""
        configurer(capability_roles={
            "referentiel.create": ["super_admin", "admin", "manager"],
            "referentiel.update": ["super_admin", "admin", "manager"],
        })
        self.login(self.owner)

        creation = self.client.post(
            "/api/dossier-kinds/", {"project_kind": "congres", "name": "Goodies"}, format="json"
        )
        desactivation = self.client.patch(
            f"/api/dossier-kinds/{self.stands.pk}/", {"is_active": False}, format="json"
        )

        self.assertEqual(creation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(desactivation.status_code, status.HTTP_403_FORBIDDEN)
        self.stands.refresh_from_db()
        self.assertTrue(self.stands.is_active)

    def test_un_type_ne_se_supprime_pas(self):
        self.login(self.controller)

        reponse = self.client.delete(f"/api/dossier-kinds/{self.stands.pk}/")

        self.assertEqual(reponse.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(DossierKind.objects.filter(pk=self.stands.pk).exists())

    def test_un_type_employe_ne_change_pas_de_type_de_projet(self):
        self.login(self.controller)

        reponse = self.client.patch(
            f"/api/dossier-kinds/{self.stands.pk}/", {"project_kind": "voyage"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
