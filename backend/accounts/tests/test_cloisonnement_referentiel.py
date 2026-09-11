"""Le référentiel du pays voisin n'existe pas pour un compte restreint.

Audit du 8 septembre 2026, §4.5 : les sérialiseurs du référentiel (équipes,
projets, centres de coûts, intitulés, catégories, bénéficiaires) exposaient
``country`` comme une clé étrangère ordinaire, et leur validateur d'unicité
``(country, nom)`` s'exécutait avant le contrôle de périmètre. Un compte
restreint doté de ``referentiel.create`` lisait alors, dans la différence
entre « existe déjà » (400) et « hors périmètre » (403), le référentiel de
la filiale voisine. Cloisonnés (``ChampCloisonne``), un pays hors périmètre
est un pays inconnu : la même réponse, quel que soit ce qui existe chez le
voisin.
"""

from django.core.cache import cache
from rest_framework import status

from accounts.models import Role
from core.models import (
    CostCenter,
    ExpenseTitle,
    MarketingCategory,
    Manager,
    Project,
    Team,
)
from expenses.models import Beneficiary

from .test_scoping import ScopingTestCase, make_user


class CloisonnementDuReferentielTests(ScopingTestCase):
    """Un manager togolais à qui la matrice a ouvert le référentiel : il ne
    doit rien apprendre du référentiel ivoirien, ni le reconstituer."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rh = make_user("rh.admin", Role.ADMIN)
        # Ce qui existe côté Côte d'Ivoire, que le Togolais ne doit pas sonder.
        cls.equipe_ci = Team.objects.create(country=cls.ivoire, name="Équipe secrète Abidjan")
        cls.projet_ci = Project.objects.create(country=cls.ivoire, name="Projet confidentiel CI")
        cls.centre_ci = CostCenter.objects.create(country=cls.ivoire, code="CI-99", name="Centre CI")
        cls.intitule_ci = ExpenseTitle.objects.create(country=cls.ivoire, label="Intitulé CI")
        cls.categorie_ci = MarketingCategory.objects.create(country=cls.ivoire, name="Catégorie CI")
        cls.beneficiaire_ci = Beneficiary.objects.create(
            country=cls.ivoire, name="Clinique des Deux Plateaux", kind=Beneficiary.Kind.PROSPECT
        )

    def setUp(self):
        super().setUp()
        cache.clear()
        # La matrice ouvre le référentiel au pays — configuration prévue,
        # documentée, réglée par un administrateur.
        self.login(self.rh)
        reponse = self.client.patch(
            "/api/permissions/",
            {"capabilities": {
                "referentiel.create": ["super_admin", "admin", "manager"],
                "referentiel.update": ["super_admin", "admin", "manager"],
            }},
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        self.login(self.rep_togo)

    def _creer(self, route, charge):
        return self.client.post(f"/api/{route}", charge, format="json")

    def test_creer_chez_le_voisin_est_refuse_sans_dire_si_le_nom_existe(self):
        """Le cœur de la fuite : sur un pays hors périmètre, la réponse est la
        même que le nom existe déjà chez le voisin ou non — jamais un 400
        « existe déjà » qui confirmerait l'existence, jamais un 403 « hors
        périmètre » distinct d'un 400 « invalide »."""
        cas = [
            ("teams/", {"name": "Équipe secrète Abidjan"}, {"name": "Équipe inédite"}),
            ("projects/", {"name": "Projet confidentiel CI"}, {"name": "Projet inédit"}),
            ("cost-centers/", {"code": "CI-99", "name": "Centre CI"},
             {"code": "CI-00", "name": "Centre inédit"}),
            ("expense-titles/", {"label": "Intitulé CI"}, {"label": "Intitulé inédit"}),
            ("marketing-categories/", {"name": "Catégorie CI"}, {"name": "Catégorie inédite"}),
            ("beneficiaries/", {"name": "Clinique des Deux Plateaux", "kind": "prospect"},
             {"name": "Prospect inédit", "kind": "prospect"}),
        ]
        for route, existant, inedit in cas:
            with self.subTest(route=route):
                r_existant = self._creer(route, {"country": self.ivoire.pk, **existant})
                r_inedit = self._creer(route, {"country": self.ivoire.pk, **inedit})
                # Même code pour les deux : rien ne distingue un nom qui
                # existe chez le voisin d'un nom qui n'y existe pas.
                self.assertEqual(r_existant.status_code, r_inedit.status_code, route)
                self.assertEqual(r_existant.status_code, status.HTTP_400_BAD_REQUEST, r_existant.data)
                # Et le message porte sur le pays « invalide », pas sur l'unicité.
                self.assertIn("country", r_existant.data)
                self.assertNotIn("existe déjà", str(r_existant.data).lower())

    def test_rien_n_est_cree_chez_le_voisin(self):
        avant = Team.objects.filter(country=self.ivoire).count()
        self._creer("teams/", {"country": self.ivoire.pk, "name": "Équipe pirate"})
        self.assertEqual(Team.objects.filter(country=self.ivoire).count(), avant)

    def test_creer_dans_son_pays_reste_possible(self):
        """Le cloisonnement ne ferme pas le référentiel de son propre pays :
        la capacité ouverte sert bien à quelque chose."""
        reponse = self._creer("teams/", {"country": self.togo.pk, "name": "Équipe Kara"})
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)


