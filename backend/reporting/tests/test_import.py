"""Import Excel des dépenses, dans le contrat produit par l'export."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest import mock
from urllib.parse import urlencode

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from openpyxl import Workbook

from budget.models import ExchangeRate
from core.models import Manager
from expenses.models import AuditLog, Dossier, Expense
from expenses.tests.base import ExpenseTestCase
from expenses.workflow import Status
from reporting import imports
from reporting.exports import EXPENSE_COLUMNS

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ImportTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        # Un manager se résout dans son pays : celui du socle n'y était pas
        # rattaché.
        self.togo.managers.add(self.manager)

    def _classeur(self, lignes, entetes=None):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "BASE DE DONNEES ACTIONS"
        entetes = entetes or [title for title, _ in EXPENSE_COLUMNS]
        sheet.append(entetes)
        for ligne in lignes:
            sheet.append([ligne.get(entete) for entete in entetes])
        contenu = BytesIO()
        workbook.save(contenu)
        contenu.seek(0)
        return contenu

    def _ligne(self, **overrides):
        ligne = {
            "N°ORDRE": "N-IMPORT-01",
            "DATE": f"15/03/{self.year} 12:30",
            "PAYS": "Togo",
            "TEAM": "Équipe Lomé",
            "OWNER": "Kodjo Mensah",
            "LIBELLE DES TRANSACTIONS": "Déplacement",
            "DEPENSES": 1200,
            "DEVISE D'ORIGINE": "",
            "MONTANT D'ORIGINE": "",
            "MONTANT JUSTIFIER": 800,
            "ECART": 400,
            "STATUT": "Brouillon",
            "PIECES JUSTIFICATIVES": "Facture",
        }
        ligne.update(overrides)
        return ligne

    def _importer(self, contenu, user=None, **query):
        self.login(user or self.owner)
        url = "/api/imports/expenses.xlsx"
        if query:
            url += "?" + urlencode(query)
        return self.client.post(
            url, {"file": ("depenses.xlsx", contenu, XLSX)}, format="multipart"
        )

    def test_un_classeur_exporte_se_reimporte(self):
        """Le siège exporte ; le pays réimporte : ce sont deux rôles."""
        self.make_expense(amount="1200.00", justified_amount="800.00")
        self.login(self.doo)
        export = self.client.get("/api/exports/expenses.xlsx", {"year": self.year})
        Expense.objects.all().delete()
        Dossier.objects.all().delete()

        response = self._importer(BytesIO(export.content), user=self.owner)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lignes_creees"], 1)
        self.assertFalse(response.data["erreurs"])
        expense = Expense.objects.get()
        self.assertEqual(str(expense.amount), "1200.00")
        # Le classeur portait 800 de justifié : l'import n'en tient pas compte.
        self.assertEqual(str(expense.justified_amount), "0.00")
        self.assertEqual(expense.status, Status.DRAFT)

    def test_un_role_de_lecture_ne_peut_pas_importer(self):
        """Importer, c'est déclarer : la direction constate, elle ne déclare pas."""
        response = self._importer(self._classeur([self._ligne()]), user=self.doo)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Expense.objects.count(), 0)

    def test_tout_arrive_en_brouillon(self):
        response = self._importer(self._classeur([self._ligne(STATUT="Justifié")]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Expense.objects.get().status, Status.DRAFT)
        self.assertEqual(Dossier.objects.get(number="N-IMPORT-01").status, Status.DRAFT)

    def test_le_montant_justifie_du_classeur_est_ignore(self):
        """Le pays déclare, le siège constate : un montant justifié ne
        s'importe pas, même s'il figure dans le fichier."""
        response = self._importer(
            self._classeur([self._ligne(**{"MONTANT JUSTIFIER": 1200})])
        )

        self.assertFalse(response.data["erreurs"])
        self.assertEqual(str(Expense.objects.get().justified_amount), "0.00")

    # -- Idempotence --------------------------------------------------------

    def test_reimporter_le_meme_classeur_ne_cree_rien(self):
        classeur = self._classeur([self._ligne(), self._ligne(**{"LIBELLE DES TRANSACTIONS": "Hôtel"})])
        self._importer(classeur)
        classeur.seek(0)

        response = self._importer(classeur)

        self.assertEqual(len(response.data["erreurs"]), 2)
        self.assertIn("déjà présente", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.count(), 2)

    def test_une_ligne_identique_dans_le_meme_classeur_est_refusee(self):
        response = self._importer(self._classeur([self._ligne(), self._ligne()]))

        self.assertEqual(len(response.data["erreurs"]), 1)
        self.assertEqual(response.data["erreurs"][0]["ligne"], 3)
        self.assertIn("ligne 2", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.count(), 0)

    def test_une_ligne_differente_s_ajoute_a_un_dossier_existant(self):
        self._importer(self._classeur([self._ligne()]))

        response = self._importer(self._classeur([self._ligne(DEPENSES=900)]))

        self.assertFalse(response.data["erreurs"])
        self.assertEqual(response.data["dossiers_crees"], 0)
        self.assertEqual(Expense.objects.count(), 2)

    # -- Managers -----------------------------------------------------------

    def test_le_manager_est_resolu_dans_le_pays_de_la_ligne(self):
        """Deux homonymes dans deux pays : la ligne prend celui de son pays."""
        homonyme = Manager.objects.create(name="Kodjo Mensah")
        self.ivoire.managers.add(homonyme)

        response = self._importer(self._classeur([self._ligne()]))

        self.assertFalse(response.data["erreurs"])
        self.assertEqual(Expense.objects.get().owner, self.manager)

    def test_un_manager_d_un_autre_pays_est_inconnu(self):
        voisin = Manager.objects.create(name="Awa Diop")
        self.ivoire.managers.add(voisin)

        response = self._importer(self._classeur([self._ligne(OWNER="Awa Diop")]))

        self.assertIn("inconnu", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.count(), 0)

    # -- Devise d'origine (§5.3) -------------------------------------------

    def test_un_decaissement_en_devise_est_converti_au_taux_fige(self):
        ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("655.957"), valid_from=date(2020, 1, 1)
        )

        response = self._importer(
            self._classeur([
                self._ligne(**{"DEVISE D'ORIGINE": "eur", "MONTANT D'ORIGINE": 100})
            ])
        )

        self.assertFalse(response.data["erreurs"])
        expense = Expense.objects.get()
        self.assertEqual(expense.original_currency, "EUR")
        self.assertEqual(str(expense.original_amount), "100.00")
        self.assertEqual(str(expense.amount), "65595.70")
        self.assertEqual(str(expense.original_rate), "655.957000")

    def test_devise_sans_montant_d_origine_refusee(self):
        response = self._importer(
            self._classeur([self._ligne(**{"DEVISE D'ORIGINE": "EUR"})])
        )

        self.assertIn("aucun des deux", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.count(), 0)

    def test_devise_sans_taux_refusee(self):
        response = self._importer(
            self._classeur([
                self._ligne(**{"DEVISE D'ORIGINE": "GBP", "MONTANT D'ORIGINE": 10})
            ])
        )

        self.assertIn("Aucun taux", response.data["erreurs"][0]["motif"])

    # -- Garde-fous ---------------------------------------------------------

    @override_settings(MAX_PROOF_SIZE=16)
    def test_un_classeur_trop_volumineux_est_refuse(self):
        response = self._importer(self._classeur([self._ligne()]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("volumineux", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.count(), 0)

    def test_le_nombre_de_lignes_est_plafonne(self):
        lignes = [self._ligne(**{"N°ORDRE": f"N-{i}"}) for i in range(3)]

        with mock.patch.object(imports, "LIGNES_MAX", 2):
            response = self._importer(self._classeur(lignes))

        self.assertIn("2 lignes", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.count(), 0)

    def test_les_longueurs_de_champs_sont_verifiees_ligne_par_ligne(self):
        response = self._importer(
            self._classeur([
                self._ligne(**{"N°ORDRE": "N" * 51}),
                self._ligne(**{"N°ORDRE": "N-2", "LIBELLE DES TRANSACTIONS": "L" * 251}),
                self._ligne(**{"N°ORDRE": "N-3", "DEVISE D'ORIGINE": "EURO", "MONTANT D'ORIGINE": 1}),
            ])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([e["ligne"] for e in response.data["erreurs"]], [2, 3, 4])
        for erreur in response.data["erreurs"]:
            self.assertIn("trop long", erreur["motif"])

    def test_les_montants_aberrants_sont_des_erreurs_de_ligne(self):
        """« NaN » et « Infinity » sont des Decimal valides, pas des montants."""
        response = self._importer(
            self._classeur([
                self._ligne(**{"N°ORDRE": "N-1", "DEPENSES": "NaN"}),
                self._ligne(**{"N°ORDRE": "N-2", "DEPENSES": "Infinity"}),
                self._ligne(**{"N°ORDRE": "N-3", "DEPENSES": "1" + "0" * 14}),
                self._ligne(**{"N°ORDRE": "N-4", "DEPENSES": "-5"}),
            ])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([e["ligne"] for e in response.data["erreurs"]], [2, 3, 4, 5])
        self.assertEqual(Expense.objects.count(), 0)

    def test_un_dossier_d_un_autre_pays_ne_se_devoile_pas(self):
        Dossier.objects.create(
            number="N-VOISIN", label="Abidjan", country=self.ivoire,
            date=date(self.year, 1, 10),
        )

        response = self._importer(self._classeur([self._ligne(**{"N°ORDRE": "N-VOISIN"})]))

        motif = response.data["erreurs"][0]["motif"]
        self.assertNotIn("autre pays", motif)
        self.assertNotIn("Côte", motif)
        self.assertIn("ne peut pas être utilisé", motif)
        self.assertEqual(Expense.objects.count(), 0)

    def test_le_lecteur_xml_protege_est_utilise_quand_il_est_installe(self):
        """openpyxl bascule sur defusedxml dès que le paquet est présent : le
        drapeau du module doit dire la même chose que lui."""
        from openpyxl.xml import DEFUSEDXML

        self.assertEqual(imports.DEFUSEDXML_DISPONIBLE, DEFUSEDXML)

    # -- Écriture -----------------------------------------------------------

    def test_les_lignes_sont_inserees_par_lots(self):
        lignes = [
            self._ligne(**{"LIBELLE DES TRANSACTIONS": f"Ligne {i}"}) for i in range(30)
        ]

        with CaptureQueriesContext(connection) as captured:
            response = self._importer(self._classeur(lignes))

        self.assertFalse(response.data["erreurs"])
        insertions = [
            q["sql"] for q in captured.captured_queries
            if 'INSERT INTO "expenses_expense"' in q["sql"]
        ]
        self.assertEqual(len(insertions), 1)
        self.assertEqual(Expense.objects.count(), 30)

    def test_l_import_laisse_une_trace_avec_l_adresse_du_client(self):
        self.login(self.owner)
        self.client.post(
            "/api/imports/expenses.xlsx",
            {"file": ("depenses.xlsx", self._classeur([self._ligne()]), XLSX)},
            format="multipart",
            REMOTE_ADDR="10.20.30.40",
            # Sans mandataire déclaré, un en-tête forgé n'est pas cru.
            HTTP_X_FORWARDED_FOR="1.2.3.4",
        )

        entry = AuditLog.objects.get(object_type="ExpenseImport")
        self.assertEqual(entry.action, AuditLog.Action.IMPORTED)
        self.assertEqual(entry.ip_address, "10.20.30.40")

    # -- Comportements conservés -------------------------------------------

    def test_un_pays_hors_perimetre_est_refuse(self):
        response = self._importer(self._classeur([self._ligne(PAYS="Côte d'Ivoire")]))

        self.assertEqual(response.data["erreurs"][0]["ligne"], 2)
        self.assertEqual(Expense.objects.count(), 0)

    def test_un_pays_inconnu_est_signale_sans_rien_creer(self):
        response = self._importer(self._classeur([self._ligne(PAYS="Bénin inconnu")]))

        self.assertEqual(response.data["erreurs"][0]["ligne"], 2)
        self.assertIn("inconnu", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.count(), 0)

    def test_la_previsualisation_n_ecrit_rien(self):
        avant = Expense.objects.count()
        response = self._importer(self._classeur([self._ligne()]), dry_run="true")

        self.assertEqual(response.data["dossiers_crees"], 1)
        self.assertEqual(response.data["lignes_creees"], 1)
        self.assertEqual(Expense.objects.count(), avant)

    def test_un_echec_partiel_n_ecrit_rien(self):
        response = self._importer(
            self._classeur([
                self._ligne(**{"N°ORDRE": "N-1"}),
                self._ligne(**{"N°ORDRE": "N-2", "DEPENSES": "12 000 F"}),
                self._ligne(**{"N°ORDRE": "N-3"}),
                self._ligne(**{"N°ORDRE": "N-4"}),
            ])
        )

        self.assertEqual(len(response.data["erreurs"]), 1)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(Dossier.objects.count(), 1)

    def test_un_dossier_deja_declare_est_refuse(self):
        self.dossier.status = Status.SUBMITTED
        self.dossier.save()
        response = self._importer(
            self._classeur([self._ligne(**{"N°ORDRE": self.dossier.number})])
        )

        self.assertIn("déclaré", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.count(), 0)

    def test_les_colonnes_sont_retrouvees_par_leur_en_tete(self):
        entetes = [title for title, _ in EXPENSE_COLUMNS][::-1]
        response = self._importer(self._classeur([self._ligne()], entetes))

        self.assertFalse(response.data["erreurs"])
        self.assertEqual(Expense.objects.get().title, "Déplacement")
