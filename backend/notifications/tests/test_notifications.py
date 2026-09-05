"""Notifications : cloisonnement par destinataire, dédoublonnage, e-mails."""

from decimal import Decimal
from pathlib import Path
from unittest import mock

from datetime import date

from django.contrib.auth.models import User
from django.core import mail
from django.db.models import ProtectedError
from django.core.management import call_command
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy
from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.models import Budget, BudgetReallocation
from core.management.commands.run_scheduler import JOBS
from core.models import Team
from expenses.models import Dossier
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
        restreint = make_user("controle.togo", Role.DF, [self.togo])

        togo = set(recipients_for([Role.DF], self.togo))
        ivoire = set(recipients_for([Role.DF], self.ivoire))

        self.assertIn(restreint, togo)
        self.assertNotIn(restreint, ivoire)
        # Le contrôleur sans périmètre couvre les deux.
        self.assertIn(self.controller, togo & ivoire)

    def test_un_role_toujours_global_couvre_tout(self):
        admin = make_user("admin.innov", Role.ADMIN, [self.togo])

        self.assertIn(admin, set(recipients_for([Role.ADMIN], self.ivoire)))

    def test_sans_pays_tous_les_comptes_du_role_sont_renvoyes(self):
        restreint = make_user("controle.togo", Role.DF, [self.togo])

        tous = set(recipients_for([Role.DF]))

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
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.controller.email = "dina@example.org"
        cls.controller.save()
        cls.doo.email = "doo@example.org"
        cls.doo.save()

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

    def test_une_reouverture_previent_ceux_qui_ont_declare(self):
        """Seule exception à l'irréversibilité : le dossier revient au pays,
        avec le motif, sous un type qui lui est propre. Les managers du pays
        sont prévenus ; le DM, au siège, non ; le voisin, non ;
        l'administrateur qui rouvre, pas davantage."""
        dm_togo = make_user("dm.togo", Role.DM, [self.togo])
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()

        triggers.dossier_reopened(self.dossier, self.doo, "Facture illisible")

        notification = Notification.objects.get(recipient=self.owner)
        self.assertEqual(notification.kind, Notification.Kind.DOSSIER_REOPENED)
        self.assertEqual(notification.level, Notification.Level.WARNING)
        self.assertIn("N-0001", notification.title)
        self.assertIn("Facture illisible", notification.body)
        self.assertEqual(notification.link, f"/dossiers/{self.dossier.pk}")
        for absent in (dm_togo, self.rep_ivoire, self.doo):
            self.assertFalse(Notification.objects.filter(recipient=absent).exists(), absent)

    def test_une_soumission_previent_le_dm_et_le_df_du_pays(self):
        """Le contrôle est au siège, en deux temps : le DM qui mettra en
        contrôle et le DF qui tranchera sont prévenus — chacun sur son
        périmètre, et jamais le manager qui a soumis."""
        dm_togo = make_user("dm.togo", Role.DM, [self.togo])
        dm_ivoire = make_user("dm.ivoire", Role.DM, [self.ivoire])
        self.make_expense(amount="1000.00")

        self.submit_dossier()

        soumissions = Notification.objects.filter(kind=Notification.Kind.EXPENSE_SUBMITTED)
        self.assertEqual(
            set(soumissions.values_list("recipient__username", flat=True)),
            {dm_togo.username, self.controller.username, self.doo.username},
        )
        self.assertFalse(soumissions.filter(recipient=dm_ivoire).exists())
        self.assertFalse(soumissions.filter(recipient=self.owner).exists())

    def test_le_type_dossier_rouvert_se_traduit(self):
        from django.utils import translation

        (notification,) = self.notifier(
            [self.controller], kind=Notification.Kind.DOSSIER_REOPENED
        )

        self.assertEqual(notification.get_kind_display(), "Dossier rouvert")
        with translation.override("en"):
            self.assertEqual(notification.get_kind_display(), "Dossier reopened")

    def test_le_declencheur_de_ligne_soumise_a_disparu(self):
        """Une ligne ne se soumet plus seule : le dossier part en une action."""
        self.assertFalse(hasattr(triggers, "expense_submitted"))


