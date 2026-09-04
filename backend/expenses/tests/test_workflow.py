"""Circuit de justification, imputation budgétaire et verrouillage.

Une ligne ne se soumet jamais seule : le pays soumet le dossier, qui emporte
ses lignes. Les tests passent donc par ``submit_dossier``, le chemin réel.
"""

from datetime import date
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone
from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.aggregates import budget_figures
from budget.models import Budget, OverrunPolicy
from core.models import Project, WorkflowConfiguration
from expenses.models import AuditLog, Beneficiary, Dossier, Expense, Proof
from expenses.workflow import Status

from .base import ExpenseTestCase


def configurer(**valeurs):
    """Modifie le singleton de configuration sans le recréer."""
    configuration = WorkflowConfiguration.charger()
    for cle, valeur in valeurs.items():
        setattr(configuration, cle, valeur)
    configuration.save()
    return configuration


class TransitionTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.expense = self.make_expense()

    def test_parcours_nominal(self):
        submitted = self.submit_dossier()

        self.login(self.controller)
        reviewed = self.client.post(f"/api/expenses/{self.expense.pk}/review/")
        approved = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertEqual(submitted.data["status"], Status.SUBMITTED)
        self.assertEqual(reviewed.data["status"], Status.IN_REVIEW)
        self.assertEqual(approved.data["status"], Status.JUSTIFIED)

    def test_une_ligne_ne_se_soumet_pas_seule(self):
        """Le dossier emporte ses lignes : l'action n'existe pas sur une
        ligne, elle ne pouvait que répondre 400."""
        self.login(self.owner)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/submit/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.DRAFT)

    def test_transition_impossible_depuis_l_etat_courant(self):
        """On ne valide pas une dépense encore en brouillon."""
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.DRAFT)

    def test_le_statut_n_est_pas_modifiable_directement(self):
        self.login(self.owner)

        self.client.patch(
            f"/api/expenses/{self.expense.pk}/", {"status": Status.JUSTIFIED}
        )

        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.DRAFT)

    def test_rejet_sans_motif_refuse(self):
        self.submit_dossier()
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/reject/", {"note": "  "})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.SUBMITTED)

    def test_non_justifiee_reste_figee(self):
        """L'argent est sorti : la dépense ne se réécrit pas et ne repart pas
        au brouillon. Elle demeure au débit, marquée non justifiée."""
        self.expense.note = "Plein fait à la station de Kara"
        self.expense.save()
        self.submit_dossier()
        self.login(self.controller)
        rejected = self.client.post(
            f"/api/expenses/{self.expense.pk}/reject/", {"note": "Reçu illisible"}
        )

        self.login(self.owner)
        corrected = self.client.patch(
            f"/api/expenses/{self.expense.pk}/", {"amount": "90000.00"}
        )

        self.assertEqual(rejected.data["status"], Status.UNJUSTIFIED)
        self.assertEqual(rejected.data["control_note"], "Reçu illisible")
        # Le motif du contrôleur n'efface pas la remarque du déclarant.
        self.assertEqual(rejected.data["note"], "Plein fait à la station de Kara")
        self.assertEqual(corrected.status_code, status.HTTP_400_BAD_REQUEST)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.amount, Decimal("100000.00"))
        self.assertEqual(self.expense.status, Status.UNJUSTIFIED)

    def test_une_preuve_tardive_permet_de_justifier(self):
        """Seul chemin de rattrapage : le contrôleur constate qu'une preuve
        déposée après coup couvre la dépense."""
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(
            f"/api/expenses/{self.expense.pk}/reject/", {"note": "Preuve absente"}
        )

        response = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertEqual(response.data["status"], Status.JUSTIFIED)

    def test_saisie_reservee_aux_roles_habilites(self):
        """Le contrôleur contrôle, il ne soumet pas à la place du manager."""
        response = self.submit_dossier(user=self.controller)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_validation_reservee_aux_roles_habilites(self):
        self.submit_dossier()

        response = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_justification_refusee_sans_controle_si_etape_obligatoire(self):
        configurer(require_review_step=True)
        self.submit_dossier()
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("contrôle", str(response.data).lower())

    def test_justification_acceptee_sans_controle_si_etape_facultative(self):
        configurer(require_review_step=False)
        self.submit_dossier()
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Status.JUSTIFIED)


