"""Workflow de validation, imputation budgétaire et verrouillage."""

from decimal import Decimal

from django.utils import timezone
from rest_framework import status

from budget.aggregates import budget_figures
from budget.models import Budget, OverrunPolicy
from core.models import Project
from expenses.models import AuditLog, Expense
from expenses.workflow import Status

from .base import ExpenseTestCase


class TransitionTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.expense = self.make_expense()

    def test_parcours_nominal(self):
        self.login(self.owner)
        submitted = self.client.post(f"/api/expenses/{self.expense.pk}/submit/")

        self.login(self.controller)
        reviewed = self.client.post(f"/api/expenses/{self.expense.pk}/review/")
        approved = self.client.post(f"/api/expenses/{self.expense.pk}/approve/")

        self.assertEqual(submitted.data["status"], Status.SUBMITTED)
        self.assertEqual(reviewed.data["status"], Status.IN_REVIEW)
        self.assertEqual(approved.data["status"], Status.APPROVED)

    def test_transition_impossible_depuis_l_etat_courant(self):
        """On ne valide pas une dépense encore en brouillon."""
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/approve/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.DRAFT)

    def test_le_statut_n_est_pas_modifiable_directement(self):
        self.login(self.owner)

        self.client.patch(
            f"/api/expenses/{self.expense.pk}/", {"status": Status.APPROVED}
        )

        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.DRAFT)

    def test_rejet_sans_motif_refuse(self):
        self.login(self.owner)
        self.client.post(f"/api/expenses/{self.expense.pk}/submit/")
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/reject/", {"note": "  "})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.SUBMITTED)

    def test_rejet_motive_puis_correction_et_nouvelle_soumission(self):
        self.login(self.owner)
        self.client.post(f"/api/expenses/{self.expense.pk}/submit/")
        self.login(self.controller)
        rejected = self.client.post(
            f"/api/expenses/{self.expense.pk}/reject/", {"note": "Reçu illisible"}
        )

        self.login(self.owner)
        corrected = self.client.patch(
            f"/api/expenses/{self.expense.pk}/", {"amount": "90000.00"}
        )
        resubmitted = self.client.post(f"/api/expenses/{self.expense.pk}/submit/")

        self.assertEqual(rejected.data["status"], Status.REJECTED)
        self.assertEqual(rejected.data["note"], "Reçu illisible")
        self.assertEqual(corrected.status_code, status.HTTP_200_OK)
        self.assertEqual(resubmitted.data["status"], Status.SUBMITTED)

    def test_saisie_reservee_aux_roles_habilites(self):
        """Le contrôleur contrôle, il ne soumet pas à la place du manager."""
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/submit/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_validation_reservee_aux_roles_habilites(self):
        self.login(self.owner)
        self.client.post(f"/api/expenses/{self.expense.pk}/submit/")

        response = self.client.post(f"/api/expenses/{self.expense.pk}/approve/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class LockingTests(ExpenseTestCase):
    """§6 : une dépense validée ne se modifie plus en place."""

    def setUp(self):
        super().setUp()
        self.expense = self.make_expense()
        self.login(self.owner)
        self.client.post(f"/api/expenses/{self.expense.pk}/submit/")
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.expense.pk}/approve/")

    def test_modification_refusee_apres_validation(self):
        self.login(self.owner)

        response = self.client.patch(
            f"/api/expenses/{self.expense.pk}/", {"amount": "1.00"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.amount, Decimal("100000.00"))

    def test_suppression_impossible(self):
        """Même pour un rôle habilité à écrire : la route n'existe pas."""
        self.login(self.owner)

        response = self.client.delete(f"/api/expenses/{self.expense.pk}/")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Expense.objects.filter(pk=self.expense.pk).exists())

    def test_cloture_possible_apres_validation(self):
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/close/")

        self.assertEqual(response.data["status"], Status.CLOSED)