class LangueTests(NotificationTestCase):
    """Chaque destinataire lit sa notification et son e-mail dans sa langue."""

    TITRE = format_lazy(gettext_lazy("Justificatif manquant — {number}"), number="N-0001")
    CORPS = gettext_lazy("Aucune donnée sur la période.")

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.controller.email = "dina@example.org"
        cls.controller.save()

    def test_a_defaut_la_langue_est_le_francais(self):
        sans_profil = User.objects.create_user("sans.profil")

        self.assertEqual(services.langue_de(self.controller), "fr")
        self.assertEqual(services.langue_de(sans_profil), "fr")

    def anglophone(self, user):
        user.profile.language = "en"
        user.profile.save()

    def test_le_message_est_rendu_dans_la_langue_du_destinataire(self):
        self.anglophone(self.controller)

        (notification,) = self.notifier(
            [self.controller], title=self.TITRE, body=self.CORPS
        )

        self.assertEqual(notification.title, "Missing supporting document — N-0001")
        self.assertEqual(notification.body, "No data for the period.")
        self.assertEqual(
            mail.outbox[0].subject, "[Budget control] Missing supporting document — N-0001"
        )
        self.assertIn("No data for the period.", mail.outbox[0].body)
        # Le processus émetteur, lui, reste en français.
        self.assertEqual(str(self.TITRE), "Justificatif manquant — N-0001")

    def test_deux_destinataires_deux_langues(self):
        self.doo.email = "doo@example.org"
        self.doo.save()
        self.anglophone(self.controller)

        self.notifier([self.controller, self.doo], title=self.TITRE)

        titres = dict(
            Notification.objects.values_list("recipient__username", "title")
        )
        self.assertEqual(titres["rh.innov"], "Missing supporting document — N-0001")
        self.assertEqual(titres["do.innov"], "Justificatif manquant — N-0001")
        sujets = {m.to[0]: m.subject for m in mail.outbox}
        self.assertTrue(sujets["dina@example.org"].startswith("[Budget control]"))
        self.assertTrue(sujets["doo@example.org"].startswith("[Contrôle budgétaire]"))

    def test_une_alerte_notifiee_est_rendue_dans_la_langue_du_destinataire(self):
        """De bout en bout : l'alerte calculée par l'ordonnanceur arrive en
        anglais chez un destinataire anglophone."""
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()
        self.anglophone(self.controller)

        call_command("notify_alerts", year=self.year, verbosity=0)

        notification = Notification.objects.get(
            recipient=self.controller, kind=Notification.Kind.PROOF_MISSING
        )
        self.assertEqual(notification.title, "Missing supporting document — N-0001")
        self.assertIn("without any proof", notification.body)

    def test_la_langue_vient_du_profil(self):
        self.controller.profile.language = "en"
        self.controller.profile.save()

        (notification,) = self.notifier([self.controller], title=self.TITRE)

        self.assertEqual(notification.title, "Missing supporting document — N-0001")
        self.assertTrue(mail.outbox[0].subject.startswith("[Budget control]"))


class ConservationTests(NotificationTestCase):
    """Rien ne se supprime : une notification lue reste en base."""

    def test_une_notification_lue_reste_en_base(self):
        (notification,) = self.notifier([self.controller])
        self.login(self.controller)

        self.client.post("/api/notifications/read-all/")

        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertEqual(Notification.objects.count(), 1)

    def test_aucune_tache_planifiee_ne_purge(self):
        for job in JOBS:
            self.assertNotRegex(job["id"], r"purge|clean|prune|delete|expire")
            self.assertNotRegex(job["command"][0], r"purge|clean|prune|delete|expire")

    def test_aucune_commande_ne_supprime(self):
        """Pièces, dossiers, dépenses, notifications, journal : conservation
        illimitée. Une commande qui supprimerait serait attrapée ici."""
        racine = Path(__file__).resolve().parents[2]
        commandes = [
            source
            for app in ("reporting", "notifications", "core", "expenses")
            for source in (racine / app / "management" / "commands").glob("*.py")
        ]
        self.assertTrue(commandes)
        for source in commandes:
            with self.subTest(commande=source.name):
                self.assertNotIn(".delete(", source.read_text(encoding="utf-8"))


