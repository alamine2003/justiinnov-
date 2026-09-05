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
