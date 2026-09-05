"""Matrice des droits configurable (décision 43).

Les administrateurs règlent, case par case, quel rôle porte quelle
capacité ; les verrous, eux, ne se règlent pas : le super administrateur
garde tout, le pays ne contrôle jamais ce qu'il déclare.
"""

from django.core.cache import cache
from rest_framework import status

from core.models import ChangeLog, WorkflowConfiguration

from accounts.models import Role
from accounts.permissions import CAPACITES, CAPACITES_PAR_CLE, roles_pour

from .test_scoping import ScopingTestCase, make_user


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
                self.assertIn(Role.SUPER_ADMIN, matrice[capacite.key]["fixed_roles"])

    def test_un_droit_accorde_s_applique_a_la_requete_suivante(self):
        """Le DM reçoit l'export : la route qui lui répondait 403 s'ouvre,
        ``/api/me/`` le dit, et le journal garde l'avant et l'après."""
        self.login(self.dm)
        self.assertEqual(
            self.client.get("/api/exports/expenses.csv?year=2026").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        response = self._regler(self.rh, **{"data.export": ["super_admin", "admin", "dm"]})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        capacites = {c["key"]: c["roles"] for c in response.data["capabilities"]}
        self.assertEqual(capacites["data.export"], ["admin", "dm", "super_admin"])
        self.login(self.dm)
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
            entree.diff["data.export"], [["admin", "super_admin"], ["admin", "dm", "super_admin"]]
        )

    def test_revenir_au_defaut_efface_le_choix(self):
        self._regler(self.rh, **{"data.export": ["super_admin", "admin", "dm"]})

        self._regler(self.rh, **{"data.export": ["super_admin", "admin"]})

        self.assertEqual(WorkflowConfiguration.objects.get().capability_roles, {})

    def test_le_pays_ne_recoit_jamais_le_controle(self):
        for cle in ("expenses.review", "expenses.validate", "expenses.close",
                    "proofs.review", "dossiers.reopen", "audit.read", "users.update",
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

    def test_les_comptes_ne_s_ouvrent_pas_a_un_role_restrictible(self):
        """Un DF restreint à un pays qui créerait des comptes pourrait se
        donner un administrateur : les comptes restent aux rôles globaux."""
        for cle in ("users.read", "users.create", "users.update"):
            with self.subTest(cle=cle):
                response = self._regler(self.siege, **{cle: ["super_admin", "admin", "df"]})

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertNotIn(Role.DF, roles_pour(cle))

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

    def test_le_super_administrateur_garde_tout(self):
        response = self._regler(self.siege, **{"data.export": ["admin"]})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("data.export", response.data["capabilities"])
        self.assertIn(Role.SUPER_ADMIN, roles_pour("data.export"))

    def test_la_configuration_reste_aux_administrateurs(self):
        """Ni ouverte au DF, ni retirée à la RH : sinon plus personne pour
        régler la matrice, ou n'importe qui."""
        elargie = self._regler(self.siege, **{"configuration.manage": ["super_admin", "admin", "df"]})
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

        self.assertEqual(roles_pour("expenses.validate"), {Role.SUPER_ADMIN})
        self.login(self.rep_togo)
        self.assertFalse(self.client.get("/api/me/").data["permissions"]["expenses.validate"])

    def test_une_capacite_inconnue_ou_un_role_inconnu_sont_refuses(self):
        inconnue = self._regler(self.siege, **{"depenses.tout": ["super_admin"]})
        role = self._regler(self.siege, **{"data.export": ["super_admin", "auditeur"]})

        self.assertEqual(inconnue.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(role.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ni_le_pays_ni_le_controle_ne_reglent_la_matrice(self):
        for user in (self.rep_togo, self.controleur, self.dm):
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
        response = self._regler(self.siege, **{"dossiers.reopen": ["super_admin"]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(roles_pour("dossiers.reopen"), {Role.SUPER_ADMIN})
        self.assertEqual(CAPACITES_PAR_CLE["dossiers.reopen"].defaut, {Role.SUPER_ADMIN, Role.ADMIN})


def matrice_de(cle):
    return sorted(roles_pour(cle))
