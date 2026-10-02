"""Projets typés et numérotés, types de dossiers (décisions 100, 101, 108 à 110)."""

from rest_framework import status

from core.models import ChangeLog, DossierKind, Project, ProjectKind
from expenses.tests.base import ExpenseTestCase
from expenses.tests.test_workflow import configurer


class ProjetsTests(ExpenseTestCase):
    """Le pays ouvre ses projets et en corrige le titre ; le siège les
    type, les modifie, les désactive — motif à l'appui."""

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
        """Créer et renommer sont au pays ; modifier et désactiver restent
        au siège (décision 108)."""
        self.login(self.owner)
        reponse = self.client.patch(
            f"/api/projects/{self.projet.pk}/",
            {"is_active": False, "motif": "Fini"}, format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_manager_renomme_son_projet_motif_a_l_appui(self):
        self.login(self.owner)

        sans_motif = self.client.post(
            f"/api/projects/{self.projet.pk}/rename/", {"name": "Congrès de Lomé 2026"}, format="json"
        )
        avec_motif = self.client.post(
            f"/api/projects/{self.projet.pk}/rename/",
            {"name": "Congrès de Lomé 2026", "motif": "Année oubliée"}, format="json",
        )

        self.assertEqual(sans_motif.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("motif", sans_motif.data)
        self.assertEqual(avec_motif.status_code, status.HTTP_200_OK, avec_motif.data)
        self.assertEqual(avec_motif.data["name"], "Congrès de Lomé 2026")
        entree = ChangeLog.objects.get(
            model_name="project", object_id=self.projet.pk, action="updated"
        )
        self.assertEqual(entree.diff, {"name": ["Congrès de Lomé", "Congrès de Lomé 2026"]})
        self.assertEqual(entree.motif, "Année oubliée")
        self.assertEqual(entree.performed_by, self.owner.username)

    def test_renommer_ne_touche_a_rien_d_autre(self):
        self.login(self.owner)

        self.client.post(
            f"/api/projects/{self.projet.pk}/rename/",
            {"name": "Nouveau", "motif": "Coquille", "kind": "voyage", "is_active": False},
            format="json",
        )

        self.projet.refresh_from_db()
        self.assertEqual(self.projet.kind, ProjectKind.CONGRES)
        self.assertTrue(self.projet.is_active)

    def test_le_siege_ne_renomme_pas_un_projet_par_cette_route(self):
        """Le titre est l'affaire du pays (décision 108) ; le siège corrige
        par la modification, motif à l'appui."""
        for compte in (self.controller, self.doo):
            with self.subTest(compte=compte.username):
                self.login(compte)
                reponse = self.client.post(
                    f"/api/projects/{self.projet.pk}/rename/",
                    {"name": "Titre du siège", "motif": "Essai"}, format="json",
                )
                self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_siege_ne_change_pas_le_titre_par_la_modification(self):
        for compte in (self.controller, self.doo):
            with self.subTest(compte=compte.username):
                self.login(compte)
                reponse = self.client.patch(
                    f"/api/projects/{self.projet.pk}/",
                    {"name": "Titre du siège", "motif": "Essai"}, format="json",
                )
                self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("name", reponse.data)
        self.projet.refresh_from_db()
        self.assertEqual(self.projet.name, "Congrès de Lomé")

    def test_un_projet_du_voisin_ne_se_renomme_pas(self):
        self.login(self.rep_ivoire)

        reponse = self.client.post(
            f"/api/projects/{self.projet.pk}/rename/", {"name": "X", "motif": "Y"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_le_siege_modifie_et_desactive_avec_un_motif(self):
        self.login(self.controller)

        sans_motif = self.client.patch(
            f"/api/projects/{self.projet.pk}/", {"is_active": False}, format="json"
        )
        avec_motif = self.client.patch(
            f"/api/projects/{self.projet.pk}/",
            {"is_active": False, "motif": "Congrès annulé"}, format="json",
        )

        self.assertEqual(sans_motif.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("motif", sans_motif.data)
        self.assertEqual(avec_motif.status_code, status.HTTP_200_OK, avec_motif.data)
        entree = ChangeLog.objects.get(
            model_name="project", object_id=self.projet.pk, action="deactivated"
        )
        self.assertEqual(entree.motif, "Congrès annulé")

    def test_l_historique_du_projet_reunit_ses_journaux(self):
        """Le projet, ses dossiers, leurs lignes : une seule chronologie
        (décision 110), lue par le siège, fermée au pays par défaut."""
        self.login(self.owner)
        self.client.post(
            f"/api/projects/{self.projet.pk}/rename/",
            {"name": "Congrès de Lomé 2026", "motif": "Année oubliée"}, format="json",
        )
        self.dossier.created_by = self.owner.username
        self.dossier.save()
        self.client.post(f"/api/dossiers/{self.dossier.pk}/rename/", {"label": "Stands A"}, format="json")

        pays = self.client.get(f"/api/projects/{self.projet.pk}/historique/")
        self.login(self.controller)
        siege = self.client.get(f"/api/projects/{self.projet.pk}/historique/")
        self.login(self.rep_ivoire)
        voisin = self.client.get(f"/api/projects/{self.projet.pk}/historique/")

        self.assertEqual(pays.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(voisin.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(siege.status_code, status.HTTP_200_OK, siege.data)
        entrees = siege.data["entrees"]
        self.assertFalse(siege.data["tronque"])
        renommage = next(e for e in entrees if e["source"] == "referentiel")
        self.assertEqual(renommage["motif"], "Année oubliée")
        self.assertTrue(any(
            e["source"] == "circuit" and e["objet"] == "Dossier" and e["action"] == "renamed"
            for e in entrees
        ))
        dates = [e["created_at"] for e in entrees]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_une_ligne_retiree_reste_dans_l_historique_et_le_journal(self):
        """Elle n'est plus en base ; sa suppression, et celle de sa pièce,
        restent lisibles depuis le projet (décisions 110 et 111)."""
        from expenses.models import Expense, Proof

        self.dossier.created_by = self.owner.username
        self.dossier.save()
        ligne = Expense.objects.create(
            dossier=self.dossier, country=self.togo, project=self.projet, team=self.team,
            date="2026-03-15T10:00:00Z", title="Taxi", amount="5000.00",
            created_by=self.owner.username,
        )
        Proof.objects.create(
            dossier=self.dossier, expense=ligne, file="justificatifs/t.pdf",
            original_name="taxi.pdf", sha256="c" * 64,
        )
        self.login(self.owner)
        self.assertEqual(self.client.delete(f"/api/expenses/{ligne.pk}/").status_code, 204)
        self.login(self.controller)

        historique = self.client.get(f"/api/projects/{self.projet.pk}/historique/").data["entrees"]
        journal = self.client.get("/api/audit/", {"projet": self.projet.pk, "action": "deleted"})

        retraits = {(e["objet"], e["action"]) for e in historique if e["action"] == "deleted"}
        self.assertEqual(retraits, {("Expense", "deleted"), ("Proof", "deleted")})
        self.assertEqual(
            sorted(e["object_type"] for e in journal.data["results"]), ["Expense", "Proof"]
        )

    def test_l_historique_reste_ferme_au_pays_meme_avec_l_historique_ouvert(self):
        """Il relit le journal d'audit : ``history.read``, ouvrable au pays,
        n'y donne pas accès (``audit.read``, jamais le pays)."""
        configurer(capability_roles={"history.read": ["super_admin", "admin", "manager"]})
        self.login(self.owner)

        self.assertEqual(self.client.get("/api/history/").status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(f"/api/projects/{self.projet.pk}/historique/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_le_type_d_un_projet_ne_change_plus(self):
        self.login(self.controller)
        reponse = self.client.patch(
            f"/api/projects/{self.projet.pk}/", {"kind": "voyage", "motif": "Erreur"}, format="json"
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
            f"/api/projects/{ancien.pk}/", {"kind": "voyage", "motif": "Reprise"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        self.assertFalse(reponse.data["a_typer"])
        self.assertEqual(
            self.client.patch(
                f"/api/projects/{ancien.pk}/", {"kind": "congres", "motif": "Reprise"}, format="json"
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_le_projet_historique_ne_se_type_pas(self):
        historique = Project.objects.create(
            country=self.togo, name="Historique (avant 2.0)", is_historical=True,
            reference="TG-P-HIST",
        )
        self.login(self.controller)

        reponse = self.client.patch(
            f"/api/projects/{historique.pk}/", {"kind": "congres", "motif": "Reprise"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ni_l_historique_ni_un_projet_desactive_n_acceptent_de_dossier(self):
        """La règle que lit l'interface pour proposer « Nouveau dossier »
        (décision 105) est celle de l'ouverture (``refus_d_ouverture``)."""
        historique = Project.objects.create(
            country=self.togo, name="Historique (avant 2.0)", is_historical=True,
            reference="TG-P-HIST",
        )
        self.projet.is_active = False
        self.projet.save()
        self.login(self.owner)

        for projet in (historique, self.projet):
            with self.subTest(projet=projet.name):
                lu = self.client.get(f"/api/projects/{projet.pk}/").data
                self.assertFalse(lu["accepte_des_dossiers"])

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
    """La liste commune, lue par tous, tenue par le super administrateur
    seul (décisions 101 et 108)."""

    def test_tout_compte_lit_la_liste(self):
        self.login(self.owner)

        reponse = self.client.get("/api/dossier-kinds/", {"project_kind": "voyage"})

        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {k["name"] for k in reponse.data["results"]},
            {"Billets", "Carburant", "Hôtellerie", "Repas", "Forfait"},
        )

    def test_le_super_administrateur_ajoute_un_type_et_c_est_trace(self):
        self.login(self.doo)

        reponse = self.client.post(
            "/api/dossier-kinds/",
            {"project_kind": "soutien_financier", "name": "Bourse"},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertTrue(
            ChangeLog.objects.filter(model_name="dossier_kind", object_id=reponse.data["id"]).exists()
        )

    def test_la_rh_ne_tient_pas_la_liste_et_ne_se_l_ouvre_pas(self):
        """Elle règle la matrice : le verrou l'empêche de se rouvrir la
        liste qui fixe les dossiers de chaque projet."""
        self.login(self.controller)

        creation = self.client.post(
            "/api/dossier-kinds/", {"project_kind": "congres", "name": "Goodies"}, format="json"
        )
        ouverture = self.client.patch(
            "/api/permissions/",
            {"capabilities": {"dossier_kinds.manage": ["super_admin", "admin"]}},
            format="json",
        )

        self.assertEqual(creation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ouverture.status_code, status.HTTP_400_BAD_REQUEST)

    def test_une_modification_exige_un_motif(self):
        self.login(self.doo)
        url = f"/api/dossier-kinds/{self.stands.pk}/"

        sans_motif = self.client.patch(url, {"is_active": False}, format="json")
        avec_motif = self.client.patch(url, {"is_active": False, "motif": "Plus de stands"}, format="json")

        self.assertEqual(sans_motif.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(avec_motif.status_code, status.HTTP_200_OK, avec_motif.data)
        self.assertEqual(
            ChangeLog.objects.get(model_name="dossier_kind", action="deactivated").motif,
            "Plus de stands",
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
        self.login(self.doo)

        reponse = self.client.delete(f"/api/dossier-kinds/{self.stands.pk}/")

        self.assertEqual(reponse.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(DossierKind.objects.filter(pk=self.stands.pk).exists())

    def test_un_type_employe_ne_change_pas_de_type_de_projet(self):
        self.login(self.doo)

        reponse = self.client.patch(
            f"/api/dossier-kinds/{self.stands.pk}/",
            {"project_kind": "voyage", "motif": "Erreur"}, format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
