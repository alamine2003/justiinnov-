"""Le titre d'un dossier se renomme jusqu'à la clôture, et c'est tracé (décisions 104 et 108)."""

from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from expenses.models import AuditLog, Dossier
from expenses.workflow import Status

from .base import ExpenseTestCase
from .test_workflow import configurer


class RenommerTests(ExpenseTestCase):
    def renommer(self, user, label, dossier=None):
        self.login(user)
        return self.client.post(
            f"/api/dossiers/{(dossier or self.dossier).pk}/rename/", {"label": label}, format="json"
        )

    def test_un_manager_du_pays_renomme_tant_que_non_cloture(self):
        for statut in (Status.DRAFT, Status.SUBMITTED, Status.JUSTIFIED):
            with self.subTest(statut=statut):
                Dossier.objects.filter(pk=self.dossier.pk).update(status=statut)
                titre = f"Stands — {statut}"

                reponse = self.renommer(self.owner, titre)

                self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
                self.assertEqual(reponse.data["label"], titre)
                self.assertEqual(reponse.data["status"], statut)

    def test_cloture_le_titre_ne_change_plus(self):
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.CLOSED)

        reponse = self.renommer(self.owner, "Après coup")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.label, "Mission Lomé")
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.RENAMED).exists())

    def test_pas_seulement_l_auteur(self):
        """Tout manager du pays, pas seulement celui qui l'a ouvert."""
        collegue = make_user("collegue.togo", Role.MANAGER, [self.togo])
        self.dossier.created_by = self.owner.username
        self.dossier.save()

        self.assertEqual(self.renommer(collegue, "Stands — salon").status_code, status.HTTP_200_OK)

    def test_chaque_changement_est_trace_avec_l_ancien_titre(self):
        ancien = self.dossier.label

        self.renommer(self.owner, "Stands du hall A")

        entree = AuditLog.objects.get(object_type="Dossier", action=AuditLog.Action.RENAMED)
        self.assertEqual(entree.detail["before"], {"label": ancien})
        self.assertEqual(entree.detail["after"], {"label": "Stands du hall A"})
        self.assertEqual(entree.user, self.owner.username)

    def test_un_titre_identique_ne_laisse_pas_de_trace(self):
        self.renommer(self.owner, self.dossier.label)

        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.RENAMED).exists())

    def test_un_titre_vide_est_refuse(self):
        reponse = self.renommer(self.owner, "   ")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.label, "Mission Lomé")

    def test_rien_d_autre_ne_change(self):
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.SUBMITTED)
        self.renommer(
            self.owner, "Nouveau titre",
        )
        reponse = self.client.post(
            f"/api/dossiers/{self.dossier.pk}/rename/",
            {"label": "Encore", "status": "draft", "number": "X", "project": None},
            format="json",
        )

        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)
        self.assertEqual(self.dossier.number, "N-0001")
        self.assertEqual(self.dossier.project, self.projet)

    def test_le_siege_ne_renomme_pas_par_defaut(self):
        for user in (self.controller, self.doo):
            with self.subTest(role=user.profile.role):
                self.assertEqual(
                    self.renommer(user, "Titre du siège").status_code, status.HTTP_403_FORBIDDEN
                )

    def test_la_matrice_ne_l_accorde_pas_au_siege(self):
        """Verrouillé (décision 108) : même enregistré en base, le réglage
        ne l'ouvre pas au siège — les verrous valent à la lecture."""
        configurer(capability_roles={"dossiers.rename": ["manager", "admin"]})

        self.assertEqual(
            self.renommer(self.controller, "Titre RH").status_code, status.HTTP_403_FORBIDDEN
        )
        self.login(self.controller)
        reponse = self.client.patch(
            "/api/permissions/",
            {"capabilities": {"dossiers.rename": ["manager", "admin"]}},
            format="json",
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_dossier_du_voisin_est_introuvable(self):
        self.assertEqual(
            self.renommer(self.rep_ivoire, "Chez le voisin").status_code, status.HTTP_404_NOT_FOUND
        )

    def test_l_action_est_proposee_dans_allowed_actions(self):
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.JUSTIFIED)
        self.login(self.owner)

        actions = self.client.get(f"/api/dossiers/{self.dossier.pk}/").data["allowed_actions"]

        self.assertIn("rename", actions)
        self.login(self.controller)
        self.assertNotIn(
            "rename", self.client.get(f"/api/dossiers/{self.dossier.pk}/").data["allowed_actions"]
        )
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.CLOSED)
        self.login(self.owner)
        self.assertNotIn(
            "rename", self.client.get(f"/api/dossiers/{self.dossier.pk}/").data["allowed_actions"]
        )