class ResponsablesDuPaysTests(ScopingTestCase):
    """Un pays inscrit ses propres responsables, et seulement les siens.

    ``managers.create`` et ``managers.update`` sont séparées des capacités du
    pays : elles s'ouvrent au pays, celles du pays non. Le rattachement
    s'écrit sur le responsable (``/api/managers/``), plus par la fiche du
    pays — une relation, un seul chemin d'écriture, une seule capacité.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rh = make_user("rh.responsables", Role.ADMIN)
        cls.manager_ci = Manager.objects.create(name="Responsable Abidjan")
        cls.ivoire.managers.add(cls.manager_ci)

    def setUp(self):
        super().setUp()
        cache.clear()
        self.login(self.rh)
        reponse = self.client.patch(
            "/api/permissions/",
            {"capabilities": {
                "managers.create": ["super_admin", "admin", "manager"],
                "managers.update": ["super_admin", "admin", "manager"],
            }},
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        self.login(self.rep_togo)

    def test_le_pays_inscrit_son_responsable_et_le_retrouve(self):
        reponse = self.client.post(
            "/api/managers/",
            {"name": "Kofi Mensah", "countries": [self.togo.pk]},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        cree = Manager.objects.get(pk=reponse.data["id"])
        self.assertIn(self.togo, cree.countries.all())
        # Créé dans son pays, donc relisible : c'est tout l'objet de
        # l'exigence d'un pays à l'inscription.
        liste = self.client.get("/api/managers/")
        self.assertIn(cree.pk, [ligne["id"] for ligne in liste.data["results"]])

    def test_un_responsable_sans_pays_est_refuse_au_pays(self):
        """Sans rattachement, il sortirait du périmètre à peine créé."""
        reponse = self.client.post("/api/managers/", {"name": "Sans pays"}, format="json")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST, reponse.data)
        self.assertIn("countries", reponse.data)
        self.assertFalse(Manager.objects.filter(name="Sans pays").exists())

    def test_le_pays_du_voisin_n_est_pas_proposable(self):
        reponse = self.client.post(
            "/api/managers/",
            {"name": "Chez le voisin", "countries": [self.ivoire.pk]},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST, reponse.data)
        self.assertFalse(Manager.objects.filter(name="Chez le voisin").exists())

    def test_le_responsable_du_voisin_n_existe_pas(self):
        """404, jamais 403 : son existence ne doit pas fuiter."""
        reponse = self.client.patch(
            f"/api/managers/{self.manager_ci.pk}/", {"title": "Détourné"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND, reponse.data)
        self.manager_ci.refresh_from_db()
        self.assertNotEqual(self.manager_ci.title, "Détourné")

    def test_le_pays_ne_se_rattache_pas_le_responsable_du_voisin(self):
        """Même en le nommant directement : le champ ne propose que son pays,
        et le responsable visé est hors de sa vue."""
        reponse = self.client.patch(
            f"/api/managers/{self.manager_ci.pk}/",
            {"countries": [self.togo.pk]},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND, reponse.data)
        self.assertNotIn(self.manager_ci, self.togo.managers.all())

    def test_les_capacites_du_pays_restent_fermees(self):
        """Ouvrir le responsable n'ouvre pas la devise : c'est la raison
        d'être de la scission."""
        reponse = self.client.patch(
            f"/api/countries/{self.togo.pk}/", {"currency": "EUR"}, format="json"
        )

        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN, reponse.data)
        self.togo.refresh_from_db()
        self.assertNotEqual(self.togo.currency, "EUR")
