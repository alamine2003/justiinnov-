"""Demande de réouverture d'un dossier : la réouverture, demandée par le pays.

Un dossier soumis ou en contrôle est parti trop tôt, ou faux. Le pays ne
peut pas revenir dessus ; il le demande, motif à l'appui, et un
administrateur — jamais l'auteur de la demande — approuve ou refuse.
Approuvée, la demande passe par la réouverture ordinaire : dossier et
lignes au brouillon, motif gardé sur le dossier, traces ``reopened``, pays
prévenu. Refusée, le dossier reste déclaré.
"""

from datetime import date

from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from expenses.models import AuditLog, Dossier, ReopenRequest
from expenses.workflow import REQUEST_REOPENING, Status
from notifications.models import Notification

from .base import ExpenseTestCase
from .test_verrous import CourseTestCase

MOTIF = "Le dossier est parti sans la facture d'hôtel : il faut la joindre avant contrôle."


class ReouvertureDemandeeTestCase(ExpenseTestCase):
    """Un dossier soumis par le pays, avec sa ligne « Hôtel »."""

    def setUp(self):
        super().setUp()
        self.admin = make_user("rh.admin", Role.ADMIN)
        self.dm_togo = make_user("dm.togo", Role.DM, [self.togo])
        self.ligne = self.make_expense(amount="250000.00", title="Hôtel")
        soumis = self.submit_dossier()
        self.assertEqual(soumis.status_code, status.HTTP_200_OK, soumis.data)
        self.dossier.refresh_from_db()

    def demander(self, user=None, dossier=None, motif=MOTIF):
        self.login(user or self.owner)
        payload = {"dossier": (dossier or self.dossier).pk}
        if motif is not None:
            payload["motif"] = motif
        return self.client.post("/api/reopen-requests/", payload)

    def approuver(self, pk, user=None, note=""):
        self.login(user or self.admin)
        return self.client.post(f"/api/reopen-requests/{pk}/approve/", {"note": note})

    def refuser(self, pk, user=None, note="Le dossier est complet : le contrôle continue."):
        self.login(user or self.admin)
        payload = {"note": note} if note is not None else {}
        return self.client.post(f"/api/reopen-requests/{pk}/refuse/", payload)

    def dossier_api(self, user=None, dossier=None):
        self.login(user or self.owner)
        return self.client.get(f"/api/dossiers/{(dossier or self.dossier).pk}/").data

    def brouillon(self):
        """Un second dossier, jamais soumis."""
        return Dossier.objects.create(
            number="N-0002", label="Brouillon", country=self.togo, team=self.team,
            owner=self.manager, date=date(self.year, 3, 16),
            created_by=self.owner.username,
        )


