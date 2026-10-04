"""La remise à zéro des essais, une seule fois, tracée (décision 113).

Hors brouillon, rien ne se supprime ; la seule porte est
``manage.py remise_a_zero_des_essais``. Elle compte sans rien retirer par
défaut, exige le nom de la base pour agir, refuse un compte qui
n'administre pas la plateforme, ne s'ouvre qu'une fois, et laisse au
journal une entrée par objet retiré — clôturé compris.
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from rest_framework import status

from budget.models import Budget
from core.models import Project
from core.statuts import Status
from expenses.models import (
    AuditLog,
    Dossier,
    Expense,
    FichierASupprimer,
    Proof,
    Rectification,
)

from .base import ExpenseTestCase

MOTIF = "Saisies d'essai avant l'ouverture aux filiales"
DUMP = "justi_innov-2026-10-04T120215Z.dump"


class RemiseAZeroTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.brouillon = self.make_expense(title="Hôtel", amount="25000.00")
        self.cloturee = self.make_expense(title="Taxi", amount="10000.00")
        self.make_expense(title="Repas", amount="5000.00")
        reponse = self.submit_dossier()
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        Expense.objects.filter(pk=self.cloturee.pk).update(
            status=Status.CLOSED, justified_amount=Decimal("10000.00")
        )
        for rang, ligne in enumerate((self.cloturee, self.brouillon)):
            Proof.objects.create(
                dossier=self.dossier, expense=ligne, file=f"justificatifs/f{rang}.pdf",
                original_name="facture.pdf", sha256=str(rang) * 64,
            )
        Rectification.objects.create(
            expense=self.cloturee, motif="Montant à revoir", requested_by="owner.togo",
            previous_status=Status.CLOSED, previous_justified_amount=Decimal("10000.00"),
        )

    def remettre_a_zero(self, *, compte=None, executer=True, base=None):
        sortie = StringIO()
        call_command(
            "remise_a_zero_des_essais", compte=(compte or self.controller).username,
            motif=MOTIF, sauvegarde=DUMP, executer=executer,
            base=connection.settings_dict["NAME"] if base is None else base, stdout=sortie,
        )
        return sortie.getvalue()

    def test_sans_executer_rien_ne_part(self):
        sortie = self.remettre_a_zero(executer=False)

        self.assertIn("À retirer : 1 dossier(s), 3 ligne(s), 2 pièce(s), 1 demande(s)", sortie)
        self.assertEqual(Expense.objects.count(), 3)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.PURGED).exists())

    def test_tout_part_et_chaque_objet_laisse_sa_trace(self):
        projets, enveloppes = Project.objects.count(), Budget.objects.count()

        self.remettre_a_zero()

        for modele in (Dossier, Expense, Proof, Rectification):
            self.assertFalse(modele.objects.exists(), modele.__name__)
        self.assertEqual(Project.objects.count(), projets)
        self.assertEqual(Budget.objects.count(), enveloppes)
        self.assertEqual(FichierASupprimer.objects.count(), 2)
        traces = AuditLog.objects.filter(action=AuditLog.Action.PURGED)
        self.assertEqual(
            sorted(traces.values_list("object_type", flat=True)),
            ["Dossier", "Expense", "Expense", "Expense", "Proof", "Proof", "Rectification"],
        )
        self.assertTrue(all(
            t.detail["motif"] == MOTIF and t.detail["sauvegarde"] == DUMP
            and t.user == self.controller.username for t in traces
        ))
        cloturee = traces.get(object_type="Expense", object_id=self.cloturee.pk)
        self.assertEqual(cloturee.detail["status"], Status.CLOSED)
        self.assertEqual(cloturee.detail["amount"], "10000.00")

    def test_la_base_se_recopie(self):
        with self.assertRaises(CommandError):
            self.remettre_a_zero(base="justi_innov")

        self.assertEqual(Expense.objects.count(), 3)

    def test_un_manager_ne_la_lance_pas(self):
        with self.assertRaises(CommandError):
            self.remettre_a_zero(compte=self.owner)

        self.assertEqual(Dossier.objects.count(), 1)

    def test_elle_ne_se_fait_qu_une_fois(self):
        self.remettre_a_zero()

        with self.assertRaises(CommandError):
            self.remettre_a_zero(executer=False)

    def test_la_synthese_de_l_audit_la_compte(self):
        self.remettre_a_zero()
        self.login(self.doo)

        reponse = self.client.get("/api/audit/synthese/")

        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data["compteurs"]["suppressions"], 7)
        self.assertIn("purged", {e["action"] for e in reponse.data["a_surveiller"]})
