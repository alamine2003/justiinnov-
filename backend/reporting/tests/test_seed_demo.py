"""Jeu de démonstration : idempotent, produit par les actions réelles."""

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from budget.models import Budget, ExchangeRate
from core.models import ChangeLog, Country, Team
from expenses.models import AuditLog, Dossier, Expense, Proof
from expenses.tests.base import in_memory_storage
from expenses.workflow import Status
from notifications.models import Notification
from reporting.management.commands.seed_demo import ACTEUR, TEMOIN


@in_memory_storage
class SeedDemoTests(TestCase):
    def _etat(self):
        return {
            modele.__name__: modele.objects.count()
            for modele in (
                Country, Team, Budget, ExchangeRate, User, Dossier, Expense, Proof,
                AuditLog, ChangeLog, Notification,
            )
        }

    def _lancer(self):
        sortie = StringIO()
        call_command("seed_demo", "--base-jetable", stdout=sortie)
        return sortie.getvalue()

    def test_sans_drapeau_la_commande_refuse_avant_d_ecrire(self):
        """Rien ne se supprime : un jeu de démonstration lancé par mégarde
        sur une base réelle y resterait. Le drapeau est donc explicite."""
        avant = self._etat()

        with self.assertRaisesMessage(CommandError, "--base-jetable"):
            call_command("seed_demo")

        self.assertEqual(self._etat(), avant)
        self.assertFalse(Dossier.objects.filter(number=TEMOIN).exists())

    def test_deux_executions_meme_etat(self):
        self._lancer()
        etat = self._etat()

        sortie = self._lancer()

        self.assertEqual(self._etat(), etat)
        self.assertIn("rien à faire", sortie)

    def test_les_dossiers_sont_dans_les_etats_annonces(self):
        self._lancer()

        etats = dict(
            Dossier.objects.filter(number__startswith="DEMO-").values_list("number", "status")
        )
        self.assertEqual(
            etats,
            {
                TEMOIN: Status.DRAFT,
                "DEMO-0002": Status.SUBMITTED,
                "DEMO-0003": Status.SUBMITTED,
                "DEMO-0004": Status.SUBMITTED,
            },
        )
        partiel = Dossier.objects.get(number="DEMO-0003")
        self.assertEqual(
            sorted(partiel.expenses.values_list("status", flat=True)),
            sorted([Status.JUSTIFIED, Status.JUSTIFIED, Status.SUBMITTED]),
        )
        totaux = partiel.totals()
        self.assertGreater(totaux["justified"], 0)
        self.assertGreater(totaux["gap"], 0)
        self.assertEqual(
            Dossier.objects.get(number="DEMO-0004").expenses.get().status,
            Status.UNJUSTIFIED,
        )
        # Rouvert puis resoumis : le motif reste lisible, la pièce a une
        # seconde version et la première est archivée.
        rouvert = Dossier.objects.get(number="DEMO-0002")
        self.assertIn("illisible", rouvert.reopen_note)
        self.assertEqual(
            sorted(rouvert.proofs.values_list("status", flat=True)),
            [Proof.ProofStatus.ARCHIVED, Proof.ProofStatus.RECEIVED],
        )
        self.assertFalse(Dossier.objects.get(number=TEMOIN).proofs.exists())
        self.assertEqual(Country.objects.filter(code__in=["TG", "CI"]).count(), 2)
        self.assertTrue(Expense.objects.filter(original_currency="EUR").exists())

    def test_les_traces_viennent_des_actions_reelles(self):
        self._lancer()

        actions = set(AuditLog.objects.values_list("action", flat=True))
        self.assertLessEqual(
            {
                AuditLog.Action.CREATED, AuditLog.Action.SUBMITTED,
                AuditLog.Action.REOPENED, AuditLog.Action.JUSTIFIED,
                AuditLog.Action.UNJUSTIFIED, AuditLog.Action.PROOF_UPLOADED,
                AuditLog.Action.PROOF_REPLACED,
            },
            actions,
        )
        self.assertTrue(AuditLog.objects.filter(user="demo.controle").exists())
        self.assertTrue(ChangeLog.objects.filter(performed_by=ACTEUR).exists())
        self.assertTrue(
            Notification.objects.filter(
                recipient__username="demo.pays", kind=Notification.Kind.DOSSIER_REOPENED
            ).exists()
        )

    def test_les_comptes_de_demonstration_ne_se_connectent_pas(self):
        self._lancer()

        for username in ("demo.pays", "demo.controle", "demo.direction"):
            user = User.objects.get(username=username)
            self.assertFalse(user.has_usable_password(), username)
            self.assertEqual(user.email, "")

    def test_un_pays_deja_cree_est_reutilise(self):
        Country.objects.create(
            name="Togo", code="TG", country_ref="TG-01", currency="XOF",
            timezone="Africa/Lome",
        )

        self._lancer()

        self.assertEqual(Country.objects.filter(code="TG").count(), 1)
        self.assertTrue(Dossier.objects.filter(number=TEMOIN, country__code="TG").exists())

    def test_rien_ne_se_supprime_pas_meme_la_demonstration(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", "--reset")