class DemandeTests(ReouvertureDemandeeTestCase):
    def test_le_pays_demande_la_reouverture_d_un_dossier_soumis(self):
        response = self.demander()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["status"], ReopenRequest.Status.PENDING)
        self.assertEqual(response.data["requested_by"], "owner.togo")
        self.assertEqual(response.data["previous_status"], Status.SUBMITTED)
        self.assertEqual(response.data["dossier_number"], "N-0001")
        self.assertEqual(response.data["dossier_status"], Status.SUBMITTED)
        self.assertFalse(response.data["can_decide"])
        # Le dossier n'a pas bougé : seule la décision le rouvrira.
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)
        self.assertEqual(self.dossier.reopen_note, "")

    def test_le_siege_demande_aussi(self):
        """Ouverte à tous par défaut : le DM, le DF, l'administrateur."""
        for compte in (self.controller, self.dm_togo, self.admin, self.doo):
            demande = self.demander(user=compte)
            self.assertEqual(demande.status_code, status.HTTP_201_CREATED, compte)
            # Une demande à la fois : on la refuse pour laisser place à la suivante.
            self.refuser(demande.data["id"], user=self.doo if compte != self.doo else self.admin)

    def test_un_dossier_en_controle_se_demande_aussi(self):
        self.login(self.controller)
        controle = self.client.post(f"/api/dossiers/{self.dossier.pk}/review/")
        self.assertEqual(controle.status_code, status.HTTP_200_OK, controle.data)

        demande = self.demander()

        self.assertEqual(demande.status_code, status.HTTP_201_CREATED, demande.data)
        self.assertEqual(demande.data["previous_status"], Status.IN_REVIEW)

    def test_un_brouillon_n_a_rien_a_rouvrir(self):
        response = self.demander(dossier=self.brouillon())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)
        self.assertFalse(ReopenRequest.objects.exists())

    def test_un_dossier_constate_ne_se_demande_pas(self):
        """Le siège a constaté : la réouverture s'arrête là, et la demande
        avec elle — c'est une rectification qu'il faut demander."""
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.ligne.pk}/reject/", {"note": "Sans reçu"})
        rejete = self.client.post(f"/api/dossiers/{self.dossier.pk}/reject/", {"note": "Rien"})
        self.assertEqual(rejete.status_code, status.HTTP_200_OK, rejete.data)

        response = self.demander()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)
        self.assertFalse(ReopenRequest.objects.exists())

    def test_une_ligne_constatee_bloque_la_demande(self):
        """Le dossier est encore soumis, mais une ligne est justifiée : la
        réouverture serait refusée, la demande l'est donc aussi."""
        self.login(self.controller)
        justifie = self.client.post(f"/api/expenses/{self.ligne.pk}/justify/")
        self.assertEqual(justifie.status_code, status.HTTP_200_OK, justifie.data)

        response = self.demander()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expenses", response.data)
        self.assertFalse(ReopenRequest.objects.exists())

    def test_le_motif_est_obligatoire(self):
        sans = self.demander(motif=None)
        vide = self.demander(motif="   ")

        self.assertEqual(sans.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("motif", sans.data)
        self.assertEqual(vide.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("motif", vide.data)
        self.assertFalse(ReopenRequest.objects.exists())

    def test_une_seule_demande_en_attente_par_dossier(self):
        self.demander()

        seconde = self.demander(user=self.controller, motif="Autre raison.")

        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", seconde.data)
        self.assertEqual(ReopenRequest.objects.count(), 1)

    def test_apres_un_refus_une_nouvelle_demande_est_possible(self):
        premiere = self.demander()
        self.refuser(premiere.data["id"])

        seconde = self.demander(motif="La facture est arrivée depuis.")

        self.assertEqual(seconde.status_code, status.HTTP_201_CREATED, seconde.data)
        self.assertEqual(ReopenRequest.objects.count(), 2)

    def test_le_voisin_ne_voit_ni_ne_demande(self):
        """Le cloisonnement : le dossier du Togo n'existe pas pour la Côte
        d'Ivoire, ni à la demande, ni en lecture."""
        hors = self.demander(user=self.rep_ivoire)
        self.assertEqual(hors.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", hors.data)

        demande = self.demander()
        self.login(self.rep_ivoire)
        liste = self.client.get("/api/reopen-requests/")
        fiche = self.client.get(f"/api/reopen-requests/{demande.data['id']}/")
        self.assertEqual(liste.data["count"], 0)
        self.assertEqual(fiche.status_code, status.HTTP_404_NOT_FOUND)

    def test_la_demande_ne_se_modifie_ni_ne_se_supprime(self):
        demande = self.demander()
        self.login(self.doo)

        modifie = self.client.patch(
            f"/api/reopen-requests/{demande.data['id']}/", {"motif": "Autre chose"}
        )
        supprime = self.client.delete(f"/api/reopen-requests/{demande.data['id']}/")

        self.assertEqual(modifie.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(supprime.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ActionsProposeesTests(ReouvertureDemandeeTestCase):
    def test_le_dossier_propose_la_demande_tant_qu_aucune_n_attend(self):
        self.assertIn(REQUEST_REOPENING, self.dossier_api()["allowed_actions"])
        self.assertIn(REQUEST_REOPENING, self.dossier_api(self.controller)["allowed_actions"])
        self.login(self.owner)
        liste = self.client.get("/api/dossiers/").data["results"]
        self.assertIn(REQUEST_REOPENING, liste[0]["allowed_actions"])

        self.demander()

        self.assertNotIn(REQUEST_REOPENING, self.dossier_api()["allowed_actions"])
        self.assertNotIn(REQUEST_REOPENING, self.dossier_api(self.controller)["allowed_actions"])

    def test_ni_un_brouillon_ni_un_dossier_constate_ne_la_proposent(self):
        brouillon = self.brouillon()
        self.assertNotIn(REQUEST_REOPENING, self.dossier_api(dossier=brouillon)["allowed_actions"])

        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.ligne.pk}/justify/")

        # Une ligne constatée suffit : la réouverture n'est plus possible.
        self.assertNotIn(REQUEST_REOPENING, self.dossier_api()["allowed_actions"])

    def test_can_decide_dit_qui_tranche(self):
        demande = self.demander(user=self.admin)
        pk = demande.data["id"]

        def can_decide(compte):
            self.login(compte)
            return self.client.get(f"/api/reopen-requests/{pk}/").data["can_decide"]

        self.assertFalse(can_decide(self.admin), "jamais l'auteur de la demande")
        self.assertTrue(can_decide(self.doo))
        self.assertFalse(can_decide(self.owner))
        self.assertFalse(can_decide(self.controller))
        self.assertFalse(can_decide(self.dm_togo))

        self.approuver(pk, user=self.doo)
        self.assertFalse(can_decide(self.doo), "déjà tranchée")


class DecisionTests(ReouvertureDemandeeTestCase):
    def test_approuvee_le_dossier_revient_au_brouillon(self):
        demande = self.demander()

        response = self.approuver(demande.data["id"], note="D'accord, joignez la facture.")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], ReopenRequest.Status.APPROVED)
        self.assertEqual(response.data["decided_by"], "rh.admin")
        self.assertEqual(response.data["decision_note"], "D'accord, joignez la facture.")
        self.assertIsNotNone(response.data["decided_at"])
        self.assertEqual(response.data["dossier_status"], Status.DRAFT)
        self.assertEqual(response.data["previous_status"], Status.SUBMITTED)
        self.assertFalse(response.data["can_decide"])

        # La réouverture ordinaire : dossier et lignes au brouillon, sans
        # imputation, le motif de la demande gardé sur le dossier.
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.DRAFT)
        self.assertEqual(self.dossier.reopen_note, MOTIF)
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.status, Status.DRAFT)
        self.assertIsNone(self.ligne.budget)

    def test_le_pays_corrige_et_resoumet(self):
        self.approuver(self.demander().data["id"])

        resoumis = self.submit_dossier()

        self.assertEqual(resoumis.status_code, status.HTTP_200_OK, resoumis.data)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)
        # Le motif de la réouverture reste lisible après la resoumission.
        self.assertEqual(self.dossier.reopen_note, MOTIF)

    def test_refusee_le_dossier_reste_declare(self):
        demande = self.demander()

        response = self.refuser(demande.data["id"], note="Le dossier est complet.")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], ReopenRequest.Status.REFUSED)
        self.assertEqual(response.data["decision_note"], "Le dossier est complet.")
        self.assertEqual(response.data["dossier_status"], Status.SUBMITTED)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.REOPENED).exists())

    def test_le_refus_est_motive(self):
        demande = self.demander()

        sans = self.refuser(demande.data["id"], note=None)
        vide = self.refuser(demande.data["id"], note="  ")

        self.assertEqual(sans.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("note", sans.data)
        self.assertEqual(vide.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ReopenRequest.objects.get().status, ReopenRequest.Status.PENDING)

    def test_l_approbation_n_exige_pas_de_motif(self):
        response = self.approuver(self.demander().data["id"])

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["decision_note"], "")

    def test_l_auteur_de_la_demande_ne_la_tranche_pas(self):
        """Celui qui demande à rouvrir ne se l'accorde pas — même un
        administrateur."""
        demande = self.demander(user=self.admin)

        approuve = self.approuver(demande.data["id"], user=self.admin)
        refuse = self.refuser(demande.data["id"], user=self.admin)

        self.assertEqual(approuve.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(refuse.status_code, status.HTTP_403_FORBIDDEN)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)

        autre = self.approuver(demande.data["id"], user=self.doo)
        self.assertEqual(autre.status_code, status.HTTP_200_OK, autre.data)

    def test_ni_le_pays_ni_le_dm_ni_le_df_ne_decident(self):
        demande = self.demander()

        for compte in (self.owner, self.dm_togo, self.controller):
            approuve = self.approuver(demande.data["id"], user=compte)
            refuse = self.refuser(demande.data["id"], user=compte)
            self.assertEqual(approuve.status_code, status.HTTP_403_FORBIDDEN, compte)
            self.assertEqual(refuse.status_code, status.HTTP_403_FORBIDDEN, compte)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)

    def test_une_demande_tranchee_ne_se_retranche_pas(self):
        demande = self.demander()
        self.approuver(demande.data["id"])

        encore = self.approuver(demande.data["id"], user=self.doo)
        refus = self.refuser(demande.data["id"], user=self.doo)

        self.assertEqual(encore.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", encore.data)
        self.assertEqual(refus.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.REOPENED, object_type="Dossier").count(), 1
        )

    def test_un_constat_survenu_entre_temps_bloque_l_approbation(self):
        """Approuver, c'est rouvrir : les mêmes verrous, le même refus dès
        qu'une ligne a été constatée. La demande reste en attente."""
        demande = self.demander()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.ligne.pk}/justify/")

        response = self.approuver(demande.data["id"])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("expenses", response.data)
        self.assertEqual(ReopenRequest.objects.get().status, ReopenRequest.Status.PENDING)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)


