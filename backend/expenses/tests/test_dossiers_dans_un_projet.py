"""Un projet naît avec ses dossiers prédéfinis (décisions 102 et 106)."""

from datetime import date

from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from core.models import DossierKind, Project, ProjectKind, Team
from expenses.models import AuditLog, Dossier, Expense
from expenses.workflow import Status

from .base import ExpenseTestCase


class DossiersPredefinisTests(ExpenseTestCase):
    """Un projet naît avec ses dossiers, un par type (décision 106)."""

    def creer(self, user=None, **charge):
        self.login(user or self.owner)
        return self.client.post(
            "/api/projects/",
            {
                "country": self.togo.pk, "name": "Congrès de Kara",
                "kind": ProjectKind.CONGRES, "team": self.team.pk, **charge,
            },
            format="json",
        )

    def types_du(self, kind):
        return list(
            DossierKind.objects.filter(project_kind=kind, is_active=True).values_list("name", flat=True)
        )

    def test_le_projet_recoit_un_dossier_par_type(self):
        reponse = self.creer()

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        projet = Project.objects.get(pk=reponse.data["id"])
        dossiers = list(projet.dossiers.order_by("number"))
        types = self.types_du(ProjectKind.CONGRES)
        self.assertTrue(types)
        self.assertEqual([d.label for d in dossiers], types)
        self.assertEqual([d.kind.name for d in dossiers], types)
        self.assertEqual(
            [d.number for d in dossiers],
            [f"{projet.reference}-D{rang:03d}" for rang in range(1, len(types) + 1)],
        )
        for dossier in dossiers:
            # Brouillons du pays, signés par le manager qui a créé le projet,
            # dans son équipe : lui seul les soumet (décision 46).
            self.assertEqual(dossier.country, self.togo)
            self.assertEqual(dossier.team, self.team)
            self.assertEqual(dossier.status, Status.DRAFT)
            self.assertEqual(dossier.created_by, self.owner.username)
        self.assertEqual(
            AuditLog.objects.filter(
                object_type="Dossier", action=AuditLog.Action.CREATED,
                object_id__in=[d.pk for d in dossiers],
            ).count(),
            len(dossiers),
        )
        self.assertEqual(reponse.data["dossier_count"], len(dossiers))

    def test_le_type_de_projet_choisit_ses_dossiers(self):
        voyage = self.creer(name="Tournée du Nord", kind=ProjectKind.VOYAGE)

        self.assertEqual(voyage.status_code, status.HTTP_201_CREATED, voyage.data)
        self.assertEqual(
            list(Dossier.objects.filter(project_id=voyage.data["id"]).order_by("number")
                 .values_list("label", flat=True)),
            self.types_du(ProjectKind.VOYAGE),
        )

    def test_un_projet_qui_ne_recevrait_aucun_dossier_ne_se_cree_pas(self):
        """Le pays n'aurait aucun moyen d'en ouvrir : ni projet inactif, ni
        type de projet sans type de dossier actif."""
        DossierKind.objects.filter(project_kind=ProjectKind.SOUTIEN_FINANCIER).update(is_active=False)

        sans_type_actif = self.creer(kind=ProjectKind.SOUTIEN_FINANCIER)
        inactif = self.creer(name="Congrès en sommeil", is_active=False)

        for reponse in (sans_type_actif, inactif):
            self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST, reponse.data)
        self.assertFalse(
            Project.objects.filter(name__in=["Congrès de Kara", "Congrès en sommeil"]).exists()
        )

    def test_le_siege_complete_un_projet_de_ses_dossiers_manquants(self):
        """Un type ajouté depuis : le projet n'est pas complété d'office,
        le siège le complète à la demande ; rien n'est ouvert deux fois."""
        projet_id = self.creer().data["id"]
        badges = DossierKind.objects.create(project_kind=ProjectKind.CONGRES, name="Badges")
        self.assertFalse(Dossier.objects.filter(project_id=projet_id, kind=badges).exists())

        refus_pays = self.client.post(f"/api/projects/{projet_id}/completer/")
        self.login(self.controller)
        complete = self.client.post(f"/api/projects/{projet_id}/completer/")
        encore = self.client.post(f"/api/projects/{projet_id}/completer/")

        self.assertEqual(refus_pays.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(complete.status_code, status.HTTP_200_OK, complete.data)
        self.assertEqual(encore.status_code, status.HTTP_200_OK)
        ajoute = Dossier.objects.get(project_id=projet_id, kind=badges)
        self.assertTrue(ajoute.predefini)
        self.assertEqual(ajoute.created_by, "")
        self.assertEqual(
            Dossier.objects.filter(project_id=projet_id).count(),
            len(self.types_du(ProjectKind.CONGRES)),
        )

    def test_le_dossier_ajoute_reste_lisible_par_l_equipe_du_projet(self):
        """Le dossier complété prend l'équipe commune des dossiers déjà là :
        sans elle, le manager rattaché à cette équipe ne le voyait pas."""
        cloisonne = make_user("equipe.togo", Role.MANAGER, [self.togo], teams=[self.team])
        projet_id = self.creer(cloisonne).data["id"]
        badges = DossierKind.objects.create(project_kind=ProjectKind.CONGRES, name="Badges")
        self.login(self.controller)

        reponse = self.client.post(f"/api/projects/{projet_id}/completer/")

        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        ajoute = Dossier.objects.get(project_id=projet_id, kind=badges)
        self.assertEqual(ajoute.team, self.team)
        self.login(cloisonne)
        self.assertEqual(
            self.client.get(f"/api/dossiers/{ajoute.pk}/").status_code, status.HTTP_200_OK
        )

    def test_sans_equipe_commune_le_dossier_ajoute_n_en_devine_pas(self):
        """Deux équipes parmi les dossiers déjà là : rien ne se devine."""
        projet_id = self.creer().data["id"]
        autre = Team.objects.create(country=self.togo, name="Équipe Kara")
        Dossier.objects.filter(pk=Dossier.objects.filter(project_id=projet_id).first().pk).update(
            team=autre
        )
        badges = DossierKind.objects.create(project_kind=ProjectKind.CONGRES, name="Badges")
        self.login(self.controller)

        self.client.post(f"/api/projects/{projet_id}/completer/")

        self.assertIsNone(Dossier.objects.get(project_id=projet_id, kind=badges).team)

    def test_un_projet_inactif_ne_se_complete_pas(self):
        self.projet.is_active = False
        self.projet.save()
        self.login(self.controller)

        reponse = self.client.post(f"/api/projects/{self.projet.pk}/completer/")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_type_desactive_n_ouvre_pas_de_dossier(self):
        self.stands.is_active = False
        self.stands.save()

        reponse = self.creer()

        self.assertFalse(
            Dossier.objects.filter(project_id=reponse.data["id"], kind=self.stands).exists()
        )

    def test_sans_type_le_projet_ne_se_cree_pas(self):
        reponse = self.creer(kind="")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("kind", reponse.data)
        self.assertFalse(Project.objects.filter(name="Congrès de Kara").exists())

    def test_l_equipe_d_un_autre_pays_est_refusee(self):
        abidjan = Team.objects.create(country=self.ivoire, name="Équipe Abidjan")

        reponse = self.creer(team=abidjan.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Project.objects.filter(name="Congrès de Kara").exists())

    def test_un_manager_rattache_a_des_equipes_en_choisit_une_des_siennes(self):
        """Ses dossiers lui resteraient sinon invisibles."""
        autre = Team.objects.create(country=self.togo, name="Équipe Kara")
        cloisonne = make_user("kara.togo", Role.MANAGER, [self.togo], teams=[self.team])

        sans_equipe = self.creer(cloisonne, team=None)
        hors_equipe = self.creer(cloisonne, team=autre.pk)
        dans_l_equipe = self.creer(cloisonne)

        self.assertEqual(sans_equipe.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("team", sans_equipe.data)
        self.assertEqual(hors_equipe.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(dans_l_equipe.status_code, status.HTTP_201_CREATED, dans_l_equipe.data)
        self.login(cloisonne)
        self.assertEqual(
            self.client.get("/api/dossiers/", {"project": dans_l_equipe.data["id"]}).data["count"],
            len(self.types_du(ProjectKind.CONGRES)),
        )

    def test_le_siege_ne_cree_pas_de_projet(self):
        """Créer un projet ouvre des dossiers : c'est une déclaration
        (décisions 89 et 108)."""
        for compte in (self.controller, self.doo):
            with self.subTest(compte=compte.username):
                self.assertEqual(self.creer(compte).status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Project.objects.filter(name="Congrès de Kara").exists())

    def test_un_projet_chez_le_voisin_ne_se_cree_pas(self):
        reponse = self.creer(country=self.ivoire.pk, team=None)

        self.assertIn(reponse.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN))
        self.assertFalse(Project.objects.filter(name="Congrès de Kara").exists())

    def test_un_dossier_ne_s_ouvre_plus_a_la_main(self):
        self.login(self.owner)

        reponse = self.client.post(
            "/api/dossiers/",
            {"project": self.projet.pk, "kind": self.stands.pk, "date": f"{self.year}-04-01"},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_le_siege_type_un_ancien_projet_qui_recoit_ses_dossiers(self):
        """Un projet d'avant la 2.0, typé par le siège, reçoit ses dossiers ;
        sans auteur, ils reviennent au pays."""
        a_typer = Project.objects.create(country=self.togo, name="À typer", reference="TG-P-2025-001")
        self.login(self.controller)

        reponse = self.client.patch(
            f"/api/projects/{a_typer.pk}/",
            {"kind": ProjectKind.SOUTIEN_FINANCIER, "motif": "Typage de reprise"},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        dossiers = Dossier.objects.filter(project=a_typer)
        self.assertEqual(
            list(dossiers.values_list("label", flat=True)), self.types_du(ProjectKind.SOUTIEN_FINANCIER)
        )
        self.assertEqual(set(dossiers.values_list("created_by", flat=True)), {""})

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
        self.creer()
        self.login(self.owner)

        par_projet = self.client.get("/api/dossiers/", {"project": self.projet.pk})
        par_type = self.client.get("/api/dossiers/", {"kind": self.stands.pk})
        par_type_de_projet = self.client.get("/api/dossiers/", {"project__kind": "voyage"})

        self.assertEqual(par_projet.data["count"], 1)
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
