"""Les services du circuit (``expenses.transitions``), sans client HTTP.

Les tests des vues (``test_workflow``, ``test_reouverture``…) restent le
filet du contrat ; ceux-ci exercent les règles là où elles vivent
désormais : rôle, état de départ, motif, quatre yeux, lignes exigées,
dépassement, réouverture, trace.
"""

from decimal import Decimal

from accounts.models import Role
from accounts.permissions import get_access
from accounts.tests.test_scoping import make_user
from budget.models import OverrunPolicy
from core.journal import Trace
from core.regles import PermissionRefusee, RegleViolee
from expenses import transitions
from expenses.models import AuditLog, Dossier
from expenses.workflow import Status, TransitionError

from .base import ExpenseTestCase

ADRESSE = "41.79.0.10"


def trace(user):
    """La trace qu'une vue construirait depuis la requête."""
    return Trace(user=user.username, ip=ADRESSE, user_agent="Test", compte=user)


class ServicesDuCircuitTests(ExpenseTestCase):
    def setUp(self):
        self.ligne = self.make_expense()

    def soumettre(self, user=None):
        user = user or self.owner
        return transitions.soumettre(self.dossier, get_access(user), trace(user))

    def trancher(self, objet, action, user, **donnees):
        return transitions.trancher(
            objet, action, get_access(user), trace=trace(user), **donnees
        )

    # -- Soumission -----------------------------------------------------------

    def test_soumettre_declare_le_dossier_et_ses_lignes(self):
        resultat = self.soumettre()

        self.ligne.refresh_from_db()
        self.assertEqual(resultat.instance.status, Status.SUBMITTED)
        self.assertEqual(self.ligne.status, Status.SUBMITTED)
        self.assertEqual(self.ligne.budget, self.budget)
        # Une trace pour le dossier, une par ligne.
        self.assertEqual(len(resultat.audit), 2)
        self.assertEqual(
            {e.object_type for e in resultat.audit}, {"Dossier", "Expense"}
        )
        # Sans pièce : le pays est prévenu, la soumission passe.
        self.assertIn("sans preuve", resultat.warning)

    def test_un_dossier_vide_ne_se_soumet_pas(self):
        vide = Dossier.objects.create(
            number="N-0002", label="Vide", country=self.togo,
            date=self.dossier.date, created_by=self.owner.username,
        )

        with self.assertRaises(RegleViolee) as refus:
            transitions.soumettre(vide, get_access(self.owner), trace(self.owner))

        self.assertEqual(refus.exception.champ, "expenses")

    def test_le_role_est_verifie_par_le_service(self):
        """Le siège ne déclare pas : la matrice vaut aussi hors HTTP."""
        with self.assertRaises(PermissionRefusee):
            self.soumettre(self.controller)

        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.status, Status.DRAFT)

    def test_etat_de_depart_invalide(self):
        with self.assertRaises(TransitionError) as refus:
            transitions.mettre_en_controle(
                self.dossier, get_access(self.controller), trace(self.controller)
            )

        self.assertEqual(refus.exception.champ, "status")
        self.assertIn("Brouillon", str(refus.exception))

    # -- Dépassement --------------------------------------------------------

    def test_depassement_bloquant(self):
        self.budget.amount = Decimal("1.00")
        self.budget.overrun_policy = OverrunPolicy.BLOCK
        self.budget.save()

        with self.assertRaises(RegleViolee) as refus:
            self.soumettre()

        self.assertEqual(refus.exception.champ, "amount")
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.status, Status.DRAFT)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.SUBMITTED).exists())

    def test_depassement_avertissant(self):
        self.budget.amount = Decimal("1.00")
        self.budget.overrun_policy = OverrunPolicy.WARN
        self.budget.save()

        resultat = self.soumettre()

        self.assertIn("Dépassement", resultat.warning)
        self.assertEqual(resultat.instance.status, Status.SUBMITTED)

    # -- Contrôle -------------------------------------------------------------

    def test_un_rejet_sans_motif_est_refuse(self):
        self.soumettre()

        with self.assertRaises(RegleViolee) as refus:
            self.trancher(self.ligne, "reject", self.controller, note="  ")

        self.assertEqual(refus.exception.champ, "note")

    def test_quatre_yeux_sur_la_ligne(self):
        """Même au siège, celui qui a saisi ne tranche pas ce qu'il a saisi."""
        auteur = make_user("df.auteur", Role.DF)
        self.ligne.created_by = auteur.username
        self.ligne.save()
        self.soumettre()

        with self.assertRaises(PermissionRefusee):
            self.trancher(self.ligne, "justify", auteur)
        resultat = self.trancher(self.ligne, "justify", self.controller)

        self.assertEqual(resultat.instance.status, Status.JUSTIFIED)
        self.assertEqual(resultat.instance.justified_amount, self.ligne.amount)

    def test_quatre_yeux_sur_le_dossier(self):
        auteur = make_user("df.ouvreur", Role.DF)
        self.dossier.created_by = auteur.username
        self.dossier.save()
        self.soumettre()

        with self.assertRaises(PermissionRefusee):
            transitions.mettre_en_controle(self.dossier, get_access(auteur), trace(auteur))

    def test_une_ligne_sans_auteur_ne_se_controle_pas(self):
        self.ligne.created_by = ""
        self.ligne.save()
        self.soumettre()

        with self.assertRaises(RegleViolee) as refus:
            transitions.mettre_en_controle(
                self.ligne, get_access(self.controller), trace(self.controller)
            )

        self.assertEqual(refus.exception.champ, "created_by")

    def test_lignes_non_tranchees_bloquent_le_dossier(self):
        self.soumettre()

        with self.assertRaises(RegleViolee) as refus:
            self.trancher(self.dossier, "reject", self.controller, note="Rien")

        self.assertEqual(refus.exception.champ, "expenses")
        self.assertIn("Carburant", str(refus.exception))

    def test_le_montant_justifie_ne_depasse_pas_la_depense(self):
        self.soumettre()

        with self.assertRaises(RegleViolee) as refus:
            self.trancher(
                self.ligne, "justify", self.controller,
                justified_amount=Decimal("100000.01"),
            )

        self.assertEqual(refus.exception.champ, "justified_amount")
        self.ligne.refresh_from_db()
        self.assertEqual(self.ligne.status, Status.SUBMITTED)

    def test_le_rejet_remet_le_justifie_a_zero_et_se_journalise(self):
        self.soumettre()

        resultat = self.trancher(self.ligne, "reject", self.controller, note="Sans reçu")

        self.assertEqual(resultat.instance.status, Status.UNJUSTIFIED)
        self.assertEqual(resultat.instance.justified_amount, Decimal("0.00"))
        self.assertEqual(resultat.instance.control_note, "Sans reçu")
        entree = resultat.audit[0]
        self.assertEqual(entree.action, AuditLog.Action.UNJUSTIFIED)
        self.assertEqual(entree.detail["note"], "Sans reçu")
        self.assertEqual(entree.detail["before"]["status"], Status.SUBMITTED)

    def test_cloturer_apres_justification(self):
        self.soumettre()
        self.trancher(self.ligne, "justify", self.controller)

        resultat = transitions.cloturer(
            self.ligne, get_access(self.controller), trace(self.controller)
        )

        self.assertEqual(resultat.instance.status, Status.CLOSED)

    # -- Réouverture ----------------------------------------------------------

    def rouvrir(self, motif="Montant douteux", user=None):
        user = user or self.doo
        return transitions.rouvrir(self.dossier, get_access(user), motif, trace(user))

    def test_reouverture_ramene_le_dossier_et_ses_lignes_au_brouillon(self):
        self.soumettre()

        resultat = self.rouvrir()

        self.ligne.refresh_from_db()
        self.assertEqual(resultat.instance.status, Status.DRAFT)
        self.assertEqual(resultat.instance.reopen_note, "Montant douteux")
        self.assertEqual(self.ligne.status, Status.DRAFT)
        self.assertIsNone(self.ligne.budget)
        self.assertEqual(
            [e.object_type for e in resultat.audit], ["Expense", "Dossier"]
        )

    def test_reouverture_sans_motif_refusee(self):
        self.soumettre()

        with self.assertRaises(RegleViolee) as refus:
            self.rouvrir(motif="")

        self.assertEqual(refus.exception.champ, "note")

    def test_reouverture_refusee_quand_une_ligne_est_constatee(self):
        self.soumettre()
        self.trancher(self.ligne, "justify", self.controller)

        with self.assertRaises(RegleViolee) as refus:
            self.rouvrir()

        self.assertEqual(refus.exception.champ, "expenses")
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.status, Status.SUBMITTED)

    def test_reouverture_reservee_aux_administrateurs(self):
        self.soumettre()

        with self.assertRaises(PermissionRefusee):
            self.rouvrir(user=self.controller)

    # -- Brouillons -----------------------------------------------------------

    def test_un_tiers_ne_retire_pas_le_brouillon_d_autrui(self):
        autre = make_user("kofi.togo", Role.MANAGER, [self.togo])

        with self.assertRaises(PermissionRefusee):
            transitions.retirer_brouillon(self.ligne, get_access(autre), trace(autre))

    def test_un_element_declare_ne_se_retire_pas(self):
        self.soumettre()

        with self.assertRaises(RegleViolee) as refus:
            transitions.retirer_brouillon(
                self.ligne, get_access(self.owner), trace(self.owner)
            )

        self.assertEqual(refus.exception.champ, "status")

    def test_l_auteur_retire_son_brouillon_avec_sa_trace(self):
        resultat = transitions.retirer_brouillon(
            self.dossier, get_access(self.owner), trace(self.owner)
        )

        self.assertFalse(Dossier.objects.filter(pk=self.dossier.pk).exists())
        self.assertEqual(
            [e.object_type for e in resultat.audit], ["Expense", "Dossier"]
        )
        self.assertEqual(resultat.audit[-1].detail["lines"], 1)

    # -- Trace ----------------------------------------------------------------

    def test_la_trace_porte_l_auteur_et_l_adresse(self):
        resultat = self.soumettre()

        for entree in resultat.audit:
            entree.refresh_from_db()
            self.assertEqual(entree.user, "owner.togo")
            self.assertEqual(entree.ip_address, ADRESSE)
            self.assertEqual(entree.user_agent, "Test")
            self.assertEqual(entree.country, self.togo)
