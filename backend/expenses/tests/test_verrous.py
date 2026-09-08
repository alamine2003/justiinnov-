"""Courses réelles sur le circuit : deux connexions, un seul gagnant.

Le « stock » de cette application, c'est l'enveloppe : deux dossiers soumis
au même instant ne doivent pas la franchir chacun de leur côté quand sa
politique est de bloquer. Et une ligne ne se tranche qu'une fois : deux
membres du siège qui la justifient en même temps ne produisent qu'un
constat. Un ``TransactionTestCase`` est nécessaire : les autres tests
vivent dans une transaction jamais validée, invisible à une seconde
connexion (voir ``budget/tests/test_verrous.py``).
"""

import threading
import time
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.models import Budget, OverrunPolicy
from core.models import Country, Manager, Team
from expenses.models import AuditLog, Dossier, Expense, Proof
from expenses.services import committed_total
from expenses.workflow import Status


class CourseSurLeCircuit(TransactionTestCase):
    def setUp(self):
        self.togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        self.team = Team.objects.create(country=self.togo, name="Équipe Lomé")
        self.manager = Manager.objects.create(name="Kodjo Mensah")
        self.manager.countries.add(self.togo)
        self.year = timezone.now().year
        self.budget = Budget.objects.create(
            country=self.togo, year=self.year, amount=Decimal("1000000.00"),
            overrun_policy=OverrunPolicy.BLOCK,
        )
        self.owner = make_user("owner.togo", Role.MANAGER, [self.togo])
        self.df = make_user("df.innov", Role.DF)
        self.df_bis = make_user("df2.innov", Role.DF)

    def _client(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def _dossier(self, numero, montant, statut=Status.DRAFT):
        dossier = Dossier.objects.create(
            number=numero, label=f"Mission {numero}", country=self.togo,
            team=self.team, owner=self.manager, date=date(self.year, 3, 15),
            status=statut, created_by=self.owner.username,
        )
        Expense.objects.create(
            dossier=dossier, country=self.togo, team=self.team, owner=self.manager,
            date=timezone.now(), title="Carburant", amount=Decimal(montant),
            created_by=self.owner.username, status=statut,
            budget=self.budget if statut != Status.DRAFT else None,
        )
        return dossier

    def _attendre_une_session_bloquee(self, delai=10):
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
                if cursor.fetchone()[0]:
                    return True
            time.sleep(0.05)
        return False

    def _en_course(self, premiere, seconde):
        """Joue ``premiere`` sous transaction ouverte, ``seconde`` dans un
        autre fil qui doit attendre le verrou, puis rend les deux réponses."""
        resultats = {}

        def concurrent():
            try:
                resultats["seconde"] = seconde()
            finally:
                connection.close()

        fil = threading.Thread(target=concurrent)
        with transaction.atomic():
            resultats["premiere"] = premiere()
            fil.start()
            resultats["bloquee"] = self._attendre_une_session_bloquee()
        fil.join(timeout=10)
        self.assertFalse(fil.is_alive(), "la seconde requête n'a pas abouti")
        self.assertTrue(resultats["bloquee"], "la seconde requête aurait dû attendre le verrou")
        return resultats["premiere"], resultats["seconde"]

    def test_deux_soumissions_ne_franchissent_pas_l_enveloppe(self):
        """Deux dossiers de 600 000 sur une enveloppe de 1 000 000 qui
        bloque : le premier passe, le second attend le verrou puis est
        refusé — jamais 1 200 000 d'engagés."""
        premier = self._dossier("N-0001", "600000.00")
        second = self._dossier("N-0002", "600000.00")
        client = self._client(self.owner)

        premiere, seconde = self._en_course(
            lambda: client.post(f"/api/dossiers/{premier.pk}/submit/"),
            lambda: self._client(self.owner).post(f"/api/dossiers/{second.pk}/submit/"),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        self.assertIn("amount", seconde.data)
        self.assertEqual(committed_total(self.budget), Decimal("600000.00"))
        self.assertEqual(Dossier.objects.get(pk=second.pk).status, Status.DRAFT)
        self.assertEqual(Expense.objects.filter(status=Status.SUBMITTED).count(), 1)

    def test_une_ligne_ne_se_justifie_qu_une_fois(self):
        """Deux DF tranchent la même ligne au même instant : un constat,
        une trace, et le second apprend que c'est déjà fait."""
        dossier = self._dossier("N-0003", "100000.00", statut=Status.SUBMITTED)
        ligne = dossier.expenses.get()
        url = f"/api/expenses/{ligne.pk}/justify/"

        premiere, seconde = self._en_course(
            lambda: self._client(self.df).post(url),
            lambda: self._client(self.df_bis).post(url),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        self.assertIn("status", seconde.data)
        ligne.refresh_from_db()
        self.assertEqual(ligne.status, Status.JUSTIFIED)
        self.assertEqual(ligne.justified_amount, Decimal("100000.00"))
        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.JUSTIFIED, object_id=ligne.pk).count(), 1
        )

    def test_le_meme_dossier_ne_se_soumet_qu_une_fois(self):
        """Deux clics sur « Soumettre » : le second attend le verrou du
        dossier puis apprend qu'il est déjà déclaré ; une seule trace."""
        dossier = self._dossier("N-0004", "1000.00")
        url = f"/api/dossiers/{dossier.pk}/submit/"

        premiere, seconde = self._en_course(
            lambda: self._client(self.owner).post(url),
            lambda: self._client(self.owner).post(url),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.SUBMITTED, object_type="Dossier", object_id=dossier.pk).count(), 1
        )

    def test_justifier_et_refuser_la_meme_ligne_au_meme_instant(self):
        """L'un justifie, l'autre refuse : le premier constat tient, le
        second est refusé, la ligne n'a qu'un état et qu'une trace."""
        dossier = self._dossier("N-0005", "100000.00", statut=Status.SUBMITTED)
        ligne = dossier.expenses.get()

        premiere, seconde = self._en_course(
            lambda: self._client(self.df).post(f"/api/expenses/{ligne.pk}/justify/"),
            lambda: self._client(self.df_bis).post(
                f"/api/expenses/{ligne.pk}/reject/", {"note": "Sans reçu"}, format="json"
            ),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        ligne.refresh_from_db()
        self.assertEqual(ligne.status, Status.JUSTIFIED)
        self.assertEqual(
            AuditLog.objects.filter(
                object_id=ligne.pk, action__in=[AuditLog.Action.JUSTIFIED, AuditLog.Action.REJECTED]
            ).count(),
            1,
        )

    def test_deux_reouvertures_simultanees(self):
        """Deux administrateurs rouvrent le même dossier : une réouverture,
        une notification, une trace par ligne."""
        admin = make_user("rh.innov", Role.ADMIN)
        admin_bis = make_user("rh2.innov", Role.ADMIN)
        dossier = self._dossier("N-0006", "100000.00", statut=Status.SUBMITTED)
        url = f"/api/dossiers/{dossier.pk}/reopen/"

        premiere, seconde = self._en_course(
            lambda: self._client(admin).post(url, {"note": "Montant douteux"}, format="json"),
            lambda: self._client(admin_bis).post(url, {"note": "Montant douteux"}, format="json"),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.REOPENED).count(), 2)  # dossier + sa ligne

    def test_le_meme_fichier_depose_deux_fois_en_meme_temps(self):
        """Deux dépôts simultanés du même justificatif : la vérification du
        sérialiseur ne voit pas l'autre transaction, la contrainte d'unicité
        en base tranche — une pièce, pas deux."""
        dossier = self._dossier("N-0007", "1000.00")
        contenu = b"%PDF-1.4 recu de mission"

        def deposer():
            return self._client(self.owner).post(
                "/api/proofs/",
                {"dossier": dossier.pk, "kind": "invoice",
                 "file": SimpleUploadedFile("recu.pdf", contenu, content_type="application/pdf")},
                format="multipart",
            )

        premiere, seconde = self._en_course(deposer, deposer)

        codes = sorted([premiere.status_code, seconde.status_code])
        self.assertEqual(codes, [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST], (premiere.data, seconde.data))
        self.assertEqual(Proof.objects.filter(dossier=dossier).count(), 1)


