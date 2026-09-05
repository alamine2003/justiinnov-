"""Actions calculées côté serveur : ``allowed_actions`` sur la ligne et le
dossier.

C'est la fin du miroir de règles côté client : rôle, état, étape de
contrôle obligatoire, quatre yeux, lignes tranchées et pièces exploitables
sont jugés par le serveur, l'interface n'affiche que ce qu'il permet.
"""

from datetime import date

from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from expenses.models import Dossier, Proof
from expenses.workflow import Status

from .base import ExpenseTestCase
from .test_workflow import configurer


class ActionsDeLigneTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.dm = make_user("dm.innov", Role.DM)
        self.ligne = self.make_expense()
        self.submit_dossier()

    def _actions(self, user, ligne=None):
        self.login(user)
        response = self.client.get(f"/api/expenses/{(ligne or self.ligne).pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["allowed_actions"]

    def test_le_pays_n_a_aucune_action_de_controle(self):
        self.assertEqual(self._actions(self.owner), [])

    def test_le_dm_ne_fait_que_mettre_en_controle(self):
        self.assertEqual(self._actions(self.dm), ["review"])

    def test_le_df_tranche_une_ligne_soumise(self):
        self.assertEqual(self._actions(self.controller), ["review", "justify", "reject"])

    def test_l_etape_de_controle_obligatoire_retire_justify(self):
        configurer(require_review_step=True)

        self.assertEqual(self._actions(self.controller), ["review", "reject"])

    def test_l_auteur_d_une_ligne_ne_la_justifie_pas(self):
        """Quatre yeux : la ligne saisie par le DF ne lui propose rien, et
        propose tout à un autre membre du siège."""
        dossier = Dossier.objects.create(
            number="N-0002", label="Mission du DF", country=self.togo,
            date=date(self.year, 3, 16), created_by=self.owner.username,
        )
        propre = self.make_expense(dossier=dossier, created_by=self.controller.username)
        self.submit_dossier(dossier)

        self.assertEqual(self._actions(self.controller, propre), [])
        self.assertEqual(self._actions(self.doo, propre), ["review", "justify", "reject"])

    def test_une_ligne_sans_auteur_n_admet_rien(self):
        dossier = Dossier.objects.create(
            number="N-0003", label="Import", country=self.togo,
            date=date(self.year, 3, 16), created_by=self.owner.username,
        )
        anonyme = self.make_expense(dossier=dossier, created_by="")
        self.submit_dossier(dossier)

        self.assertEqual(self._actions(self.controller, anonyme), [])

    def test_une_ligne_justifiee_ne_propose_que_la_cloture(self):
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.ligne.pk}/justify/")

        self.assertEqual(self._actions(self.controller), ["close"])
        self.assertEqual(self._actions(self.dm), [])

    def test_le_registre_les_expose_aussi(self):
        self.login(self.controller)

        response = self.client.get("/api/expenses/register/")

        self.assertEqual(
            response.data["results"][0]["allowed_actions"], ["review", "justify", "reject"]
        )


class ActionsDeDossierTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.dm = make_user("dm.innov", Role.DM)
        self.admin = make_user("rh.admin", Role.ADMIN)

    def _actions(self, user, dossier=None, via="detail"):
        self.login(user)
        pk = (dossier or self.dossier).pk
        if via == "liste":
            response = self.client.get("/api/dossiers/")
            return next(d for d in response.data["results"] if d["id"] == pk)["allowed_actions"]
        response = self.client.get(f"/api/dossiers/{pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["allowed_actions"]

    def _piece(self, statut=Proof.ProofStatus.RECEIVED):
        return Proof.objects.create(
            dossier=self.dossier, file="justificatifs/f.pdf",
            original_name="facture.pdf", sha256="a" * 64, status=statut,
        )

    def test_un_dossier_vide_ne_se_soumet_pas(self):
        self.assertEqual(self._actions(self.owner), [])

        self.make_expense()

        self.assertEqual(self._actions(self.owner), ["submit"])
        self.assertEqual(self._actions(self.owner, via="liste"), ["submit"])
        self.assertEqual(self._actions(self.controller), [])

    def test_un_dossier_soumis_attend_ses_lignes(self):
        """Le DF peut le mettre en contrôle, pas le trancher tant qu'une
        ligne reste en suspens ; le DM ne fait que le mettre en contrôle ;
        l'administrateur peut aussi le rouvrir."""
        self.make_expense()
        self._piece()
        self.submit_dossier()

        self.assertEqual(self._actions(self.dm), ["review"])
        self.assertEqual(self._actions(self.controller), ["review"])
        self.assertEqual(self._actions(self.admin), ["review", "reopen"])
        self.assertEqual(self._actions(self.owner), [])

    def test_les_lignes_tranchees_ouvrent_le_constat(self):
        ligne = self.make_expense()
        autre = self.make_expense(title="Hôtel")
        self._piece()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{ligne.pk}/justify/")

        avec_une_en_suspens = self._actions(self.controller)
        self.client.post(f"/api/expenses/{autre.pk}/reject/", {"note": "Sans reçu"})
        toutes_tranchees = self._actions(self.controller)
        rouvrable = self._actions(self.admin)

        self.assertEqual(avec_une_en_suspens, ["review"])
        # Une ligne non justifiée : le dossier ne se justifie pas, il se
        # constate non justifié.
        self.assertEqual(toutes_tranchees, ["review", "reject"])
        # Une ligne justifiée est un constat : plus de réouverture.
        self.assertEqual(rouvrable, ["review", "reject"])

    def test_un_dossier_sans_piece_exploitable_ne_se_justifie_pas(self):
        ligne = self.make_expense()
        self._piece(Proof.ProofStatus.REJECTED)
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{ligne.pk}/justify/")

        self.assertEqual(self._actions(self.controller), ["review", "reject"])

    def test_toutes_les_lignes_justifiees_et_une_piece(self):
        ligne = self.make_expense()
        self._piece()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{ligne.pk}/justify/")

        self.assertEqual(self._actions(self.controller), ["review", "justify", "reject"])
        self.assertEqual(self._actions(self.controller, via="liste"), ["review", "justify", "reject"])

    def test_celui_qui_a_ouvert_le_dossier_n_y_voit_aucun_controle(self):
        self.dossier.created_by = self.controller.username
        self.dossier.save()
        self.make_expense()
        self._piece()
        self.submit_dossier()

        self.assertEqual(self._actions(self.controller), [])
        self.assertEqual(self._actions(self.doo), ["review", "reopen"])

    def test_un_dossier_justifie_se_clot(self):
        ligne = self.make_expense()
        self._piece()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{ligne.pk}/justify/")
        self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(self._actions(self.controller), ["close"])
        self.assertEqual(self._actions(self.admin), ["close"])


class TransitionRenvoieLeDetailTests(ExpenseTestCase):
    """Une transition répond le dossier complet, lignes et pièces comprises :
    l'interface affiche ce qui est, sans recharger."""

    def test_la_soumission_renvoie_les_lignes_et_les_pieces(self):
        ligne = self.make_expense()
        Proof.objects.create(
            dossier=self.dossier, file="justificatifs/f.pdf",
            original_name="facture.pdf", sha256="a" * 64,
        )

        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], Status.SUBMITTED)
        self.assertEqual([e["id"] for e in response.data["expenses"]], [ligne.pk])
        self.assertEqual(response.data["expenses"][0]["status"], Status.SUBMITTED)
        self.assertEqual(len(response.data["proofs"]), 1)
        self.assertEqual(response.data["expense_count"], 1)
        self.assertEqual(response.data["allowed_actions"], [])

    def test_la_justification_renvoie_le_detail_avec_les_actions(self):
        ligne = self.make_expense()
        Proof.objects.create(
            dossier=self.dossier, file="justificatifs/f.pdf",
            original_name="facture.pdf", sha256="a" * 64,
        )
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{ligne.pk}/justify/")

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["expenses"][0]["status"], Status.JUSTIFIED)
        self.assertEqual(response.data["expenses"][0]["allowed_actions"], ["close"])
        self.assertEqual(response.data["allowed_actions"], ["close"])
