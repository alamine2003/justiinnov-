"""Réouverture d'un dossier déclaré : seule exception à l'irréversibilité.

Réservée aux administrateurs, motivée, refusée dès que le siège a constaté,
tracée sur le dossier et sur chaque ligne, notifiée au pays. Elle sert à
demander des comptes, jamais à corriger en silence.
"""

from datetime import date
from decimal import Decimal

from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.aggregates import budget_figures
from expenses.models import AuditLog, Dossier
from expenses.workflow import Status
from notifications.models import Notification

from .base import ExpenseTestCase

MOTIF = "Le montant de l'hôtel ne correspond pas à la facture jointe."


class ReouvertureTestCase(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("rh.admin", Role.ADMIN)
        self.dm_togo = make_user("dm.togo", Role.DM, [self.togo])
        self.ligne = self.make_expense(amount="250000.00", title="Hôtel")
        self.autre_ligne = self.make_expense(amount="50000.00", title="Taxi")
        self.submit_dossier()

    def reopen(self, user=None, note=MOTIF, dossier=None):
        self.login(user or self.admin)
        payload = {"note": note} if note is not None else {}
        return self.client.post(
            f"/api/dossiers/{(dossier or self.dossier).pk}/reopen/", payload
        )


class ReouvertureTests(ReouvertureTestCase):
    def test_le_dossier_et_ses_lignes_reviennent_au_brouillon(self):
        response = self.reopen()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], Status.DRAFT)
        self.assertEqual(response.data["reopen_note"], MOTIF)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.DRAFT)
        for ligne in (self.ligne, self.autre_ligne):
            ligne.refresh_from_db()
            self.assertEqual(ligne.status, Status.DRAFT)
            self.assertIsNone(ligne.budget)

    def test_l_engagement_est_libere_sur_l_enveloppe(self):
        """Les lignes rouvertes ne sont plus déclarées : elles ne pèsent
        plus sur l'enveloppe, jusqu'à la resoumission."""
        self.assertEqual(budget_figures(self.budget)["engaged"], Decimal("300000.00"))

        self.reopen()

        figures = budget_figures(self.budget)
        self.assertEqual(figures["engaged"], Decimal("0.00"))
        self.assertEqual(figures["remaining"], Decimal("1000000.00"))

    def test_le_super_administrateur_rouvre_aussi(self):
        response = self.reopen(user=self.doo)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_le_pays_ne_rouvre_pas_son_propre_dossier(self):
        """Le pays se corrigerait lui-même : c'est précisément ce que la
        réouverture ne doit pas permettre."""
        for compte in (self.owner, self.dm_togo):
            response = self.reopen(user=compte)

            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, compte)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)

    def test_la_direction_financiere_ne_rouvre_pas(self):
        """Le DF constate ; il ne défait pas la déclaration du pays."""
        response = self.reopen(user=self.controller)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_motif_est_obligatoire(self):
        sans = self.reopen(note=None)
        vide = self.reopen(note="   ")

        self.assertEqual(sans.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("note", sans.data)
        self.assertEqual(vide.status_code, status.HTTP_400_BAD_REQUEST)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)

    def test_refusee_des_qu_une_ligne_est_constatee(self):
        """Une ligne justifiée est un constat du siège : il ne se défait pas.
        Le dossier, lui, est toujours « soumis » — l'état du dossier ne
        suffit donc pas, il faut regarder les lignes."""
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.ligne.pk}/justify/")

        response = self.reopen()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Hôtel", str(response.data["expenses"]))
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)
        self.autre_ligne.refresh_from_db()
        self.assertEqual(self.autre_ligne.status, Status.SUBMITTED)
        self.assertEqual(self.autre_ligne.budget, self.budget)

    def test_refusee_sur_un_dossier_justifie_ou_cloture(self):
        for etat in (Status.JUSTIFIED, Status.CLOSED):
            Dossier.objects.filter(pk=self.dossier.pk).update(status=etat)

            response = self.reopen()

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, etat)
            self.assertIn("status", response.data)

    def test_possible_depuis_en_controle_et_non_justifie(self):
        """Ni la mise en contrôle ni le constat d'absence de preuve ne sont
        un constat de justification : le dossier peut encore revenir."""
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.ligne.pk}/reject/", {"note": "Sans reçu"})
        self.client.post(f"/api/expenses/{self.autre_ligne.pk}/review/")
        self.client.post(f"/api/expenses/{self.autre_ligne.pk}/reject/", {"note": "Sans reçu"})
        self.client.post(f"/api/dossiers/{self.dossier.pk}/reject/", {"note": "Rien"})
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.UNJUSTIFIED)

        response = self.reopen()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.status, Status.DRAFT)
        # Le constat de non-justification reste lisible sur la ligne.
        self.assertEqual(self.ligne.control_note, "Sans reçu")

    def test_un_brouillon_ne_se_rouvre_pas(self):
        brouillon = Dossier.objects.create(
            number="N-0002", label="Jamais parti", country=self.togo,
            date=date(self.year, 3, 15), created_by=self.owner.username,
        )

        response = self.reopen(dossier=brouillon)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_le_pays_corrige_puis_resoumet(self):
        """La raison d'être de la réouverture : le dossier repasse par tout
        le circuit, avec ses lignes corrigées."""
        self.reopen()

        self.login(self.owner)
        corrige = self.client.patch(
            f"/api/expenses/{self.ligne.pk}/", {"amount": "200000.00"}
        )
        resoumis = self.submit_dossier()

        self.assertEqual(corrige.status_code, status.HTTP_200_OK, corrige.data)
        self.assertEqual(resoumis.status_code, status.HTTP_200_OK, resoumis.data)
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.status, Status.SUBMITTED)
        self.assertEqual(self.ligne.budget, self.budget)
        self.assertEqual(budget_figures(self.budget)["engaged"], Decimal("250000.00"))
        # Le motif reste visible après la resoumission : le siège doit voir
        # que ce dossier est déjà revenu une fois, et pourquoi.
        self.assertEqual(resoumis.data["reopen_note"], MOTIF)

    def test_le_motif_ne_se_modifie_pas_a_la_main(self):
        self.reopen()
        self.login(self.owner)

        response = self.client.patch(
            f"/api/dossiers/{self.dossier.pk}/", {"reopen_note": "Rien à signaler"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["reopen_note"], MOTIF)


class TraceDeReouvertureTests(ReouvertureTestCase):
    def test_le_dossier_et_chaque_ligne_sont_journalises(self):
        self.reopen()

        traces = AuditLog.objects.filter(action=AuditLog.Action.REOPENED)
        dossier = traces.get(object_type="Dossier")
        lignes = traces.filter(object_type="Expense")

        self.assertEqual(dossier.object_id, self.dossier.pk)
        self.assertEqual(dossier.user, "rh.admin")
        self.assertEqual(dossier.country, self.togo)
        self.assertEqual(dossier.detail["note"], MOTIF)
        self.assertEqual(dossier.detail["from_status"], Status.SUBMITTED)
        self.assertEqual(dossier.detail["to_status"], Status.DRAFT)
        self.assertEqual(dossier.detail["after"]["reopen_note"], MOTIF)
        self.assertIsNotNone(dossier.ip_address)

        self.assertEqual(lignes.count(), 2)
        trace = lignes.get(object_id=self.ligne.pk)
        self.assertEqual(trace.user, "rh.admin")
        self.assertEqual(trace.detail["note"], MOTIF)
        self.assertEqual(trace.detail["before"]["budget"], self.budget.pk)
        self.assertIsNone(trace.detail["after"]["budget"])
        self.assertEqual(trace.detail["dossier"], "N-0001")

    def test_l_historique_des_reouvertures_se_lit_dans_le_journal(self):
        """Deux réouvertures, deux motifs : la fiche ne garde que le dernier,
        le journal garde tout."""
        self.reopen(note="Premier motif")
        self.submit_dossier()
        self.reopen(note="Second motif")

        motifs = list(
            AuditLog.objects.filter(
                action=AuditLog.Action.REOPENED, object_type="Dossier"
            ).order_by("pk").values_list("detail__note", flat=True)
        )
        self.assertEqual(motifs, ["Premier motif", "Second motif"])
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.reopen_note, "Second motif")

    def test_le_pays_est_prevenu_avec_le_motif(self):
        """Le DM et les managers du pays apprennent que le dossier leur
        revient, et pourquoi. L'administrateur qui rouvre n'est pas averti,
        et le siège non plus : ce n'est pas à lui d'agir."""
        self.reopen()

        # La soumission a déjà prévenu le siège : seules les notifications
        # de réouverture comptent ici.
        rouvertures = Notification.objects.filter(title__startswith="Dossier rouvert")
        for compte in (self.owner, self.dm_togo):
            recues = rouvertures.filter(recipient=compte)
            self.assertEqual(recues.count(), 1, compte)
            notification = recues.get()
            self.assertIn("N-0001", notification.title)
            self.assertIn(MOTIF, notification.body)
            self.assertEqual(notification.link, f"/dossiers/{self.dossier.pk}")
        self.assertFalse(rouvertures.filter(recipient=self.admin).exists())
        self.assertFalse(rouvertures.filter(recipient=self.controller).exists())
        self.assertFalse(rouvertures.filter(recipient=self.rep_ivoire).exists())

    def test_une_ligne_ne_se_rouvre_pas_seule(self):
        """Comme la soumission, la réouverture porte sur le dossier."""
        self.login(self.admin)

        response = self.client.post(f"/api/expenses/{self.ligne.pk}/reopen/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.status, Status.SUBMITTED)
