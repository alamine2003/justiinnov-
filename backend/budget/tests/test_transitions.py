"""Les services de réallocation (``budget.transitions``), sans client HTTP.

Les tests des vues (``test_budgets``, ``test_verrous``) restent le filet du
contrat ; ceux-ci exercent les règles là où elles vivent désormais : rôle,
motif, disponible, auto-décision, périmètre, journal.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role
from accounts.permissions import Access, get_access
from accounts.tests.test_scoping import make_user
from budget import transitions
from budget.models import Budget, BudgetReallocation
from core.journal import Trace
from core.models import ChangeLog, Country, Project
from core.regles import HorsPerimetre, PermissionRefusee, RegleViolee
from expenses.models import AuditLog, Dossier, Expense
from expenses.workflow import Status
from notifications.models import Notification

ADRESSE = "41.79.0.10"


def trace(user):
    return Trace(user=user.username, ip=ADRESSE, user_agent="Test", compte=user)


class ServicesDeReallocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        cls.ivoire = Country.objects.create(
            name="Côte d'Ivoire", code="CI", country_ref="CT-01",
            currency="XOF", timezone="Africa/Abidjan",
        )
        cls.source = Budget.objects.create(
            country=cls.togo, year=2026, amount=Decimal("10000000.00")
        )
        projet = Project.objects.create(country=cls.togo, name="Projet TG")
        cls.cible = Budget.objects.create(
            country=cls.togo, year=2026, project=projet, amount=Decimal("0.00")
        )
        cls.ivoirienne = Budget.objects.create(
            country=cls.ivoire, year=2026, amount=Decimal("1000000.00")
        )
        cls.siege = make_user("ceo.innov", Role.SUPER_ADMIN)
        cls.doo = make_user("do.innov", Role.SUPER_ADMIN)
        cls.df = make_user("df.innov", Role.DF)

    def demander(self, montant="1000000.00", motif="Renfort", par=None, cible=None):
        par = par or self.siege
        return transitions.demander(
            self.source, cible or self.cible, Decimal(montant), motif,
            get_access(par), trace(par),
        )

    def imputer(self, montant, statut=Status.SUBMITTED):
        dossier = Dossier.objects.create(
            number=f"D-{Expense.objects.count() + 1:04d}", label="Mission",
            country=self.togo, date=date(2026, 3, 1), status=Status.SUBMITTED,
        )
        return Expense.objects.create(
            dossier=dossier, country=self.togo, budget=self.source,
            date=timezone.now(), title="Carburant",
            amount=Decimal(montant), status=statut,
        )

    # -- Demande ----------------------------------------------------------------

    def test_demander_cree_journalise_et_previent(self):
        resultat = self.demander()

        demande = resultat.instance
        self.assertEqual(demande.status, BudgetReallocation.Status.PENDING)
        self.assertEqual(demande.requested_by, "ceo.innov")
        entree = resultat.audit[0]
        self.assertEqual(entree.action, AuditLog.Action.CREATED)
        self.assertEqual(entree.object_type, "BudgetReallocation")
        self.assertEqual(entree.country, self.togo)
        self.assertEqual(entree.detail["amount"], "1000000.00")
        # Les arbitres sont prévenus, sauf celui qui demande.
        destinataires = set(
            Notification.objects.filter(
                kind=Notification.Kind.REALLOCATION_REQUESTED
            ).values_list("recipient__username", flat=True)
        )
        self.assertEqual(destinataires, {"do.innov"})

    def test_demander_exige_un_motif(self):
        with self.assertRaises(RegleViolee) as refus:
            self.demander(motif="   ")

        self.assertEqual(refus.exception.champ, "reason")

    def test_demander_exige_le_disponible(self):
        self.imputer("9500000.00")

        with self.assertRaises(RegleViolee) as refus:
            self.demander("1000000.00")

        self.assertEqual(refus.exception.champ, "amount")
        self.assertFalse(BudgetReallocation.objects.exists())

    def test_demander_exige_la_meme_devise_et_deux_enveloppes(self):
        self.ivoire.currency = "MAD"
        self.ivoire.save()

        with self.assertRaises(RegleViolee) as devise:
            self.demander(cible=self.ivoirienne)
        with self.assertRaises(RegleViolee) as meme:
            self.demander(cible=self.source)

        self.assertEqual(devise.exception.champ, "target")
        self.assertEqual(meme.exception.champ, "target")

    def test_le_df_ne_demande_ni_ne_decide(self):
        demande = self.demander().instance

        with self.assertRaises(PermissionRefusee):
            self.demander(par=self.df)
        with self.assertRaises(PermissionRefusee):
            transitions.approuver(demande, get_access(self.df), "", trace(self.df))
        with self.assertRaises(PermissionRefusee):
            transitions.refuser(demande, get_access(self.df), "Non", trace(self.df))

    # -- Décision ---------------------------------------------------------------

    def test_approuver_transfere_les_montants_et_journalise(self):
        demande = self.demander().instance

        resultat = transitions.approuver(
            demande, get_access(self.doo), "D'accord", trace(self.doo)
        )

        self.source.refresh_from_db()
        self.cible.refresh_from_db()
        self.assertEqual(self.source.amount, Decimal("9000000.00"))
        self.assertEqual(self.cible.amount, Decimal("1000000.00"))
        self.assertEqual(resultat.instance.status, BudgetReallocation.Status.APPROVED)
        self.assertEqual(resultat.instance.decided_by, "do.innov")
        self.assertIsNotNone(resultat.instance.decided_at)
        entree = resultat.audit[0]
        self.assertEqual(entree.action, AuditLog.Action.UPDATED)
        self.assertEqual(entree.detail["from_status"], "pending")
        self.assertEqual(entree.detail["to_status"], "approved")
        self.assertEqual(entree.detail["note"], "D'accord")
        # Le mouvement des enveloppes, lui, reste dans l'historique.
        self.assertEqual(
            ChangeLog.objects.filter(
                model_name=ChangeLog.Models.BUDGET, action=ChangeLog.Actions.UPDATED
            ).count(),
            2,
        )

    def test_auto_approbation_refusee(self):
        demande = self.demander(par=self.doo).instance

        with self.assertRaises(PermissionRefusee):
            transitions.approuver(demande, get_access(self.doo), "", trace(self.doo))
        with self.assertRaises(PermissionRefusee):
            transitions.refuser(demande, get_access(self.doo), "Non", trace(self.doo))

        demande.refresh_from_db()
        self.assertEqual(demande.status, BudgetReallocation.Status.PENDING)

    def test_approuver_reverifie_le_disponible(self):
        """Une dépense peut sortir entre la demande et la décision."""
        demande = self.demander("1000000.00").instance
        self.imputer("9500000.00")

        with self.assertRaises(RegleViolee) as refus:
            transitions.approuver(demande, get_access(self.doo), "", trace(self.doo))

        self.assertEqual(refus.exception.champ, "amount")
        self.source.refresh_from_db()
        self.assertEqual(self.source.amount, Decimal("10000000.00"))
        demande.refresh_from_db()
        self.assertEqual(demande.status, BudgetReallocation.Status.PENDING)

    def test_refuser_exige_un_motif(self):
        demande = self.demander().instance

        with self.assertRaises(RegleViolee) as refus:
            transitions.refuser(demande, get_access(self.doo), " ", trace(self.doo))

        self.assertEqual(refus.exception.champ, "note")

    def test_refuser_motive_journalise(self):
        demande = self.demander().instance

        resultat = transitions.refuser(
            demande, get_access(self.doo), "Hors priorité", trace(self.doo)
        )

        self.assertEqual(resultat.instance.status, BudgetReallocation.Status.REJECTED)
        self.assertEqual(resultat.instance.decision_note, "Hors priorité")
        self.assertEqual(resultat.audit[0].detail["to_status"], "rejected")
        self.source.refresh_from_db()
        self.assertEqual(self.source.amount, Decimal("10000000.00"))

    def test_une_reallocation_traitee_ne_se_decide_plus(self):
        demande = self.demander().instance
        transitions.approuver(demande, get_access(self.doo), "", trace(self.doo))

        with self.assertRaises(RegleViolee) as refus:
            transitions.approuver(demande, get_access(self.doo), "", trace(self.doo))

        self.assertEqual(refus.exception.champ, "status")
        self.source.refresh_from_db()
        self.assertEqual(self.source.amount, Decimal("9000000.00"))

    def test_la_destination_hors_perimetre_n_existe_pas(self):
        """Aucun décideur n'est restreint aujourd'hui ; la règle est prête
        pour le jour où l'un le sera."""
        demande = BudgetReallocation.objects.create(
            source=self.source, target=self.ivoirienne,
            amount=Decimal("1000.00"), reason="Renfort", requested_by="ceo.innov",
        )
        restreint = Access(
            role=Role.SUPER_ADMIN, country_ids=[self.togo.pk], username="do.togo"
        )

        with self.assertRaises(HorsPerimetre):
            transitions.verifier_la_decision(demande, restreint)
        self.assertFalse(transitions.peut_decider(demande, restreint))

    def test_peut_decider_suit_les_memes_regles(self):
        demande = self.demander(par=self.siege).instance

        self.assertTrue(transitions.peut_decider(demande, get_access(self.doo)))
        self.assertFalse(transitions.peut_decider(demande, get_access(self.siege)))
        self.assertFalse(transitions.peut_decider(demande, get_access(self.df)))
        self.assertFalse(transitions.peut_decider(demande, None))

    # -- Trace ------------------------------------------------------------------

    def test_la_trace_porte_l_auteur_et_l_adresse(self):
        demande = self.demander().instance

        resultat = transitions.approuver(demande, get_access(self.doo), "", trace(self.doo))

        entree = resultat.audit[0]
        entree.refresh_from_db()
        self.assertEqual(entree.user, "do.innov")
        self.assertEqual(entree.ip_address, ADRESSE)
        self.assertEqual(entree.user_agent, "Test")
