"""La liste commune des types de projets, réglée par le super administrateur (décision 119)."""

from django.utils import translation
from rest_framework import status

from core.models import ChangeLog, DossierKind, Project, ProjectType, code_de_type
from expenses.models import Dossier
from expenses.tests.base import ExpenseTestCase
from expenses.tests.test_workflow import configurer


class CodeDeTypeTests(ExpenseTestCase):
    def test_le_code_vient_du_nom_et_ne_se_repete_pas(self):
        self.assertEqual(code_de_type("Soutien financier", []), "soutien_financier")
        self.assertEqual(code_de_type("Formation", ["formation"]), "formation_2")
        self.assertEqual(code_de_type("Formation", ["formation", "formation_2"]), "formation_3")
        self.assertEqual(code_de_type("Séminaire médical", []), "seminaire_medical")
        self.assertEqual(code_de_type("???", []), "type")
        self.assertLessEqual(len(code_de_type("x" * 80, ["x" * 24])), 24)


class TypesDeProjetsTests(ExpenseTestCase):
    """Lue par tous, tenue par le super administrateur seul, motif à l'appui."""

    def creer_type(self, nom="Formation", **charge):
        self.login(self.doo)
        return self.client.post(
            "/api/project-types/", {"name": nom, "name_en": "Training", **charge}, format="json"
        )

    def test_tout_compte_lit_la_liste_dans_l_ordre(self):
        self.login(self.owner)

        reponse = self.client.get("/api/project-types/")

        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [t["code"] for t in reponse.data["results"]],
            ["congres", "voyage", "soutien_financier"],
        )
        congres = reponse.data["results"][0]
        self.assertEqual(congres["dossier_kinds_actifs"], 4)

    def test_le_libelle_suit_la_langue_du_lecteur(self):
        self.login(self.owner)

        en = self.client.get("/api/project-types/", HTTP_ACCEPT_LANGUAGE="en")
        fr = self.client.get("/api/project-types/", HTTP_ACCEPT_LANGUAGE="fr")

        self.assertEqual(en.data["results"][1]["libelle"], "Trip")
        self.assertEqual(fr.data["results"][1]["libelle"], "Voyage")

    def test_le_super_administrateur_ajoute_un_type_au_code_calcule_et_c_est_trace(self):
        reponse = self.creer_type(code="pirate")

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertEqual(reponse.data["code"], "formation")
        self.assertTrue(
            ChangeLog.objects.filter(model_name="project_type", object_id=reponse.data["id"]).exists()
        )

    def test_un_nom_deja_pris_est_refuse(self):
        reponse = self.creer_type("Voyage")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", reponse.data)

    def test_un_type_nouveau_ouvre_un_projet_avec_ses_dossiers_dans_l_ordre(self):
        """Le geste que la 2.2 ouvre : un type « Formation » et ses deux
        dossiers, puis un projet du pays qui les reçoit d'office."""
        formation = self.creer_type().data
        for ordre, nom in ((2, "Salles"), (1, "Supports")):
            cree = self.client.post(
                "/api/dossier-kinds/",
                {"project_kind": formation["code"], "name": nom, "ordre": ordre},
                format="json",
            )
            self.assertEqual(cree.status_code, status.HTTP_201_CREATED, cree.data)
        self.login(self.owner)

        reponse = self.client.post(
            "/api/projects/",
            {"country": self.togo.pk, "name": "Formation des délégués", "kind": formation["code"]},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertEqual(reponse.data["kind"], "formation")
        self.assertEqual(reponse.data["kind_display"], "Formation")
        dossiers = Dossier.objects.filter(project_id=reponse.data["id"]).order_by("sequence")
        self.assertEqual(list(dossiers.values_list("label", flat=True)), ["Supports", "Salles"])

    def test_un_type_desactive_n_ouvre_plus_de_projet_mais_garde_les_siens(self):
        self.login(self.doo)
        desactivation = self.client.patch(
            f"/api/project-types/{ProjectType.objects.get(code='congres').pk}/",
            {"is_active": False, "motif": "Plus de congrès cette année"}, format="json",
        )
        self.assertEqual(desactivation.status_code, status.HTTP_200_OK, desactivation.data)
        self.login(self.owner)

        creation = self.client.post(
            "/api/projects/",
            {"country": self.togo.pk, "name": "Congrès tardif", "kind": "congres"},
            format="json",
        )

        self.assertEqual(creation.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("kind", creation.data)
        self.projet.refresh_from_db()
        self.assertTrue(self.projet.accepte_des_dossiers)
        self.assertEqual(
            ChangeLog.objects.get(model_name="project_type", action="deactivated").motif,
            "Plus de congrès cette année",
        )

    def test_une_modification_exige_un_motif_et_le_code_ne_change_pas(self):
        self.login(self.doo)
        voyage = ProjectType.objects.get(code="voyage")
        url = f"/api/project-types/{voyage.pk}/"

        sans_motif = self.client.patch(url, {"name": "Déplacement"}, format="json")
        avec_motif = self.client.patch(
            url, {"name": "Déplacement", "code": "deplacement", "motif": "Terme de la direction"},
            format="json",
        )

        self.assertEqual(sans_motif.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(avec_motif.status_code, status.HTTP_200_OK, avec_motif.data)
        voyage.refresh_from_db()
        self.assertEqual((voyage.code, voyage.name), ("voyage", "Déplacement"))
        # Les projets et les types de dossiers gardent leur type.
        self.assertTrue(DossierKind.objects.filter(project_kind="voyage").exists())

    def test_la_rh_lit_mais_ne_tient_pas_la_liste_et_ne_se_l_ouvre_pas(self):
        self.login(self.controller)

        lecture = self.client.get("/api/project-types/")
        creation = self.client.post("/api/project-types/", {"name": "Formation"}, format="json")
        ouverture = self.client.patch(
            "/api/permissions/",
            {"capabilities": {"project_types.manage": ["super_admin", "admin"]}},
            format="json",
        )

        self.assertEqual(lecture.status_code, status.HTTP_200_OK)
        self.assertEqual(creation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ouverture.status_code, status.HTTP_400_BAD_REQUEST)

    def test_le_pays_ne_la_tient_pas_meme_avec_le_referentiel_ouvert(self):
        configurer(capability_roles={
            "referentiel.create": ["super_admin", "admin", "manager"],
            "referentiel.update": ["super_admin", "admin", "manager"],
        })
        self.login(self.owner)

        creation = self.client.post("/api/project-types/", {"name": "Formation"}, format="json")

        self.assertEqual(creation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ProjectType.objects.filter(name="Formation").exists())

    def test_un_type_ne_se_supprime_pas(self):
        self.login(self.doo)
        voyage = ProjectType.objects.get(code="voyage")

        reponse = self.client.delete(f"/api/project-types/{voyage.pk}/")

        self.assertEqual(reponse.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(ProjectType.objects.filter(pk=voyage.pk).exists())

    def test_la_liste_des_projets_se_filtre_par_un_type_nouveau(self):
        formation = ProjectType.objects.create(name="Formation")
        Project.objects.filter(pk=self.projet.pk).update(kind=formation)
        self.login(self.controller)

        reponse = self.client.get("/api/projects/", {"kind": "formation"})

        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual([p["id"] for p in reponse.data["results"]], [self.projet.pk])

    def test_le_libelle_anglais_manquant_retombe_sur_le_francais(self):
        formation = ProjectType.objects.create(name="Formation")

        with translation.override("en"):
            self.assertEqual(formation.libelle, "Formation")
