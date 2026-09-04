"""Notifications : cloisonnement par destinataire, dédoublonnage, e-mails."""

from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.management import call_command
from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.models import Budget, BudgetReallocation
from expenses.tests.base import ExpenseTestCase
from expenses.workflow import Status
from notifications import services, triggers
from notifications.models import Notification
from notifications.services import notify, recipients_for


class NotificationTestCase(ExpenseTestCase):
    def notifier(self, recipients, cle="evenement:1", **extra):
        options = {
            "kind": Notification.Kind.PROOF_MISSING,
            "title": "Justificatif manquant — N-0001",
            "dedup_key": cle,
            "country": self.togo,
        }
        options.update(extra)
        return notify(recipients, **options)


class CloisonnementTests(NotificationTestCase):
    def test_chacun_ne_voit_que_les_siennes(self):
        self.notifier([self.controller], cle="controle:1", link="/dossiers/1")
        self.notifier([self.rep_ivoire], cle="ivoire:1", country=self.ivoire, link="/dossiers/2")

        self.login(self.controller)
        mine = self.client.get("/api/notifications/")
        self.login(self.rep_ivoire)
        theirs = self.client.get("/api/notifications/")

        self.assertEqual([n["link"] for n in mine.data["results"]], ["/dossiers/1"])
        self.assertEqual([n["link"] for n in theirs.data["results"]], ["/dossiers/2"])

    def test_la_notification_d_autrui_repond_404(self):
        """Ni lecture ni marquage : l'objet n'existe pas pour un autre."""
        (notification,) = self.notifier([self.controller])
        self.login(self.rep_ivoire)

        lecture = self.client.get(f"/api/notifications/{notification.pk}/")
        marquage = self.client.post(f"/api/notifications/{notification.pk}/read/")

        self.assertEqual(lecture.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(marquage.status_code, status.HTTP_404_NOT_FOUND)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_un_pays_ne_recoit_jamais_l_alerte_d_un_autre(self):
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()

        call_command("notify_alerts", year=self.year, verbosity=0)

        self.assertTrue(Notification.objects.filter(recipient=self.owner).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.rep_ivoire).exists())

    def test_la_cle_d_unicite_est_indexee(self):
        champs = [tuple(index.fields) for index in Notification._meta.indexes]
        self.assertIn(("dedup_key",), champs)


class DestinatairesTests(NotificationTestCase):
    def test_un_siege_restreint_ne_couvre_que_son_perimetre(self):
        """Un contrôleur limité au Togo n'est pas concerné par Abidjan."""
        restreint = make_user("controle.togo", Role.CONTROLLER, [self.togo])

        togo = set(recipients_for([Role.CONTROLLER], self.togo))
        ivoire = set(recipients_for([Role.CONTROLLER], self.ivoire))

        self.assertIn(restreint, togo)
        self.assertNotIn(restreint, ivoire)
        # Le contrôleur sans périmètre couvre les deux.
        self.assertIn(self.controller, togo & ivoire)

    def test_un_role_toujours_global_couvre_tout(self):
        admin = make_user("admin.innov", Role.ADMIN, [self.togo])

        self.assertIn(admin, set(recipients_for([Role.ADMIN], self.ivoire)))

    def test_sans_pays_tous_les_comptes_du_role_sont_renvoyes(self):
        restreint = make_user("controle.togo", Role.CONTROLLER, [self.togo])

        tous = set(recipients_for([Role.CONTROLLER]))

        self.assertEqual(tous, {self.controller, restreint})


class DedoublonnageTests(NotificationTestCase):
    def test_un_meme_evenement_ne_notifie_qu_une_fois(self):
        self.notifier([self.controller])
        self.notifier([self.controller])

        self.assertEqual(Notification.objects.filter(recipient=self.controller).count(), 1)

    def test_deux_processus_simultanes_ne_doublent_ni_la_ligne_ni_l_e_mail(self):
        """L'ordonnanceur et une requête web notifient le même événement au
        même instant : la contrainte tranche la ligne, et ``emailed_at``
        réclamé avant l'envoi tranche l'e-mail."""
        self.controller.email = "dina@example.org"
        self.controller.save()
        self.notifier([self.controller])
        self.assertEqual(len(mail.outbox), 1)

        # Le second processus a lu « personne d'averti » avant que le premier
        # n'écrive : on rejoue son passage avec cette lecture périmée.
        with mock.patch.object(services, "_deja_avertis", return_value=set()):
            self.notifier([self.controller])

        self.assertEqual(Notification.objects.filter(recipient=self.controller).count(), 1)
        self.assertEqual(len(mail.outbox), 1)


class EmailTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        self.controller.email = "dina@example.org"
        self.controller.save()
        self.doo.email = "doo@example.org"
        self.doo.save()

    def test_un_message_par_destinataire(self):
        """Un envoi groupé exposait à chacun l'adresse des autres."""
        self.notifier([self.controller, self.doo])

        self.assertEqual(len(mail.outbox), 2)
        for message in mail.outbox:
            self.assertEqual(len(message.to), 1)
        self.assertEqual(
            {m.to[0] for m in mail.outbox}, {"dina@example.org", "doo@example.org"}
        )

    def test_le_sujet_tient_sur_une_ligne(self):
        self.notifier([self.controller], title="Dépense\r\nBcc: pirate@example.org")

        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("\n", mail.outbox[0].subject)
        self.assertIn("Dépense Bcc: pirate@example.org", mail.outbox[0].subject)

    def test_l_horodatage_d_envoi_est_pose(self):
        (notification,) = self.notifier([self.controller])

        self.assertIsNotNone(notification.emailed_at or Notification.objects.get(pk=notification.pk).emailed_at)

    def test_une_panne_d_envoi_ne_pretend_pas_avoir_envoye(self):
        with mock.patch.object(
            services.EmailMessage, "send", side_effect=OSError("SMTP HS")
        ), self.assertLogs("notifications.services", level="ERROR"):
            (notification,) = self.notifier([self.controller])

        notification.refresh_from_db()
        self.assertIsNone(notification.emailed_at)


class DeclencheursTests(NotificationTestCase):
    def test_une_demande_de_reallocation_previent_les_arbitres(self):
        projet_budget = Budget.objects.create(
            country=self.togo, year=self.year, amount=Decimal("100000.00"),
            team=self.team,
        )
        demande = BudgetReallocation.objects.create(
            source=self.budget, target=projet_budget, amount=Decimal("25000.00"),
            reason="Renfort de l'équipe", requested_by=self.owner.username,
        )

        triggers.reallocation_requested(demande, self.owner)

        notification = Notification.objects.get(recipient=self.doo)
        self.assertEqual(notification.kind, Notification.Kind.REALLOCATION_REQUESTED)
        self.assertIn("25000.00", notification.body)
        self.assertIn("Renfort", notification.body)
        # Le pays est averti de l'état de son enveloppe, pas de l'arbitrage.
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())

    def test_le_declencheur_de_ligne_soumise_a_disparu(self):
        """Une ligne ne se soumet plus seule : le dossier part en une action."""
        self.assertFalse(hasattr(triggers, "expense_submitted"))
