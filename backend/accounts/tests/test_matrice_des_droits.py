"""Matrice des droits configurable (décision 43).

Les administrateurs règlent, case par case, quel rôle porte quelle
capacité — l'argent compris (décision 58) ; les verrous, eux, ne se règlent
pas (décision 89) : le pays seul déclare, l'administrateur seul contrôle,
les administrateurs gardent l'administration.
"""

from django.core.cache import cache
from rest_framework import status

from core.models import ChangeLog, WorkflowConfiguration

from accounts.models import Role
from accounts.permissions import CAPACITES, CAPACITES_PAR_CLE, COUNTRY_ROLES, roles_pour

from .test_scoping import ScopingTestCase, make_user

#: Les lignes de la matrice qui ne bougent pas : la déclaration au pays, le
#: contrôle à l'administrateur (décision 89).
DECLARATION = (
    "expenses.create", "expenses.update", "expenses.delete",
    "proofs.upload", "dossiers.submit",
)
CONTROLE = (
    "expenses.review", "expenses.validate", "expenses.close",
    "proofs.review", "dossiers.reopen", "rectifications.decide",
)


class MatriceDesDroitsTests(ScopingTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rh = make_user("rh.admin", Role.ADMIN)

    def setUp(self):
        super().setUp()
        cache.clear()

    def _regler(self, user, **capacites):
        self.login(user)
        return self.client.patch(
            "/api/permissions/", {"capabilities": capacites}, format="json"
        )

    def _matrice(self):
        self.login(self.siege)
        return {c["key"]: c for c in self.client.get("/api/permissions/").data["capabilities"]}

    def test_la_matrice_par_defaut_est_celle_du_code(self):
        matrice = self._matrice()

        for capacite in CAPACITES:
            with self.subTest(capacite=capacite.key):
                self.assertEqual(matrice[capacite.key]["roles"], sorted(capacite.defaut))
                self.assertEqual(matrice[capacite.key]["default_roles"], sorted(capacite.defaut))
                self.assertEqual(matrice[capacite.key]["fixed_roles"], sorted(capacite.fixes))

    def test_la_declaration_est_au_pays_seul(self):
        """Ni l'administrateur ni le super administrateur ne créent de
        dossier ni ne déposent de pièce (décision 89) ; le pays les garde."""
        for cle in DECLARATION:
            with self.subTest(cle=cle):
                self.assertEqual(roles_pour(cle), COUNTRY_ROLES)
                refus = self._regler(self.siege, **{cle: ["super_admin", "admin", "manager"]})
                self.assertEqual(refus.status_code, status.HTTP_400_BAD_REQUEST)
                retrait = self._regler(self.siege, **{cle: []})
                self.assertEqual(retrait.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(roles_pour(cle), COUNTRY_ROLES)
        # L'import, lui, peut être retiré au pays : il garde la saisie.
        self.assertEqual(roles_pour("data.import"), COUNTRY_ROLES)
        self.assertEqual(self._regler(self.rh, **{"data.import": []}).status_code, 200)
        self.assertEqual(roles_pour("data.import"), frozenset())

    def test_le_controle_est_a_l_administrateur_seul(self):
        """Le super administrateur supervise, il ne tranche pas ; le pays ne
        contrôle pas ce qu'il déclare (décision 89)."""
        for cle in CONTROLE:
            with self.subTest(cle=cle):
                self.assertEqual(roles_pour(cle), {Role.ADMIN})
                for roles in (["admin", "super_admin"], ["admin", "manager"], []):
                    response = self._regler(self.siege, **{cle: roles})
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, roles)
                self.assertEqual(roles_pour(cle), {Role.ADMIN})

    def test_un_droit_accorde_s_applique_a_la_requete_suivante(self):
        """Le manager reçoit l'export : la route qui lui répondait 403
        s'ouvre, ``/api/me/`` le dit, et le journal garde l'avant et
        l'après."""
        self.login(self.rep_togo)
        self.assertEqual(
            self.client.get("/api/exports/expenses.csv?year=2026").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        response = self._regler(self.rh, **{"data.export": ["super_admin", "admin", "manager"]})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        capacites = {c["key"]: c["roles"] for c in response.data["capabilities"]}
        self.assertEqual(capacites["data.export"], ["admin", "manager", "super_admin"])
        self.login(self.rep_togo)
        self.assertTrue(self.client.get("/api/me/").data["permissions"]["data.export"])
        self.assertEqual(
            self.client.get("/api/exports/expenses.csv?year=2026").status_code,
            status.HTTP_200_OK,
        )
        entree = ChangeLog.objects.filter(
            model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION, label="Matrice des droits"
        ).latest("pk")
        self.assertEqual(entree.performed_by, self.rh.username)
        self.assertEqual(
            entree.diff["data.export"],
            [["admin", "super_admin"], ["admin", "manager", "super_admin"]],
        )

    def test_revenir_au_defaut_efface_le_choix(self):
        self._regler(self.rh, **{"data.export": ["super_admin", "admin", "manager"]})

        self._regler(self.rh, **{"data.export": ["super_admin", "admin"]})

        self.assertEqual(WorkflowConfiguration.objects.get().capability_roles, {})

    def test_le_pays_ne_recoit_jamais_le_controle(self):
        for cle in (*CONTROLE, "audit.read", "users.update",
                    "budgets.update", "reallocations.decide", "rates.manage",
                    "countries.create", "countries.update"):
            with self.subTest(cle=cle):
                response = self._regler(self.siege, **{cle: ["super_admin", "admin", "manager"]})

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(cle, response.data["capabilities"])
                self.assertNotIn(Role.MANAGER, roles_pour(cle))

    def test_un_pays_dote_du_droit_par_la_base_n_ouvre_pas_de_filiale(self):
        """Ouvrir une filiale est une décision du siège : même une valeur
        glissée en base ne la rend pas au manager, et la route le refuse."""
        configuration = WorkflowConfiguration.charger()
        configuration.capability_roles = {"countries.create": ["super_admin", "manager"]}
        configuration.save()

        self.login(self.rep_togo)
        response = self.client.post(
            "/api/countries/",
            {"code": "SN", "country_ref": "SN-01", "name": "Sénégal",
             "currency": "XOF", "timezone": "Africa/Dakar"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn(Role.MANAGER, roles_pour("countries.create"))

    def test_les_comptes_ne_s_ouvrent_pas_au_pays(self):
        """Un manager qui créerait des comptes pourrait se donner un
        administrateur : les comptes restent au siège."""
        for cle in ("users.read", "users.create", "users.update"):
            with self.subTest(cle=cle):
                response = self._regler(self.siege, **{cle: ["super_admin", "admin", "manager"]})

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertNotIn(Role.MANAGER, roles_pour(cle))

    def test_une_valeur_mal_formee_vaut_le_defaut(self):
        """Une matrice qui lèverait fermerait toute l'API, y compris la route
        qui permet de la réparer."""
        configuration = WorkflowConfiguration.charger()
        configuration.capability_roles = {"data.export": 1, "audit.read": "admin"}
        configuration.save()

        self.assertEqual(sorted(roles_pour("data.export")), ["admin", "super_admin"])
        self.assertEqual(sorted(roles_pour("audit.read")), ["admin", "super_admin"])
        self.login(self.siege)
        self.assertEqual(self.client.get("/api/permissions/").status_code, status.HTTP_200_OK)

    def test_les_enveloppes_sont_a_la_direction_seule(self):
        """Décision 91 : attribuer, modifier, supprimer une enveloppe,
        arbitrer une réallocation, tenir les taux — le super administrateur
        seul. L'administrateur contrôle les dépenses et lit les enveloppes :
        il ne peut ni se rouvrir ces lignes, ni les retirer à la direction."""
        for cle in ("budgets.create", "budgets.update", "budgets.delete",
                    "reallocations.request", "reallocations.decide", "rates.manage"):
            with self.subTest(cle=cle):
                self.assertEqual(sorted(roles_pour(cle)), ["super_admin"])
                self.assertIn("admin", self._matrice()[cle]["locked_roles"])
                # L'administrateur qui se rouvrirait la ligne est refusé…
                rouverte = self._regler(self.rh, **{cle: ["super_admin", "admin"]})
                self.assertEqual(rouverte.status_code, status.HTTP_400_BAD_REQUEST, rouverte.data)
                # … la direction ne se la retire pas non plus.
                retiree = self._regler(self.siege, **{cle: []})
                self.assertEqual(retiree.status_code, status.HTTP_400_BAD_REQUEST, retiree.data)
                self.assertEqual(sorted(roles_pour(cle)), ["super_admin"])

    def test_la_demande_de_reallocation_reste_ouvrable_au_pays(self):
        """Choix d'organisation : la matrice peut ouvrir la demande de
        réallocation au manager — jamais à l'administrateur."""
        ouverte = self._regler(self.siege, **{"reallocations.request": ["super_admin", "manager"]})

        self.assertEqual(ouverte.status_code, status.HTTP_200_OK, ouverte.data)
        self.assertEqual(sorted(roles_pour("reallocations.request")), ["manager", "super_admin"])

    def test_les_administrateurs_gardent_tout(self):
        """Ni le super administrateur ni l'administrateur ne se retirent un
        droit : celui qui attribue les droits ne peut pas perdre les siens."""
        sans_direction = self._regler(self.siege, **{"data.export": ["admin"]})
        sans_rh = self._regler(self.siege, **{"data.export": ["super_admin"]})

        for response in (sans_direction, sans_rh):
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("data.export", response.data["capabilities"])
        self.assertEqual(sorted(roles_pour("data.export")), ["admin", "super_admin"])

    def test_la_configuration_reste_aux_administrateurs(self):
        """Ni ouverte au pays, ni retirée à la RH : sinon plus personne pour
        régler la matrice, ou n'importe qui."""
        elargie = self._regler(self.siege, **{"configuration.manage": ["super_admin", "admin", "manager"]})
        retiree = self._regler(self.siege, **{"configuration.manage": ["super_admin"]})

        self.assertEqual(elargie.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(retiree.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(matrice_de("configuration.manage"), ["admin", "super_admin"])

    def test_une_valeur_glissee_en_base_ne_leve_pas_les_verrous(self):
        """Les verrous s'appliquent à la lecture, pas seulement à
        l'enregistrement : un autre chemin d'écriture ne les contourne pas."""
        configuration = WorkflowConfiguration.charger()
        configuration.capability_roles = {
            "expenses.validate": ["manager"],
            "inconnue": ["manager"],
        }
        configuration.save()

        self.assertEqual(roles_pour("expenses.validate"), {Role.ADMIN})
        self.login(self.rep_togo)
        self.assertFalse(self.client.get("/api/me/").data["permissions"]["expenses.validate"])

    def test_une_capacite_inconnue_ou_un_role_inconnu_sont_refuses(self):
        inconnue = self._regler(self.siege, **{"depenses.tout": ["super_admin"]})
        role = self._regler(self.siege, **{"data.export": ["super_admin", "auditeur"]})

        self.assertEqual(inconnue.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(role.status_code, status.HTTP_400_BAD_REQUEST)

    def test_le_pays_ne_regle_pas_la_matrice(self):
        for user in (self.rep_togo,):
            with self.subTest(user=user.username):
                response = self._regler(user, **{"data.export": ["super_admin", "admin"]})
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.login(user)
                self.assertEqual(
                    self.client.get("/api/permissions/").status_code, status.HTTP_403_FORBIDDEN
                )

    def test_un_choix_enregistre_se_lit_dans_roles_pour(self):
        """Le défaut reste dans le code, le choix dans la base : ``roles_pour``
        rend le second (les services sont éprouvés dans ``expenses``)."""
        response = self._regler(self.siege, **{"data.export": ["super_admin", "admin", "manager"]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            roles_pour("data.export"), {Role.SUPER_ADMIN, Role.ADMIN, Role.MANAGER}
        )
        self.assertEqual(CAPACITES_PAR_CLE["data.export"].defaut, {Role.SUPER_ADMIN, Role.ADMIN})


def matrice_de(cle):
    return sorted(roles_pour(cle))


class ContratDeLaMatriceTests(ScopingTestCase):
    """Ce que la matrice et le profil disent à l'interface, en plus des droits."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rh = make_user("rh.admin", Role.ADMIN)

    def setUp(self):
        super().setUp()
        cache.clear()

    def _roles(self, user):
        self.login(user)
        response = self.client.get("/api/permissions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {r["value"]: r for r in response.data["roles"]}

    def test_un_administrateur_ne_confere_pas_le_role_de_super_administrateur(self):
        """La même règle que ``UserViewSet`` : la matrice la dit d'avance,
        pour que l'interface ne propose pas un rôle que le serveur refusera."""
        roles = self._roles(self.rh)

        self.assertFalse(roles[Role.SUPER_ADMIN]["assignable"])
        self.assertTrue(roles[Role.ADMIN]["assignable"])
        self.assertTrue(roles[Role.MANAGER]["assignable"])

    def test_un_super_administrateur_confere_tous_les_roles(self):
        roles = self._roles(self.siege)

        self.assertTrue(all(role["assignable"] for role in roles.values()))

    def test_le_profil_expose_les_seuils_d_alerte_a_tous_les_roles(self):
        configuration = WorkflowConfiguration.charger()
        configuration.alert_thresholds = [70, 90, 100]
        configuration.save()

        for user in (self.rep_togo, self.controleur, self.rh, self.siege):
            with self.subTest(compte=user.username):
                self.login(user)
                response = self.client.get("/api/me/")

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["alert_thresholds"], [70, 90, 100])