class TraceEtNotificationTests(ReouvertureDemandeeTestCase):
    def test_la_demande_et_la_decision_sont_journalisees(self):
        demande = self.demander()
        self.approuver(demande.data["id"], note="D'accord.")

        demandee = AuditLog.objects.get(action=AuditLog.Action.REOPEN_REQUESTED)
        self.assertEqual(demandee.object_type, "ReopenRequest")
        self.assertEqual(demandee.object_id, demande.data["id"])
        self.assertEqual(demandee.user, "owner.togo")
        self.assertEqual(demandee.country, self.togo)
        self.assertEqual(demandee.detail["note"], MOTIF)
        self.assertEqual(demandee.detail["from_status"], Status.SUBMITTED)
        self.assertEqual(demandee.detail["dossier"], "N-0001")
        self.assertIsNotNone(demandee.ip_address)

        # La réouverture elle-même est tracée comme toute réouverture : sur
        # le dossier et sur chaque ligne, avec le motif de la demande.
        rouvert = AuditLog.objects.get(action=AuditLog.Action.REOPENED, object_type="Dossier")
        self.assertEqual(rouvert.object_id, self.dossier.pk)
        self.assertEqual(rouvert.user, "rh.admin")
        self.assertEqual(rouvert.detail["from_status"], Status.SUBMITTED)
        self.assertEqual(rouvert.detail["to_status"], Status.DRAFT)
        self.assertEqual(rouvert.detail["note"], MOTIF)
        ligne = AuditLog.objects.get(action=AuditLog.Action.REOPENED, object_type="Expense")
        self.assertEqual(ligne.object_id, self.ligne.pk)
        self.assertEqual(ligne.detail["note"], MOTIF)

        decidee = AuditLog.objects.get(action=AuditLog.Action.REOPEN_DECIDED)
        self.assertEqual(decidee.user, "rh.admin")
        self.assertEqual(decidee.detail["to_status"], ReopenRequest.Status.APPROVED)
        self.assertEqual(decidee.detail["note"], "D'accord.")

    def test_les_decideurs_sont_prevenus_de_la_demande(self):
        """Ceux qui peuvent trancher — RH et direction — apprennent la
        demande ; ni le demandeur, ni le contrôle, ni le voisin."""
        self.demander()

        demandes = Notification.objects.filter(kind=Notification.Kind.REOPEN_REQUESTED)
        for compte in (self.admin, self.doo):
            recue = demandes.filter(recipient=compte)
            self.assertEqual(recue.count(), 1, compte)
            self.assertIn("N-0001", recue.get().title)
            self.assertIn(MOTIF, recue.get().body)
            self.assertEqual(recue.get().link, f"/dossiers/{self.dossier.pk}")
        for compte in (self.owner, self.controller, self.dm_togo, self.rep_ivoire):
            self.assertFalse(demandes.filter(recipient=compte).exists(), compte)

    def test_le_demandeur_apprend_l_approbation_et_le_pays_la_reouverture(self):
        """Approuvée, la réouverture ordinaire prévient les managers du pays
        (``dossier_reopened``) ; la décision, elle, ne revient qu'au
        demandeur — pas deux fois la même nouvelle au même pays."""
        demande = self.demander(user=self.dm_togo)
        self.approuver(demande.data["id"])

        rouverts = Notification.objects.filter(kind=Notification.Kind.DOSSIER_REOPENED)
        self.assertEqual(rouverts.filter(recipient=self.owner).count(), 1)
        self.assertIn(MOTIF, rouverts.get().body)
        decisions = Notification.objects.filter(kind=Notification.Kind.REOPEN_DECIDED)
        recue = decisions.filter(recipient=self.dm_togo).get()
        self.assertIn("approuvée", recue.title)
        for compte in (self.owner, self.admin, self.doo, self.controller, self.rep_ivoire):
            self.assertFalse(decisions.filter(recipient=compte).exists(), compte)

    def test_le_demandeur_et_le_pays_apprennent_le_refus_avec_son_motif(self):
        demande = self.demander(user=self.dm_togo)
        self.refuser(demande.data["id"], note="Le dossier est complet.")

        decisions = Notification.objects.filter(kind=Notification.Kind.REOPEN_DECIDED)
        for compte in (self.dm_togo, self.owner):
            recue = decisions.filter(recipient=compte).get()
            self.assertIn("refusée", recue.title)
            self.assertIn("Le dossier est complet.", recue.body)
        for compte in (self.admin, self.doo, self.controller, self.rep_ivoire):
            self.assertFalse(decisions.filter(recipient=compte).exists(), compte)
        self.assertFalse(
            Notification.objects.filter(kind=Notification.Kind.DOSSIER_REOPENED).exists()
        )