class LockingTests(ExpenseTestCase):
    """§6 : une dépense déclarée ne se modifie plus, ni ne s'efface."""

    def setUp(self):
        super().setUp()
        self.expense = self.make_expense()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

    def test_modification_refusee_apres_declaration(self):
        self.login(self.owner)

        response = self.client.patch(
            f"/api/expenses/{self.expense.pk}/", {"amount": "1.00"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.amount, Decimal("100000.00"))

    def test_suppression_impossible_une_fois_declaree(self):
        """Effacer une dépense déclarée reviendrait à perdre la trace de
        l'argent."""
        self.login(self.owner)

        response = self.client.delete(f"/api/expenses/{self.expense.pk}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Expense.objects.filter(pk=self.expense.pk).exists())

    def test_cloture_possible_apres_justification(self):
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/close/")

        self.assertEqual(response.data["status"], Status.CLOSED)


class BudgetImputationTests(ExpenseTestCase):
    def test_imputation_automatique_sur_l_enveloppe_du_pays(self):
        expense = self.make_expense()

        self.submit_dossier()

        expense.refresh_from_db()
        self.assertEqual(expense.budget, self.budget)

    def test_sous_enveloppe_du_projet_prioritaire(self):
        projet = Project.objects.create(country=self.togo, name="Campagne T1")
        sous_enveloppe = Budget.objects.create(
            country=self.togo, year=self.year, project=projet,
            amount=Decimal("300000.00"),
        )
        expense = self.make_expense(project=projet)

        self.submit_dossier()

        expense.refresh_from_db()
        self.assertEqual(expense.budget, sous_enveloppe)

    def test_sans_enveloppe_active_la_soumission_echoue(self):
        """§6 : une dépense doit être associée à un budget actif."""
        self.budget.is_active = False
        self.budget.save()
        expense = self.make_expense()

        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("budget", response.data)
        expense.refresh_from_db()
        self.assertEqual(expense.status, Status.DRAFT)

    def test_engage_puis_consomme(self):
        """Une dépense soumise engage l'enveloppe ; validée, elle la consomme.
        Dans les deux cas le disponible diminue."""
        expense = self.make_expense(amount="250000.00")
        self.submit_dossier()

        engaged = budget_figures(self.budget)
        self.assertEqual(engaged["engaged"], Decimal("250000.00"))
        self.assertEqual(engaged["consumed"], Decimal("0.00"))
        self.assertEqual(engaged["remaining"], Decimal("750000.00"))

        self.login(self.controller)
        self.client.post(f"/api/expenses/{expense.pk}/justify/")

        consumed = budget_figures(self.budget)
        self.assertEqual(consumed["engaged"], Decimal("0.00"))
        self.assertEqual(consumed["consumed"], Decimal("250000.00"))
        self.assertEqual(consumed["remaining"], Decimal("750000.00"))

    def test_le_brouillon_seul_n_engage_rien(self):
        self.make_expense(amount="400000.00")  # jamais soumis

        figures = budget_figures(self.budget)

        self.assertEqual(figures["remaining"], Decimal("1000000.00"))

    def test_une_depense_non_justifiee_pese_sur_l_enveloppe(self):
        """L'absence de preuve ne fait pas revenir l'argent : elle se lit dans
        l'écart entre dépensé et justifié."""
        expense = self.make_expense(amount="400000.00")
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{expense.pk}/reject/", {"note": "Sans reçu"})

        figures = budget_figures(self.budget)

        self.assertEqual(figures["consumed"], Decimal("400000.00"))
        self.assertEqual(figures["justified"], Decimal("0.00"))
        self.assertEqual(figures["gap"], Decimal("400000.00"))
        self.assertEqual(figures["remaining"], Decimal("600000.00"))

    def test_depense_non_imputee_expose_un_libelle_nul(self):
        """Régression : la traversée `budget.__str__` renvoyait la
        représentation du method-wrapper de None, affichée telle quelle."""
        expense = self.make_expense()
        self.login(self.owner)

        response = self.client.get(f"/api/expenses/{expense.pk}/")

        self.assertIsNone(response.data["budget_label"])


class MontantJustifieTests(ExpenseTestCase):
    """Le montant justifié appartient au siège.

    Le pays déclare ce qu'il a dépensé ; le contrôleur constate ce qui est
    prouvé. Laisser le déclarant saisir le montant justifié revenait à le
    laisser se donner quitus.
    """

    def payload(self, **extra):
        data = {
            "dossier": self.dossier.pk, "country": self.togo.pk,
            "date": f"{self.year}-03-15T10:00:00Z", "title": "Carburant",
            "amount": "100000.00",
            # Une ligne ne se soumet qu'avec son équipe et son manager (§7).
            "team": self.team.pk, "owner": self.manager.pk,
        }
        data.update(extra)
        return data

    def test_ecart_calcule_jamais_saisi(self):
        """L'écart se lit, il ne s'écrit pas : la création ignore le montant
        justifié, et seule la justification le fixe."""
        self.login(self.owner)
        created = self.client.post(
            "/api/expenses/", self.payload(justified_amount="60000.00")
        )
        self.assertEqual(created.data["gap"], "100000.00")

        self.submit_dossier()
        self.login(self.controller)
        justified = self.client.post(
            f"/api/expenses/{created.data['id']}/justify/",
            {"justified_amount": "60000.00"},
        )

        self.assertEqual(justified.data["justified_amount"], "60000.00")
        self.assertEqual(justified.data["gap"], "40000.00")

    def test_un_owner_ne_fixe_pas_le_montant_justifie(self):
        self.login(self.owner)

        created = self.client.post(
            "/api/expenses/", self.payload(justified_amount="100000.00")
        )
        modified = self.client.patch(
            f"/api/expenses/{created.data['id']}/", {"justified_amount": "50000.00"}
        )

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["justified_amount"], "0.00")
        self.assertEqual(modified.status_code, status.HTTP_200_OK)
        self.assertEqual(modified.data["justified_amount"], "0.00")
        self.assertEqual(
            Expense.objects.get(pk=created.data["id"]).justified_amount, Decimal("0.00")
        )

    def test_justify_le_fixe_et_le_borne(self):
        expense = self.make_expense(amount="100000.00")
        self.submit_dossier()
        self.login(self.controller)

        trop = self.client.post(
            f"/api/expenses/{expense.pk}/justify/", {"justified_amount": "100000.01"}
        )
        negatif = self.client.post(
            f"/api/expenses/{expense.pk}/justify/", {"justified_amount": "-1"}
        )
        partiel = self.client.post(
            f"/api/expenses/{expense.pk}/justify/", {"justified_amount": "75000.00"}
        )

        self.assertEqual(trop.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("justified_amount", trop.data)
        self.assertEqual(negatif.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(partiel.status_code, status.HTTP_200_OK)
        self.assertEqual(partiel.data["justified_amount"], "75000.00")
        self.assertEqual(partiel.data["gap"], "25000.00")

    def test_justify_sans_montant_couvre_toute_la_depense(self):
        expense = self.make_expense(amount="100000.00")
        self.submit_dossier()
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{expense.pk}/justify/")

        self.assertEqual(response.data["justified_amount"], "100000.00")
        self.assertEqual(response.data["gap"], "0.00")

    def test_reject_le_remet_a_zero(self):
        expense = self.make_expense(amount="100000.00", justified_amount="60000.00")
        self.submit_dossier()
        self.login(self.controller)

        response = self.client.post(
            f"/api/expenses/{expense.pk}/reject/", {"note": "Reçu illisible"}
        )

        self.assertEqual(response.data["justified_amount"], "0.00")
        self.assertEqual(response.data["gap"], "100000.00")
        trace = AuditLog.objects.get(action=AuditLog.Action.UNJUSTIFIED)
        self.assertEqual(trace.detail["before"]["justified_amount"], "60000.00")
        self.assertEqual(trace.detail["after"]["justified_amount"], "0.00")

    def test_la_justification_est_journalisee_avec_avant_et_apres(self):
        expense = self.make_expense(amount="100000.00")
        self.submit_dossier()
        self.login(self.controller)

        self.client.post(
            f"/api/expenses/{expense.pk}/justify/",
            {"justified_amount": "80000.00", "note": "Facture partielle"},
        )

        trace = AuditLog.objects.get(action=AuditLog.Action.JUSTIFIED)
        self.assertEqual(trace.detail["before"]["justified_amount"], "0.00")
        self.assertEqual(trace.detail["after"]["justified_amount"], "80000.00")
        self.assertEqual(trace.detail["after"]["control_note"], "Facture partielle")


class OverrunPolicyTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.budget.amount = Decimal("100000.00")
        self.budget.save()
        self.compteur = 0

    def _nouveau_dossier(self):
        """Chaque soumission part d'un dossier neuf : un dossier ne se soumet
        qu'une fois."""
        self.compteur += 1
        return Dossier.objects.create(
            number=f"D-{self.compteur:03d}", label="Mission", country=self.togo,
            date=date(self.year, 3, 15), created_by=self.owner.username,
        )

    def _submit(self, amount, user=None):
        dossier = self._nouveau_dossier()
        expense = self.make_expense(amount=amount, dossier=dossier)
        return expense, self.submit_dossier(dossier, user=user)

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
        validation relève de la direction, super administratrice."""
        self.budget.overrun_policy = OverrunPolicy.APPROVAL
        self.budget.save()
        expense, submitted = self._submit("150000.00")

        self.login(self.controller)
        response = self.client.post(f"/api/expenses/{expense.pk}/justify/")

        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertIn("super administrateur", submitted.data["warning"])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        expense.refresh_from_db()
        self.assertEqual(expense.status, Status.SUBMITTED)

    def test_politique_approbation_acceptee_pour_le_do(self):
        self.budget.overrun_policy = OverrunPolicy.APPROVAL
        self.budget.save()
        expense, _ = self._submit("150000.00")

        self.login(self.doo)
        response = self.client.post(f"/api/expenses/{expense.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Dépassement", response.data["warning"])

    def test_le_cumul_des_depenses_est_pris_en_compte(self):
        self.budget.overrun_policy = OverrunPolicy.BLOCK
        self.budget.save()
        first, ok = self._submit("80000.00")

        second, response = self._submit("30000.00")

        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_le_cumul_vaut_aussi_dans_un_meme_dossier(self):
        """Les lignes d'un dossier s'additionnent au fil de la soumission :
        chacune prise à part passerait, ensemble elles dépassent."""
        self.budget.overrun_policy = OverrunPolicy.BLOCK
        self.budget.save()
        self.make_expense(amount="60000.00")
        self.make_expense(amount="60000.00")

        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            Expense.objects.filter(status=Status.SUBMITTED).exists()
        )

    def test_une_depense_engagee_reste_justifiable_si_l_enveloppe_est_reduite(self):
        """L'argent est déjà sorti : refuser de le constater le laisserait à
        jamais en suspens, sans faire revenir un franc."""
        self.budget.overrun_policy = OverrunPolicy.BLOCK
        self.budget.save()
        expense, submitted = self._submit("80000.00")
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.budget.amount = Decimal("50000.00")
        self.budget.save()

        self.login(self.controller)
        response = self.client.post(f"/api/expenses/{expense.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Status.JUSTIFIED)
        self.assertIn("Dépassement", response.data["warning"])

    def test_un_seul_avertissement_par_enveloppe(self):
        """Vingt lignes en dépassement ne doivent pas produire vingt messages
        concaténés : un par enveloppe, portant le dépassement cumulé."""
        self.budget.overrun_policy = OverrunPolicy.WARN
        self.budget.save()
        for _ in range(3):
            self.make_expense(amount="60000.00")

        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["warning"].count("Dépassement"), 1)
        # 3 × 60 000 − 100 000
        self.assertIn("80000.00", response.data["warning"])


class DossierWorkflowTests(ExpenseTestCase):
    def _piece(self, statut=Proof.ProofStatus.RECEIVED, empreinte="a"):
        return Proof.objects.create(
            dossier=self.dossier, file="justificatifs/f.pdf",
            original_name="facture.pdf", sha256=empreinte * 64, status=statut,
        )

    def _justifier_les_lignes(self):
        self.login(self.controller)
        for ligne in self.dossier.expenses.all():
            self.client.post(f"/api/expenses/{ligne.pk}/justify/")

    def test_dossier_sans_justificatif_ne_peut_etre_valide(self):
        self.make_expense()
        self.submit_dossier()
        self._justifier_les_lignes()

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("proofs", response.data)

    def test_un_dossier_dont_les_pieces_sont_toutes_archivees_n_est_pas_justifiable(self):
        """Une pièce archivée a été remplacée ; une pièce rejetée ne prouve
        rien. Ni l'une ni l'autre ne justifie un dossier."""
        self.make_expense()
        self._piece(Proof.ProofStatus.ARCHIVED, "a")
        self._piece(Proof.ProofStatus.REJECTED, "b")
        self.submit_dossier()
        self._justifier_les_lignes()

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("proofs", response.data)

    def test_un_dossier_ne_se_justifie_pas_sur_une_ligne_non_tranchee(self):
        """Le dossier ne dit pas autre chose que ses lignes : « justifié »
        avec une ligne encore soumise, le total justifié mentirait."""
        self.make_expense(title="Tranchée")
        en_suspens = self.make_expense(title="En suspens")
        self._piece()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.dossier.expenses.get(title='Tranchée').pk}/justify/")

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("En suspens", str(response.data["expenses"]))
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)
        en_suspens.refresh_from_db()
        self.assertEqual(en_suspens.status, Status.SUBMITTED)

    def test_un_dossier_ne_se_justifie_pas_sur_une_ligne_non_justifiee(self):
        ligne = self.make_expense()
        self._piece()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{ligne.pk}/reject/", {"note": "Sans reçu"})

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expenses", response.data)

    def test_un_dossier_justifie_quand_toutes_ses_lignes_le_sont(self):
        self.make_expense()
        self.make_expense(title="Hôtel")
        self._piece()
        self.submit_dossier()
        self._justifier_les_lignes()

        response = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Status.JUSTIFIED)

    def test_le_constat_de_non_justification_exige_des_lignes_tranchees(self):
        self.make_expense()
        self.submit_dossier()
        self.login(self.controller)

        response = self.client.post(
            f"/api/dossiers/{self.dossier.pk}/reject/", {"note": "Rien ne couvre"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expenses", response.data)

    def test_le_constat_de_non_justification_passe_sur_des_lignes_tranchees(self):
        ligne = self.make_expense()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{ligne.pk}/reject/", {"note": "Sans reçu"})

        response = self.client.post(
            f"/api/dossiers/{self.dossier.pk}/reject/", {"note": "Rien ne couvre"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Status.UNJUSTIFIED)
        self.assertEqual(response.data["note"], "Rien ne couvre")

    def test_celui_qui_a_ouvert_le_dossier_ne_le_tranche_pas(self):
        """Quatre yeux sur le dossier aussi : un contrôleur qui ouvre un
        dossier ne se donne pas quitus dessus."""
        self.dossier.created_by = self.controller.username
        self.dossier.save()
        self.make_expense()
        self._piece()
        self.submit_dossier()
        self._justifier_les_lignes()

        refuse = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")
        self.login(self.doo)
        accepte = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        self.assertEqual(refuse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(accepte.status_code, status.HTTP_200_OK)

    def test_le_dossier_porte_son_auteur(self):
        self.login(self.owner)

        response = self.client.post(
            "/api/dossiers/",
            {"number": "N-0100", "label": "Salon", "country": self.togo.pk,
             "date": f"{self.year}-04-01"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created_by"], "owner.togo")

    def test_totaux_du_dossier(self):
        self.make_expense(amount="100000.00", justified_amount="70000.00")
        self.make_expense(amount="50000.00", justified_amount="50000.00")
        self.login(self.owner)

        response = self.client.get(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.data["totals"]["amount"], "150000.00")
        self.assertEqual(response.data["totals"]["justified"], "120000.00")
        self.assertEqual(response.data["totals"]["gap"], "30000.00")


class ScopingTests(ExpenseTestCase):
    def _payload(self, **extra):
        data = {
            "dossier": self.dossier.pk,
            "country": self.togo.pk,
            "date": timezone.now().isoformat(),
            "title": "Dépense",
            "amount": "1000.00",
        }
        data.update(extra)
        return data

    def test_un_pays_ne_voit_pas_les_dossiers_d_un_autre(self):
        self.login(self.rep_ivoire)

        response = self.client.get("/api/dossiers/")

        self.assertEqual(response.data["count"], 0)

    def test_acces_direct_hors_perimetre_repond_404(self):
        """Un objet hors périmètre n'existe pas pour le demandeur."""
        expense = self.make_expense()
        self.login(self.rep_ivoire)

        depense = self.client.get(f"/api/expenses/{expense.pk}/")
        dossier = self.client.get(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(depense.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(dossier.status_code, status.HTTP_404_NOT_FOUND)

    def test_creation_d_une_depense_hors_perimetre_refusee(self):
        """Le refus ne doit rien apprendre : un dossier hors périmètre est
        refusé exactement comme un dossier qui n'existe pas."""
        self.login(self.rep_ivoire)
        inexistant = self.dossier.pk + 1000

        existant = self.client.post("/api/expenses/", self._payload())
        fantome = self.client.post(
            "/api/expenses/", self._payload(dossier=inexistant)
        )

        self.assertEqual(existant.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(fantome.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            str(existant.data["dossier"]).replace(str(self.dossier.pk), "N"),
            str(fantome.data["dossier"]).replace(str(inexistant), "N"),
        )
        self.assertEqual(self.dossier.expenses.count(), 0)

    def test_dossier_d_un_autre_pays_refuse(self):
        """Le dossier et la dépense doivent relever du même pays, même pour
        le siège, qui voit les deux."""
        siege = make_user("ceo.innov", Role.SUPER_ADMIN)
        self.login(siege)

        response = self.client.post(
            "/api/expenses/", self._payload(country=self.ivoire.pk)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", response.data)

    def test_beneficiaire_d_un_autre_pays_refuse(self):
        """Chaque entité du contexte est revalidée par pays : un bénéficiaire
        ivoirien ne se rattache pas à une dépense togolaise."""
        voisin = Beneficiary.objects.create(country=self.ivoire, name="Groupe Abidjan")
        self.login(self.owner)

        response = self.client.post(
            "/api/expenses/", self._payload(beneficiary=voisin.pk)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("beneficiary", response.data)

    def test_un_manager_non_rattache_au_pays_refuse(self):
        self.manager.countries.clear()
        self.login(self.owner)

        depense = self.client.post(
            "/api/expenses/", self._payload(owner=self.manager.pk)
        )
        dossier = self.client.post(
            "/api/dossiers/",
            {"number": "N-0200", "label": "Salon", "country": self.togo.pk,
             "date": f"{self.year}-04-01", "owner": self.manager.pk},
        )

        self.assertEqual(depense.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("owner", depense.data)
        self.assertEqual(dossier.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("owner", dossier.data)

    def test_un_brouillon_ne_se_deplace_pas_vers_un_dossier_declare(self):
        """Créer une ligne dans un dossier déclaré est refusé ; l'y déplacer
        par modification doit l'être tout autant."""
        ligne = self.make_expense()
        declare = Dossier.objects.create(
            number="N-0300", label="Déjà parti", country=self.togo,
            date=date(self.year, 3, 1), status=Status.SUBMITTED,
        )
        self.login(self.owner)

        response = self.client.patch(
            f"/api/expenses/{ligne.pk}/", {"dossier": declare.pk}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dossier", response.data)
        ligne.refresh_from_db()
        self.assertEqual(ligne.dossier, self.dossier)


class AuditTests(ExpenseTestCase):
    def test_chaque_transition_laisse_une_trace(self):
        expense = self.make_expense()
        self.submit_dossier()
        self.login(self.controller)
        self.client.post(f"/api/expenses/{expense.pk}/reject/", {"note": "À revoir"})

        entries = AuditLog.objects.filter(object_type="Expense").order_by("id")

        # La dépense est créée directement en base ici : seules les deux
        # transitions passées par l'API sont journalisées.
        actions = list(entries.values_list("action", flat=True))
        self.assertEqual(
            actions, [AuditLog.Action.SUBMITTED, AuditLog.Action.UNJUSTIFIED]
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

    @override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1})
    def test_l_adresse_du_client_est_lue_derriere_le_mandataire(self):
        """Derrière nginx, ``REMOTE_ADDR`` est l'adresse du conteneur : le
        journal doit lire celle du client dans ``X-Forwarded-For``, au rang
        du nombre de mandataires de confiance — pas au premier, forgeable."""
        expense = self.make_expense(amount="100000.00")
        self.login(self.owner)

        self.client.patch(
            f"/api/expenses/{expense.pk}/", {"amount": "120000.00"},
            HTTP_X_FORWARDED_FOR="203.0.113.9, 41.79.0.10",
        )

        entry = AuditLog.objects.get(action=AuditLog.Action.UPDATED)
        self.assertEqual(entry.ip_address, "41.79.0.10")

    def test_journal_reserve_aux_roles_habilites(self):
        self.login(self.owner)

        response = self.client.get("/api/audit/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_journal_lisible_par_la_rh_et_la_direction(self):
        for compte in (make_user("rh.admin", Role.ADMIN), self.doo):
            with self.subTest(role=compte.profile.role):
                self.login(compte)

                response = self.client.get("/api/audit/")

                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_journal_ferme_au_dm_et_au_df(self):
        """Le DM et le DF contrôlent les dépenses ; ils n'auditent pas. Le
        journal relit leurs propres décisions : c'est un acte
        d'administration, réservé à la RH et à la direction."""
        for compte in (self.controller, make_user("dm.innov", Role.DM)):
            with self.subTest(role=compte.profile.role):
                self.login(compte)

                response = self.client.get("/api/audit/")

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DraftDeletionTests(ExpenseTestCase):
    """« On peut écrire au brouillon » : un brouillon reste une matière de
    travail, tout le reste est définitif."""

    def test_l_auteur_supprime_son_brouillon(self):
        self.login(self.owner)
        created = self.client.post(
            "/api/expenses/",
            {
                "dossier": self.dossier.pk, "country": self.togo.pk,
                "date": f"{self.year}-03-15T10:00:00Z", "title": "Erreur de saisie",
                "amount": "1000.00",
            },
        )
        expense_id = created.data["id"]

        response = self.client.delete(f"/api/expenses/{expense_id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Expense.objects.filter(pk=expense_id).exists())

    def test_la_suppression_est_journalisee(self):
        self.login(self.owner)
        expense = self.make_expense(created_by="owner.togo")

        self.client.delete(f"/api/expenses/{expense.pk}/")

        entry = AuditLog.objects.filter(action=AuditLog.Action.DELETED).first()
        self.assertEqual(entry.user, "owner.togo")
        self.assertIn("Brouillon supprimé", entry.label)

    def test_un_tiers_ne_supprime_pas_le_brouillon_d_autrui(self):
        expense = self.make_expense(created_by="quelqu-un-dautre")
        self.login(self.owner)

        response = self.client.delete(f"/api/expenses/{expense.pk}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())


class JustificationRegisterTests(ExpenseTestCase):
    """« On t'a donné un budget, qu'as-tu dépensé, et où est la preuve ? »"""

    dossier_status = Status.SUBMITTED

    def setUp(self):
        super().setUp()
        self.depense = self.make_expense(
            amount="120000.00", justified_amount="80000.00",
            place="Lomé", title="Hébergement mission",
        )
        Proof.objects.create(
            dossier=self.dossier,
            file="justificatifs/f.pdf",
            original_name="facture.pdf",
            kind=Proof.Kind.INVOICE,
            is_complete=False,
            sha256="b" * 64,
        )
        self.login(self.controller)

    def test_le_registre_joint_la_depense_et_ses_preuves(self):
        response = self.client.get("/api/expenses/register/")

        ligne = next(
            r for r in response.data["results"] if r["id"] == self.depense.pk
        )
        self.assertEqual(ligne["place"], "Lomé")
        self.assertEqual(ligne["gap"], "40000.00")
        self.assertEqual(ligne["dossier_number"], "N-0001")
        self.assertTrue(ligne["has_proof"])
        self.assertEqual(ligne["proofs"][0]["original_name"], "facture.pdf")
        self.assertFalse(ligne["proofs"][0]["is_complete"])

    def test_une_depense_sans_preuve_est_signalee(self):
        vide = Dossier.objects.create(
            number="N-0009", label="Sans pièce", country=self.togo,
            date=self.dossier.date,
        )
        orpheline = self.make_expense(dossier=vide, amount="5000.00")

        response = self.client.get("/api/expenses/register/")

        ligne = next(
            r for r in response.data["results"] if r["id"] == orpheline.pk
        )
        self.assertFalse(ligne["has_proof"])
        self.assertEqual(ligne["proofs"], [])

    def test_filtrage_par_periode(self):
        response = self.client.get(
            "/api/expenses/register/",
            {"date__gte": f"{self.year + 1}-01-01T00:00:00Z"},
        )

        self.assertEqual(response.data["count"], 0)

    def test_registre_limite_au_perimetre(self):
        self.login(self.rep_ivoire)

        response = self.client.get("/api/expenses/register/")

        self.assertEqual(response.data["count"], 0)


class SubEnvelopeImputationTests(ExpenseTestCase):
    """La sous-enveloppe la plus précise l'emporte."""

    def setUp(self):
        super().setUp()
        self.enveloppe_equipe = Budget.objects.create(
            country=self.togo, year=self.year, team=self.team,
            amount=Decimal("500000.00"),
        )
        self.enveloppe_manager = Budget.objects.create(
            country=self.togo, year=self.year, manager=self.manager,
            amount=Decimal("400000.00"),
        )

    def _imputer(self, **kwargs):
        expense = self.make_expense(**kwargs)
        self.submit_dossier()
        expense.refresh_from_db()
        return expense.budget

    def test_l_equipe_prime_sur_le_manager(self):
        """Une dépense d'équipe pèse sur le budget de l'équipe, même si son
        propriétaire dispose d'une enveloppe personnelle."""
        self.assertEqual(
            self._imputer(team=self.team, owner=self.manager), self.enveloppe_equipe
        )

    def test_le_manager_a_defaut_d_enveloppe_d_equipe(self):
        """Une ligne soumise porte toujours son équipe et son manager (§7) :
        le repli se joue sur les enveloppes, pas sur les champs vides."""
        self.enveloppe_equipe.is_active = False
        self.enveloppe_equipe.save()

        self.assertEqual(
            self._imputer(team=self.team, owner=self.manager), self.enveloppe_manager
        )

    def test_le_projet_prime_sur_tout(self):
        projet = Project.objects.create(country=self.togo, name="Campagne")
        enveloppe_projet = Budget.objects.create(
            country=self.togo, year=self.year, project=projet,
            amount=Decimal("300000.00"),
        )

        self.assertEqual(
            self._imputer(project=projet, team=self.team, owner=self.manager),
            enveloppe_projet,
        )

    def test_repli_sur_l_enveloppe_du_pays(self):
        self.enveloppe_equipe.is_active = False
        self.enveloppe_equipe.save()
        self.enveloppe_manager.is_active = False
        self.enveloppe_manager.save()

        self.assertEqual(
            self._imputer(team=self.team, owner=self.manager), self.budget
        )


class LocalTimeTests(ExpenseTestCase):
    """§6 : l'heure se lit dans le fuseau du pays, pas dans celui du lecteur."""

    def test_le_fuseau_du_pays_accompagne_la_depense(self):
        expense = self.make_expense()
        self.login(self.controller)

        response = self.client.get(f"/api/expenses/{expense.pk}/")

        self.assertEqual(response.data["country_timezone"], "Africa/Lome")

    def test_le_fuseau_accompagne_aussi_le_dossier(self):
        self.login(self.controller)

        response = self.client.get(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.data["country_timezone"], "Africa/Lome")

    def test_le_registre_porte_le_fuseau(self):
        self.make_expense()
        self.login(self.controller)

        response = self.client.get("/api/expenses/register/")

        self.assertEqual(
            response.data["results"][0]["country_timezone"], "Africa/Lome"
        )


class SeparationOfDutiesTests(ExpenseTestCase):
    """Le pays déclare, le siège constate — le DM met en contrôle, le DF
    tranche. Personne ne se donne quitus."""

    def setUp(self):
        super().setUp()
        self.rep_togo = make_user("togo.innov", Role.MANAGER, [self.togo])
        self.dm = make_user("dm.innov", Role.DM)
        self.expense = self.make_expense(created_by="owner.togo")
        self.submit_dossier()

    def _declarer(self, created_by, numero="N-0002"):
        """Une ligne d'un autre auteur, déclarée dans son propre dossier."""
        dossier = Dossier.objects.create(
            number=numero, label="Autre mission", country=self.togo,
            date=date(self.year, 3, 16), created_by=self.owner.username,
        )
        ligne = self.make_expense(dossier=dossier, created_by=created_by)
        self.submit_dossier(dossier)
        return ligne

    def test_un_pays_ne_justifie_pas_ses_propres_depenses(self):
        """Faille trouvée en recette : un responsable pays pouvait justifier
        les dépenses de son propre pays."""
        self.login(self.rep_togo)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.SUBMITTED)

    def test_un_pays_ne_declare_pas_non_plus_une_depense_non_justifiee(self):
        self.login(self.rep_togo)

        response = self.client.post(
            f"/api/expenses/{self.expense.pk}/reject/", {"note": "Sans preuve"}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_un_pays_ne_prend_pas_une_depense_en_controle(self):
        self.login(self.rep_togo)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/review/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_un_pays_ne_cloture_pas(self):
        self.login(self.controller)
        self.client.post(f"/api/expenses/{self.expense.pk}/justify/")
        self.login(self.rep_togo)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/close/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_dm_met_en_controle(self):
        """Premier temps du contrôle, au siège : la ligne et le dossier."""
        self.login(self.dm)

        ligne = self.client.post(f"/api/expenses/{self.expense.pk}/review/")
        dossier = self.client.post(f"/api/dossiers/{self.dossier.pk}/review/")

        self.assertEqual(ligne.status_code, status.HTTP_200_OK, ligne.data)
        self.assertEqual(ligne.data["status"], Status.IN_REVIEW)
        self.assertEqual(dossier.status_code, status.HTTP_200_OK, dossier.data)
        self.assertEqual(dossier.data["status"], Status.IN_REVIEW)

    def test_le_dm_ne_tranche_pas(self):
        """Mettre en contrôle n'est pas conclure : justifier, rejeter et
        clore reviennent au DF, son supérieur."""
        self.login(self.dm)
        self.client.post(f"/api/expenses/{self.expense.pk}/review/")

        justify = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")
        reject = self.client.post(
            f"/api/expenses/{self.expense.pk}/reject/", {"note": "Sans preuve"}
        )
        dossier = self.client.post(f"/api/dossiers/{self.dossier.pk}/justify/")

        for response in (justify, reject, dossier):
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.IN_REVIEW)

    def test_le_dm_ne_declare_pas(self):
        """Le DM est au siège : il ne saisit ni ne soumet — celui qui met en
        contrôle ne peut pas être celui qui a déclaré."""
        self.login(self.dm)

        response = self.client.post(
            "/api/dossiers/",
            {"label": "Mission DM", "country": self.togo.pk,
             "date": date(self.year, 4, 1).isoformat()},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_siege_justifie(self):
        self.login(self.controller)

        response = self.client.post(f"/api/expenses/{self.expense.pk}/justify/")

        self.assertEqual(response.data["status"], Status.JUSTIFIED)

    def test_nul_ne_justifie_la_depense_qu_il_a_saisie(self):
        """Même au siège : décaisser puis se donner quitus n'est pas un
        contrôle."""
        propre = self._declarer(self.controller.username)

        self.login(self.controller)
        response = self.client.post(f"/api/expenses/{propre.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("quelqu'un d'autre", str(response.data))

    def test_nul_ne_prend_en_controle_la_depense_qu_il_a_saisie(self):
        """La mise en contrôle est déjà un acte de contrôle."""
        propre = self._declarer(self.controller.username)

        self.login(self.controller)
        response = self.client.post(f"/api/expenses/{propre.pk}/review/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_une_ligne_sans_auteur_connu_ne_se_controle_pas(self):
        """Sans auteur, la règle des quatre yeux est invérifiable : on ne
        tranche pas une ligne d'origine inconnue."""
        anonyme = self._declarer("")

        self.login(self.controller)
        response = self.client.post(f"/api/expenses/{anonyme.pk}/justify/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("created_by", response.data)

    def test_un_autre_controleur_peut_justifier(self):
        propre = self._declarer(self.controller.username)

        autre = make_user("audit.siege", Role.SUPER_ADMIN)
        self.login(autre)
        response = self.client.post(f"/api/expenses/{propre.pk}/justify/")

        self.assertEqual(response.data["status"], Status.JUSTIFIED)


class DossierSubmissionTests(ExpenseTestCase):
    """Côté pays, déclarer tient en une action : remplir, joindre, soumettre."""

    def test_le_dossier_emporte_ses_lignes(self):
        premiere = self.make_expense(amount="1000.00")
        seconde = self.make_expense(amount="2000.00")

        response = self.submit_dossier()

        self.assertEqual(response.data["status"], Status.SUBMITTED)
        premiere.refresh_from_db()
        seconde.refresh_from_db()
        self.assertEqual(premiere.status, Status.SUBMITTED)
        self.assertEqual(seconde.status, Status.SUBMITTED)
        self.assertEqual(premiere.budget, self.budget)

    def test_un_dossier_sans_ligne_ne_se_soumet_pas(self):
        """« Avant tout il doit remplir les lignes »."""
        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expenses", response.data)

    def test_soumettre_sans_piece_passe_mais_avertit(self):
        """Bloquer reviendrait à ce qu'une dépense sans reçu ne soit jamais
        déclarée : l'argent sortirait sans laisser de trace."""
        self.make_expense(amount="1000.00")

        response = self.submit_dossier()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("sans preuve", response.data["warning"])

    def test_les_lignes_soumises_engagent_l_enveloppe(self):
        self.make_expense(amount="120000.00")
        self.make_expense(amount="80000.00")

        self.submit_dossier()

        figures = budget_figures(self.budget)
        self.assertEqual(figures["engaged"], Decimal("200000.00"))

    def test_chaque_ligne_emportee_est_journalisee(self):
        self.make_expense(amount="1000.00")
        self.make_expense(amount="2000.00")

        self.submit_dossier()

        entrees = AuditLog.objects.filter(
            object_type="Expense", action=AuditLog.Action.SUBMITTED
        )
        self.assertEqual(entrees.count(), 2)
        premiere = entrees.first()
        self.assertEqual(premiere.detail["note"], "soumise avec son dossier")
        self.assertEqual(premiere.user, "owner.togo")
        self.assertEqual(premiere.country, self.togo)
        self.assertIsNotNone(premiere.ip_address)

    def test_une_ligne_deja_soumise_n_est_pas_resoumise(self):
        deja = self.make_expense(amount="1000.00", status=Status.JUSTIFIED)
        self.make_expense(amount="2000.00")

        self.submit_dossier()

        deja.refresh_from_db()
        self.assertEqual(deja.status, Status.JUSTIFIED)

    def test_le_controle_est_prevenu_une_fois_par_dossier(self):
        """Un dossier de vingt lignes ne doit pas produire vingt notifications."""
        from notifications.models import Notification

        for _ in range(3):
            self.make_expense(amount="1000.00")

        self.submit_dossier()

        recues = Notification.objects.filter(
            recipient=self.controller, kind=Notification.Kind.EXPENSE_SUBMITTED
        )
        self.assertEqual(recues.count(), 1)
        self.assertIn(self.dossier.number, recues.get().title)
