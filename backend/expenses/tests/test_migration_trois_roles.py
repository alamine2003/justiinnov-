"""Reprise des données par la décision 89 : trois rôles, déclaration au pays.

Deux migrations : ``accounts.0006_trois_roles`` désactive les comptes DM et
DF, qui n'ont plus de rôle, sans leur donner les droits d'un
administrateur ; ``expenses.0017_brouillons_du_siege_rendus_au_pays`` rend
au pays les brouillons ouverts par le siège, que plus personne ne pourrait
finir. Le test remonte la base avant elles, y dépose ce qu'une base en
service peut porter, puis les rejoue.
"""

from datetime import date, datetime, timezone as tz
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

AVANT = [("accounts", "0005_totp_dernier_compteur"), ("expenses", "0016_index_de_tri_des_listes")]
APRES = [("expenses", "0017_brouillons_du_siege_rendus_au_pays")]


class TroisRolesTests(TransactionTestCase):
    def _migrer(self, cible):
        executor = MigrationExecutor(connection)
        executor.migrate(cible)
        executor.loader.build_graph()
        return executor.loader.project_state(cible).apps

    def _peupler(self, apps):
        User = apps.get_model("auth", "User")
        UserProfile = apps.get_model("accounts", "UserProfile")
        Country = apps.get_model("core", "Country")
        Dossier = apps.get_model("expenses", "Dossier")
        Expense = apps.get_model("expenses", "Expense")

        togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-01", currency="XOF",
            timezone="Africa/Lome",
        )
        comptes = {}
        for nom, role in (
            ("dm.innov", "dm"), ("df.innov", "df"), ("rh.innov", "admin"),
            ("ceo.innov", "super_admin"), ("togo.innov", "manager"),
        ):
            user = User.objects.create(username=nom, is_active=True, is_staff=role != "manager")
            profil = UserProfile.objects.create(user=user, role=role)
            if role in ("dm", "manager"):
                profil.countries.add(togo)
            comptes[nom] = user

        def dossier(numero, auteur, statut="draft"):
            return Dossier.objects.create(
                number=numero, label="Mission", country=togo, date=date(2026, 3, 1),
                status=statut, created_by=auteur,
            )

        quand = datetime(2026, 3, 1, 12, tzinfo=tz.utc)
        du_siege = dossier("N-SIEGE", "rh.innov")
        ligne_du_siege = Expense.objects.create(
            dossier=du_siege, country=togo, date=quand, title="Taxi",
            amount=Decimal("100.00"), status="draft", created_by="rh.innov",
        )
        du_pays = dossier("N-PAYS", "togo.innov")
        declare = dossier("N-DECLARE", "ceo.innov", statut="submitted")
        return {
            "du_siege": du_siege.pk, "ligne_du_siege": ligne_du_siege.pk,
            "du_pays": du_pays.pk, "declare": declare.pk,
        }

    def test_la_reprise_desactive_le_dm_et_le_df_et_rend_les_brouillons_au_pays(self):
        apps = self._migrer(AVANT)
        try:
            pk = self._peupler(apps)
            apps = self._migrer(APRES)
            User = apps.get_model("auth", "User")
            ChangeLog = apps.get_model("core", "ChangeLog")
            AuditLog = apps.get_model("expenses", "AuditLog")
            Dossier = apps.get_model("expenses", "Dossier")
            Expense = apps.get_model("expenses", "Expense")

            for nom, ancien in (("dm.innov", "dm"), ("df.innov", "df")):
                with self.subTest(compte=nom):
                    user = User.objects.get(username=nom)
                    # Désactivé, au rôle le moins étendu, sans drapeau du
                    # siège : un administrateur décidera de son sort.
                    self.assertFalse(user.is_active)
                    self.assertFalse(user.is_staff)
                    self.assertEqual(user.profile.role, "manager")
                    entree = ChangeLog.objects.get(model_name="user", object_id=user.pk)
                    self.assertEqual(entree.diff["role"], [ancien, "manager"])
                    self.assertEqual(entree.action, "deactivated")
            # Les autres comptes ne bougent pas.
            for nom, role in (("rh.innov", "admin"), ("ceo.innov", "super_admin"),
                              ("togo.innov", "manager")):
                user = User.objects.get(username=nom)
                self.assertTrue(user.is_active, nom)
                self.assertEqual(user.profile.role, role)

            # Le brouillon du siège revient au pays, tracé ; celui du pays et
            # le déclaré gardent leur auteur.
            self.assertEqual(Dossier.objects.get(pk=pk["du_siege"]).created_by, "")
            self.assertEqual(Expense.objects.get(pk=pk["ligne_du_siege"]).created_by, "")
            self.assertEqual(Dossier.objects.get(pk=pk["du_pays"]).created_by, "togo.innov")
            self.assertEqual(Dossier.objects.get(pk=pk["declare"]).created_by, "ceo.innov")
            traces = AuditLog.objects.filter(action="updated", detail__created_by__0="rh.innov")
            self.assertEqual(
                sorted(traces.values_list("object_type", flat=True)), ["Dossier", "Expense"]
            )
        finally:
            # Les autres tests attendent la base au dernier état.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