class CourseSurLaReouvertureDemandee(CourseTestCase):
    """Deux administrateurs approuvent la même demande au même instant : une
    réouverture, une décision, le second apprend que c'est déjà fait."""

    def test_deux_approbations_simultanees(self):
        admin = self._compte("rh.innov", Role.ADMIN)
        admin_bis = self._compte("rh2.innov", Role.ADMIN)
        dossier = self._dossier("N-0010", "100000.00", statut=Status.SUBMITTED)
        demande = ReopenRequest.objects.create(
            dossier=dossier, motif="Parti trop tôt", requested_by=self.owner.username,
            previous_status=Status.SUBMITTED,
        )
        url = f"/api/reopen-requests/{demande.pk}/approve/"

        premiere, seconde = self._en_course(
            lambda: self._client(admin).post(url, {}, format="json"),
            lambda: self._client(admin_bis).post(url, {}, format="json"),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        self.assertIn("status", seconde.data)
        demande.refresh_from_db()
        self.assertEqual(demande.status, ReopenRequest.Status.APPROVED)
        self.assertEqual(demande.decided_by, "rh.innov")
        self.assertEqual(Dossier.objects.get(pk=dossier.pk).status, Status.DRAFT)
        # Dossier + sa ligne : une seule réouverture.
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.REOPENED).count(), 2)
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.REOPEN_DECIDED).count(), 1)