class CourseSurLaSaisie(CourseSurLeCircuit):
    """Audit du 8 septembre 2026, §3.6 et §3.7 : les écritures de saisie —
    modification d'une ligne ou d'un dossier, import — relisent l'état sous
    verrou avant d'écrire. Une modification validée sur un objet lu sans
    verrou écrasait ensuite l'état posé par une soumission passée
    entre-temps : la ligne revenait au brouillon, sans imputation, sans
    réouverture ni trace."""

    def test_une_modification_pendant_la_soumission_ne_ramene_pas_la_ligne_au_brouillon(self):
        dossier = self._dossier("N-0010", "1000.00")
        ligne = dossier.expenses.get()

        premiere, seconde = self._en_course(
            lambda: self._client(self.owner).post(f"/api/dossiers/{dossier.pk}/submit/"),
            lambda: self._client(self.owner).patch(
                f"/api/expenses/{ligne.pk}/", {"title": "Carburant corrigé"}, format="json"
            ),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        ligne.refresh_from_db()
        self.assertEqual(ligne.status, Status.SUBMITTED)
        self.assertEqual(ligne.budget_id, self.budget.pk)
        self.assertEqual(ligne.title, "Carburant")
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.UPDATED).exists())

    def test_une_modification_du_dossier_pendant_sa_soumission_est_refusee(self):
        dossier = self._dossier("N-0011", "1000.00")

        premiere, seconde = self._en_course(
            lambda: self._client(self.owner).post(f"/api/dossiers/{dossier.pk}/submit/"),
            lambda: self._client(self.owner).patch(
                f"/api/dossiers/{dossier.pk}/", {"label": "Mission renommée"}, format="json"
            ),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_400_BAD_REQUEST, seconde.data)
        dossier.refresh_from_db()
        self.assertEqual(dossier.status, Status.SUBMITTED)
        self.assertEqual(dossier.label, "Mission N-0011")

    def test_deux_modifications_simultanees_ne_perdent_rien(self):
        """Deux corrections du même brouillon : la seconde attend la
        première et repart de l'état écrit — les deux changements restent."""
        dossier = self._dossier("N-0012", "1000.00")
        ligne = dossier.expenses.get()
        url = f"/api/expenses/{ligne.pk}/"

        premiere, seconde = self._en_course(
            lambda: self._client(self.owner).patch(url, {"title": "Péage"}, format="json"),
            lambda: self._client(self.owner).patch(url, {"amount": "2000.00"}, format="json"),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_200_OK, seconde.data)
        ligne.refresh_from_db()
        self.assertEqual((ligne.title, ligne.amount), ("Péage", Decimal("2000.00")))

    def test_une_ligne_ajoutee_pendant_le_retrait_du_dossier_ne_casse_rien(self):
        """L'auteur retire son brouillon pendant qu'une ligne s'y ajoute :
        l'ajout attend le verrou du dossier, puis apprend qu'il n'existe
        plus — pas de 500, pas de ligne orpheline, pas de fichier perdu."""
        dossier = self._dossier("N-0013", "1000.00")

        premiere, seconde = self._en_course(
            lambda: self._client(self.owner).delete(f"/api/dossiers/{dossier.pk}/"),
            lambda: self._client(self.owner).post(
                "/api/expenses/",
                {"dossier": dossier.pk, "country": self.togo.pk, "date": timezone.now().isoformat(),
                 "title": "Ajout tardif", "amount": "10.00", "team": self.team.pk, "owner": self.manager.pk},
                format="json",
            ),
        )

        self.assertEqual(premiere.status_code, status.HTTP_204_NO_CONTENT, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_404_NOT_FOUND, seconde.data)
        self.assertFalse(Dossier.objects.filter(pk=dossier.pk).exists())
        self.assertFalse(Expense.objects.filter(title="Ajout tardif").exists())