class BudgetImputationTests(ExpenseTestCase):
    def test_imputation_automatique_sur_l_enveloppe_du_pays(self):
        expense = self.make_expense()
        self.login(self.owner)

        self.client.post(f"/api/expenses/{expense.pk}/submit/")

        expense.refresh_from_db()
        self.assertEqual(expense.budget, self.budget)

    def test_sous_enveloppe_du_projet_prioritaire(self):
        projet = Project.objects.create(country=self.togo, name="Campagne T1")
        sous_enveloppe = Budget.objects.create(
            country=self.togo, year=self.year, project=projet,
            amount=Decimal("300000.00"),
        )
        expense = self.make_expense(project=projet)
        self.login(self.owner)

        self.client.post(f"/api/expenses/{expense.pk}/submit/")

        expense.refresh_from_db()
        self.assertEqual(expense.budget, sous_enveloppe)

    def test_sans_enveloppe_active_la_soumission_echoue(self):
        """§6 : une dépense doit être associée à un budget actif."""
        self.budget.is_active = False
        self.budget.save()
        expense = self.make_expense()
        self.login(self.owner)

        response = self.client.post(f"/api/expenses/{expense.pk}/submit/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("budget", response.data)

    def test_engage_puis_consomme(self):
        """Une dépense soumise engage l'enveloppe ; validée, elle la consomme.
        Dans les deux cas le disponible diminue."""
        expense = self.make_expense(amount="250000.00")
        self.login(self.owner)
        self.client.post(f"/api/expenses/{expense.pk}/submit/")

        engaged = budget_figures(self.budget)
        self.assertEqual(engaged["engaged"], Decimal("250000.00"))
        self.assertEqual(engaged["consumed"], Decimal("0.00"))
        self.assertEqual(engaged["remaining"], Decimal("750000.00"))

        self.login(self.controller)
        self.client.post(f"/api/expenses/{expense.pk}/approve/")

        consumed = budget_figures(self.budget)
        self.assertEqual(consumed["engaged"], Decimal("0.00"))
        self.assertEqual(consumed["consumed"], Decimal("250000.00"))
        self.assertEqual(consumed["remaining"], Decimal("750000.00"))

    def test_brouillon_et_rejet_n_engagent_rien(self):
        self.make_expense(amount="400000.00")  # reste en brouillon
        rejected = self.make_expense(amount="400000.00")
        self.login(self.owner)
        self.client.post(f"/api/expenses/{rejected.pk}/submit/")
        self.login(self.controller)
        self.client.post(f"/api/expenses/{rejected.pk}/reject/", {"note": "Non justifié"})

        figures = budget_figures(self.budget)

        self.assertEqual(figures["remaining"], Decimal("1000000.00"))

    def test_depense_non_imputee_expose_un_libelle_nul(self):
        """Régression : la traversée `budget.__str__` renvoyait la
        représentation du method-wrapper de None, affichée telle quelle."""
        expense = self.make_expense()
        self.login(self.owner)

        response = self.client.get(f"/api/expenses/{expense.pk}/")

        self.assertIsNone(response.data["budget_label"])

    def test_ecart_calcule_jamais_saisi(self):
        expense = self.make_expense(amount="100000.00", justified_amount="60000.00")
        self.login(self.owner)

        response = self.client.get(f"/api/expenses/{expense.pk}/")

        self.assertEqual(response.data["gap"], "40000.00")


class OverrunPolicyTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.budget.amount = Decimal("100000.00")
        self.budget.save()

    def _submit(self, amount, user=None):
        expense = self.make_expense(amount=amount)
        self.login(user or self.owner)
        return expense, self.client.post(f"/api/expenses/{expense.pk}/submit/")

    def test_politique_bloquante(self):
        self.budget.overrun_policy = OverrunPolicy.BLOCK
        self.budget.save()

        expense, response = self._submit("150000.00")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        expense.refresh_from_db()
        self.assertEqual(expense.status, Status.DRAFT)

    def test_politique_alerte_laisse_passer_en_signalant(self):
        self.budget.overrun_policy = OverrunPolicy.WARN
        self.budget.save()

        expense, response = self._submit("150000.00")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Dépassement", response.data["warning"])
        expense.refresh_from_db()
        self.assertEqual(expense.status, Status.SUBMITTED)

    def test_politique_approbation_laisse_demander_mais_pas_valider(self):
        """Le manager doit pouvoir demander le dépassement ; seule sa
        validation relève de la direction des opérations."""
        self.budget.overrun_policy = OverrunPolicy.APPROVAL
        self.budget.save()
        expense, submitted = self._submit("150000.00")

        self.login(self.controller)
        response = self.client.post(f"/api/expenses/{expense.pk}/approve/")

        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertIn("direction des opérations", submitted.data["warning"])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        expense.refresh_from_db()
        self.assertEqual(expense.status, Status.SUBMITTED)

    def test_politique_approbation_acceptee_pour_le_do(self):
        self.budget.overrun_policy = OverrunPolicy.APPROVAL
        self.budget.save()
        expense = self.make_expense(amount="150000.00")
        self.login(self.owner)
        self.client.post(f"/api/expenses/{expense.pk}/submit/")

        self.login(self.doo)
        response = self.client.post(f"/api/expenses/{expense.pk}/approve/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Dépassement", response.data["warning"])

    def test_le_cumul_des_depenses_est_pris_en_compte(self):
        self.budget.overrun_policy = OverrunPolicy.BLOCK
        self.budget.save()
        first, ok = self._submit("80000.00")

        second, response = self._submit("30000.00")

        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DossierWorkflowTests(ExpenseTestCase):
    def test_dossier_sans_justificatif_ne_peut_etre_valide(self):
        self.login(self.owner)
        self.client.post(f"/api/dossiers/{self.dossier.pk}/submit/")
        self.login(self.controller)

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/approve/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("proofs", response.data)

    def test_totaux_du_dossier(self):
        self.make_expense(amount="100000.00", justified_amount="70000.00")
        self.make_expense(amount="50000.00", justified_amount="50000.00")
        self.login(self.owner)

        response = self.client.get(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.data["totals"]["amount"], "150000.00")
        self.assertEqual(response.data["totals"]["justified"], "120000.00")
        self.assertEqual(response.data["totals"]["gap"], "30000.00")


class ScopingTests(ExpenseTestCase):
    def test_un_pays_ne_voit_pas_les_dossiers_d_un_autre(self):
        self.login(self.rep_ivoire)

        response = self.client.get("/api/dossiers/")

        self.assertEqual(response.data["count"], 0)

    def test_creation_d_une_depense_hors_perimetre_refusee(self):
        self.login(self.rep_ivoire)

        response = self.client.post(
            "/api/expenses/",
            {
                "dossier": self.dossier.pk,
                "country": self.togo.pk,
                "date": timezone.now().isoformat(),
                "title": "Dépense pirate",
                "amount": "1000.00",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dossier_d_un_autre_pays_refuse(self):
        """Le dossier et la dépense doivent relever du même pays."""
        self.login(self.owner)

        response = self.client.post(
            "/api/expenses/",
            {
                "dossier": self.dossier.pk,
                "country": self.ivoire.pk,
                "date": timezone.now().isoformat(),
                "title": "Incohérente",
                "amount": "1000.00",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", response.data)


class AuditTests(ExpenseTestCase):
    def test_chaque_transition_laisse_une_trace(self):
        expense = self.make_expense()
        self.login(self.owner)
        self.client.post(f"/api/expenses/{expense.pk}/submit/")
        self.login(self.controller)
        self.client.post(f"/api/expenses/{expense.pk}/reject/", {"note": "À revoir"})

        entries = AuditLog.objects.filter(object_type="Expense").order_by("id")

        # La dépense est créée directement en base ici : seules les deux
        # transitions passées par l'API sont journalisées.
        actions = list(entries.values_list("action", flat=True))
        self.assertEqual(
            actions, [AuditLog.Action.SUBMITTED, AuditLog.Action.REJECTED]
        )
        rejection = entries.last()
        self.assertEqual(rejection.user, "rh.innov")
        self.assertEqual(rejection.detail["note"], "À revoir")
        self.assertEqual(rejection.detail["from_status"], Status.SUBMITTED)
        self.assertEqual(rejection.country, self.togo)

    def test_modification_conserve_l_ancienne_et_la_nouvelle_valeur(self):
        expense = self.make_expense(amount="100000.00")
        self.login(self.owner)

        self.client.patch(f"/api/expenses/{expense.pk}/", {"amount": "120000.00"})

        entry = AuditLog.objects.filter(action=AuditLog.Action.UPDATED).first()
        self.assertEqual(entry.detail["before"]["amount"], "100000.00")
        self.assertEqual(entry.detail["after"]["amount"], "120000.00")

    def test_journal_reserve_aux_roles_habilites(self):
        self.login(self.owner)

        response = self.client.get("/api/audit/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_journal_lisible_par_le_controleur(self):
        self.login(self.controller)

        response = self.client.get("/api/audit/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