class DeclencheursBilinguesTests(NotificationTestCase):
    """Les déclencheurs passent des chaînes paresseuses : un destinataire
    anglophone lit un titre anglais, son voisin francophone un titre
    français, pour le même événement."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.controller.profile.language = "en"
        cls.controller.profile.save()
        # Un second manager du Togo, anglophone : la réouverture revient au
        # pays, et chacun de ses managers la lit dans sa langue.
        cls.manager_en = make_user("kojo.togo", Role.MANAGER, [cls.togo])
        cls.manager_en.profile.language = "en"
        cls.manager_en.profile.save()
        cls.make_expense(cls, amount="1000.00")

    def test_la_soumission_arrive_en_anglais(self):
        self.submit_dossier()

        anglais = Notification.objects.get(recipient=self.controller)
        francais = Notification.objects.get(recipient=self.doo)
        self.assertEqual(anglais.title, "Dossier to review — N-0001")
        self.assertIn("on 1 line(s)", anglais.body)
        self.assertEqual(francais.title, "Dossier à contrôler — N-0001")

    def test_la_reouverture_arrive_en_anglais(self):
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()

        triggers.dossier_reopened(self.dossier, self.doo, "Facture illisible")

        anglais = Notification.objects.get(recipient=self.manager_en)
        francais = Notification.objects.get(recipient=self.owner)
        self.assertEqual(anglais.title, "Dossier reopened — N-0001")
        self.assertIn("Reason: Facture illisible", anglais.body)
        self.assertEqual(francais.title, "Dossier rouvert — N-0001")
        self.assertIn("Motif : Facture illisible", francais.body)


class EquipesTests(NotificationTestCase):
    """Un manager rattaché à des équipes n'est prévenu que de ce qui touche
    les siennes ; le siège, jamais cloisonné par équipe, reçoit tout."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.kara = Team.objects.create(country=cls.togo, name="Équipe Kara")
        cls.manager_lome = make_user(
            "lome.togo", Role.MANAGER, [cls.togo], teams=[cls.team]
        )
        cls.dossier_kara = Dossier.objects.create(
            number="N-KARA", label="Tournée de Kara", country=cls.togo,
            team=cls.kara, owner=cls.manager, date=date(cls.year, 4, 1),
            status=Status.SUBMITTED, created_by=cls.owner.username,
        )

    def test_recipients_for_cloisonne_les_managers_par_equipe(self):
        lome = set(recipients_for([Role.MANAGER], self.togo, self.team))
        kara = set(recipients_for([Role.MANAGER], self.togo, self.kara))
        pays = set(recipients_for([Role.MANAGER], self.togo))

        self.assertIn(self.manager_lome, lome)
        self.assertNotIn(self.manager_lome, kara)
        # Sans équipe rattachée, le manager couvre tout son pays.
        self.assertIn(self.owner, kara)
        # Sans équipe demandée — une alerte d'enveloppe — tout le pays.
        self.assertEqual(pays, {self.owner, self.manager_lome})

    def test_le_siege_ignore_les_equipes(self):
        """Une équipe posée sur le profil d'un DF ne porte aucun droit."""
        df_lome = make_user("df.lome", Role.DF, [self.togo], teams=[self.team])

        self.assertIn(df_lome, set(recipients_for([Role.DF], self.togo, self.kara)))
        self.assertIn(self.controller, set(recipients_for([Role.DF], self.togo, self.kara)))

    def test_une_reouverture_a_kara_ne_previent_pas_le_manager_de_lome(self):
        triggers.dossier_reopened(self.dossier_kara, self.doo, "Pièce manquante")

        self.assertFalse(Notification.objects.filter(recipient=self.manager_lome).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.owner).exists())

    def test_une_reouverture_a_lome_le_previent(self):
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()

        triggers.dossier_reopened(self.dossier, self.doo, "Pièce manquante")

        self.assertTrue(Notification.objects.filter(recipient=self.manager_lome).exists())

    def test_une_soumission_ne_depend_pas_de_l_equipe_pour_le_siege(self):
        dm_togo = make_user("dm.togo", Role.DM, [self.togo])

        triggers.dossier_submitted(self.dossier_kara, self.owner)

        self.assertTrue(Notification.objects.filter(recipient=dm_togo).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.controller).exists())


class ReouvertureTests(NotificationTestCase):
    def test_deux_reouvertures_le_meme_jour_notifient_deux_fois(self):
        """La clé porte l'instant de la réouverture, pas le jour : le pays
        apprend chaque motif, y compris le second."""
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()
        triggers.dossier_reopened(self.dossier, self.doo, "Première demande")

        # Resoumis puis rouvert de nouveau : ``updated_at`` a bougé.
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()
        triggers.dossier_reopened(self.dossier, self.doo, "Seconde demande")

        motifs = [
            n.body for n in Notification.objects.filter(
                recipient=self.owner, kind=Notification.Kind.DOSSIER_REOPENED
            )
        ]
        self.assertEqual(len(motifs), 2)
        self.assertTrue(any("Seconde" in motif for motif in motifs))

    def test_rejouer_la_meme_reouverture_ne_notifie_qu_une_fois(self):
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()

        triggers.dossier_reopened(self.dossier, self.doo, "Même demande")
        triggers.dossier_reopened(self.dossier, self.doo, "Même demande")

        self.assertEqual(
            Notification.objects.filter(
                recipient=self.owner, kind=Notification.Kind.DOSSIER_REOPENED
            ).count(),
            1,
        )


class PaysProtegeTests(NotificationTestCase):
    def test_un_pays_notifie_ne_se_supprime_pas(self):
        """La notification atteste pour quel pays quelqu'un a été prévenu :
        le pays se désactive, il ne disparaît pas sous elle."""
        self.notifier([self.controller])

        with self.assertRaises(ProtectedError):
            self.togo.delete()