class CourseSurLImport(CourseSurLeCircuit):
    """Deux imports du même classeur, ou un import pendant une soumission :
    la base et le verrou du dossier tranchent ce que la validation ne peut
    pas voir."""

    def setUp(self):
        super().setUp()
        self.admin = make_user("rh.innov", Role.ADMIN)

    def _classeur(self, numero, lignes):
        from io import BytesIO

        from openpyxl import Workbook

        from reporting.exports import EXPENSE_COLUMNS

        entetes = [titre for titre, _ in EXPENSE_COLUMNS]
        workbook = Workbook()
        feuille = workbook.active
        feuille.title = "BASE DE DONNEES ACTIONS"
        feuille.append(entetes)
        for libelle, montant in lignes:
            ligne = {
                "N°ORDRE": numero, "DATE": f"15/03/{self.year} 12:30", "PAYS": "Togo",
                "TEAM": "Équipe Lomé", "OWNER": "Kodjo Mensah",
                "LIBELLE DES TRANSACTIONS": libelle, "DEPENSES": montant,
            }
            feuille.append([ligne.get(entete) for entete in entetes])
        contenu = BytesIO()
        workbook.save(contenu)
        return contenu.getvalue()

    def _importer(self, contenu):
        return self._client(self.admin).post(
            "/api/imports/expenses.xlsx",
            {"file": SimpleUploadedFile("depenses.xlsx", contenu,
                                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            format="multipart",
        )

    def test_un_import_pendant_la_soumission_n_ajoute_rien_a_un_dossier_declare(self):
        dossier = self._dossier("N-0020", "1000.00")
        classeur = self._classeur("N-0020", [("Taxi", 500)])

        premiere, seconde = self._en_course(
            lambda: self._client(self.owner).post(f"/api/dossiers/{dossier.pk}/submit/"),
            lambda: self._importer(classeur),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(seconde.status_code, status.HTTP_200_OK, seconde.data)
        self.assertEqual(seconde.data["lignes_creees"], 0)
        self.assertIn("déjà déclaré", seconde.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.filter(dossier=dossier).count(), 1)
        self.assertFalse(Expense.objects.filter(dossier=dossier, status=Status.DRAFT).exists())

    def test_deux_imports_du_meme_classeur_n_ecrivent_les_lignes_qu_une_fois(self):
        """Le dossier existe déjà en brouillon : chaque import valide sans
        voir l'autre, le second attend le verrou du dossier, puis la
        contrainte refuse ses lignes — deux lignes en base, pas quatre."""
        self._dossier("N-0021", "1000.00")
        classeur = self._classeur("N-0021", [("Taxi", 500), ("Hôtel", 30000)])

        premiere, seconde = self._en_course(
            lambda: self._importer(classeur),
            lambda: self._importer(classeur),
        )

        self.assertEqual(premiere.status_code, status.HTTP_200_OK, premiere.data)
        self.assertEqual(premiere.data["lignes_creees"], 2)
        self.assertEqual(seconde.status_code, status.HTTP_200_OK, seconde.data)
        self.assertEqual(seconde.data["lignes_creees"], 0)
        self.assertIn("autre import", seconde.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.filter(title__in=["Taxi", "Hôtel"]).count(), 2)

    def test_un_nouvel_envoi_du_meme_classeur_est_refuse_ligne_par_ligne(self):
        self._dossier("N-0022", "1000.00")
        classeur = self._classeur("N-0022", [("Taxi", 500)])
        self.assertEqual(self._importer(classeur).data["lignes_creees"], 1)

        response = self._importer(classeur)

        self.assertEqual(response.data["lignes_creees"], 0)
        self.assertIn("déjà présente", response.data["erreurs"][0]["motif"])
        self.assertEqual(Expense.objects.filter(title="Taxi").count(), 1)
