"""Exports : cellules sûres, montants exacts, périmètre et trace."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest import mock

from openpyxl import Workbook, load_workbook
from rest_framework import status

from budget.models import Budget
from expenses.models import AuditLog, Dossier
from expenses.tests.base import in_memory_storage
from expenses.workflow import Status
from reporting import exports
from reporting.tests.test_dashboard import DashboardTestCase


def _colonne(sheet, nom):
    entetes = [cell.value for cell in sheet[1]]
    index = entetes.index(nom) + 1
    return [sheet.cell(row=r, column=index) for r in range(2, sheet.max_row + 1)]


class CelluleSureTests(DashboardTestCase):
    def test_un_libelle_en_forme_de_formule_est_ecrit_en_texte(self):
        """Un libellé « =HYPERLINK(...) » s'exécuterait à l'ouverture du
        classeur sur le poste du contrôleur."""
        piege = '=HYPERLINK("http://exemple.test";"cliquez")'
        self.make_expense(title=piege, status=Status.JUSTIFIED)
        self.login(self.doo)

        response = self.client.get("/api/exports/expenses.xlsx", {"year": self.year})

        sheet = load_workbook(BytesIO(response.content)).active
        cellule = next(c for c in _colonne(sheet, "LIBELLE DES TRANSACTIONS") if c.value == piege)
        self.assertEqual(cellule.data_type, "s")

    def test_chaque_prefixe_dangereux_est_neutralise(self):
        sheet = Workbook().active
        for prefixe in ("=", "+", "-", "@", "\t", "\r"):
            with self.subTest(prefixe=repr(prefixe)):
                cellule = exports.ecrire(sheet, 1, 1, prefixe + "SUM(A1)")
                self.assertEqual(cellule.data_type, "s")
        self.assertEqual(exports.ecrire(sheet, 1, 2, "Carburant").data_type, "s")
        self.assertFalse(exports.cellule_sure(Decimal("1.00")))

    def test_le_libelle_du_dossier_est_aussi_protege(self):
        self.dossier.label = "@SUM(1+1)"
        self.dossier.save()
        self.login(self.doo)

        response = self.client.get("/api/exports/reconciliation.xlsx", {"year": self.year})

        detail = load_workbook(BytesIO(response.content))["Rapprochement dossiers"]
        cellule = next(c for c in _colonne(detail, "LIBELLE") if c.value == "@SUM(1+1)")
        self.assertEqual(cellule.data_type, "s")


class MontantsExactsTests(DashboardTestCase):
    def test_les_montants_sont_ecrits_en_decimal(self):
        """Passer par ``float`` introduit des arrondis binaires dans un
        rapport dont la raison d'être est l'exactitude des écarts."""
        sheet = Workbook().active

        cellule = exports.ecrire(sheet, 1, 1, Decimal("12345678901234.56"))

        self.assertIsInstance(cellule.value, Decimal)
        self.assertEqual(cellule.data_type, "n")

    def test_le_classeur_relu_porte_le_montant_exact(self):
        self.login(self.doo)

        response = self.client.get("/api/exports/expenses.xlsx", {"year": self.year})

        sheet = load_workbook(BytesIO(response.content)).active
        montants = {c.value for c in _colonne(sheet, "DEPENSES")}
        self.assertIn(300000, montants)


class SousEnveloppesTests(DashboardTestCase):
    def test_une_sous_enveloppe_d_equipe_est_libellee(self):
        Budget.objects.create(
            country=self.togo, year=self.year, team=self.team,
            amount=Decimal("100000.00"),
        )
        self.login(self.doo)

        response = self.client.get("/api/exports/reconciliation.xlsx", {"year": self.year})

        sheet = load_workbook(BytesIO(response.content))["Rapprochement budgets"]
        libelles = {c.value for c in _colonne(sheet, "ENVELOPPE")}
        self.assertIn("Équipe Équipe Lomé", libelles)
        self.assertIn("Enveloppe du pays", libelles)


class PerimetreEtTraceTests(DashboardTestCase):
    def test_un_pays_inconnu_repond_404_sans_trace(self):
        """Régression : l'audit de l'export échouait sur une clé étrangère
        inexistante, en erreur 500."""
        self.login(self.doo)

        response = self.client.get(
            "/api/exports/expenses.xlsx", {"year": self.year, "country": 999999}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(AuditLog.objects.filter(object_type="Export").exists())

    def test_un_pays_hors_perimetre_repond_404(self):
        self.login(self.rep_ivoire)

        response = self.client.get(
            "/api/exports/expenses.xlsx", {"year": self.year, "country": self.togo.pk}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_une_annee_invalide_repond_400(self):
        self.login(self.doo)

        response = self.client.get("/api/exports/expenses.xlsx", {"year": "2024;rm"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_le_nom_du_fichier_reprend_l_annee_validee(self):
        self.login(self.doo)

        response = self.client.get("/api/exports/expenses.xlsx", {"year": "02024"})

        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="depenses-2024.xlsx"'
        )

    def test_la_trace_porte_l_adresse_du_client(self):
        self.login(self.doo)

        self.client.get(
            "/api/exports/report.pdf", {"year": self.year},
            REMOTE_ADDR="10.20.30.40", HTTP_X_FORWARDED_FOR="1.2.3.4",
        )

        entry = AuditLog.objects.get(object_type="Export")
        self.assertEqual(entry.ip_address, "10.20.30.40")
        self.assertEqual(entry.detail["year"], self.year)


@in_memory_storage
class RapportPdfTests(DashboardTestCase):
    def test_la_troncature_est_annoncee(self):
        self.assertIsNone(exports.avertissement_troncature(exports.MAX_DOSSIERS_PDF))
        with mock.patch.object(exports, "MAX_DOSSIERS_PDF", 2):
            phrase = exports.avertissement_troncature(5)
        self.assertIn("2 dossiers", phrase)
        self.assertIn("sur 5", phrase)

    def test_le_rapport_se_construit_avec_l_avertissement(self):
        for index in range(3):
            Dossier.objects.create(
                number=f"P-{index}", label=f"Dossier {index}", country=self.togo,
                date=date(self.year, 2, 1), status=Status.SUBMITTED,
            )
        self.login(self.doo)

        with mock.patch.object(exports, "MAX_DOSSIERS_PDF", 2), mock.patch.object(
            exports, "avertissement_troncature", wraps=exports.avertissement_troncature
        ) as avertissement:
            response = self.client.get("/api/exports/report.pdf", {"year": self.year})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.content.startswith(b"%PDF"))
        avertissement.assert_called_once_with(4)
