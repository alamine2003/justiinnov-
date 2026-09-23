"""Reprise des données par la décision 89 : trois rôles, déclaration au pays.

Trois migrations : ``accounts.0006_trois_roles`` désactive les comptes DM et
DF, qui n'ont plus de rôle, sans leur donner les droits d'un
administrateur ; ``accounts.0007_matrice_trois_roles`` retire ces rôles de
la matrice réglée ; ``expenses.0017_brouillons_du_siege_rendus_au_pays`` rend
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
APRES = [
    ("accounts", "0007_matrice_trois_roles"),
    ("expenses", "0017_brouillons_du_siege_rendus_au_pays"),
]


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
        Team = apps.get_model("core", "Team")
        Manager = apps.get_model("core", "Manager")
        Budget = apps.get_model("budget", "Budget")
        Dossier = apps.get_model("expenses", "Dossier")
        Expense = apps.get_model("expenses", "Expense")
        WorkflowConfiguration = apps.get_model("core", "WorkflowConfiguration")

        # Une matrice réglée sous l'ancien régime.
        WorkflowConfiguration.objects.update_or_create(pk=1, defaults={"capability_roles": {
            "history.read": ["dm", "df", "admin", "super_admin"],
            "data.import": ["admin", "super_admin"],
            "rectifications.request": ["manager", "admin", "dm"],
            "audit.read": ["super_admin"],
        }})
        togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-01", currency="XOF",
            timezone="Africa/Lome",
        )
        equipe = Team.objects.create(country=togo, name="Équipe Lomé")
        responsable = Manager.objects.create(name="Kodjo Mensah")
        responsable.countries.add(togo)
        Budget.objects.create(country=togo, year=2026, amount=Decimal("1000000.00"))
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

        def dossier(numero, auteur, statut="draft", **champs):
            return Dossier.objects.create(
                number=numero, label="Mission", country=togo, date=date(2026, 3, 1),
                status=statut, created_by=auteur, team=equipe, owner=responsable, **champs,
            )

        quand = datetime(2026, 3, 1, 12, tzinfo=tz.utc)

        def ligne(dossier_, auteur):
            return Expense.objects.create(
                dossier=dossier_, country=togo, date=quand, title="Taxi",
                amount=Decimal("100.00"), status="draft", created_by=auteur,
                team=equipe, owner=responsable,
            )

        # Un brouillon importé par la RH avant la décision 89.
        du_siege = dossier("N-SIEGE", "rh.innov")
        ligne_du_siege = ligne(du_siege, "rh.innov")
        # Un brouillon qu'un ancien DM avait ouvert.
        du_dm = dossier("N-DM", "dm.innov")
        # Un dossier de la RH déclaré puis rouvert : revenu au brouillon.
        rouvert = dossier("N-ROUVERT", "rh.innov", reopen_note="Facture illisible")
        du_pays = dossier("N-PAYS", "togo.innov")
        declare = dossier("N-DECLARE", "ceo.innov", statut="submitted")
        return {
            "du_siege": du_siege.pk, "ligne_du_siege": ligne_du_siege.pk,
            "du_dm": du_dm.pk, "rouvert": rouvert.pk,
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
            self.assertEqual(Dossier.objects.get(pk=pk["du_dm"]).created_by, "")
            self.assertEqual(Dossier.objects.get(pk=pk["rouvert"]).created_by, "")
            self.assertEqual(Dossier.objects.get(pk=pk["du_pays"]).created_by, "togo.innov")
            self.assertEqual(Dossier.objects.get(pk=pk["declare"]).created_by, "ceo.innov")
            traces = AuditLog.objects.filter(action="updated", detail__created_by__0="rh.innov")
            self.assertEqual(
                sorted(traces.values_list("object_type", flat=True)),
                ["Dossier", "Dossier", "Expense"],
            )

            # La matrice oublie le DM et le DF ; l'import et la demande de
            # rectification reprennent leur nouveau défaut ; le reste tient.
            WorkflowConfiguration = apps.get_model("core", "WorkflowConfiguration")
            self.assertEqual(WorkflowConfiguration.objects.get(pk=1).capability_roles, {
                "history.read": ["admin", "super_admin"],
                "audit.read": ["super_admin"],
            })
            matrice = ChangeLog.objects.get(model_name="workflow_configuration")
            self.assertEqual(
                sorted(matrice.changed_fields),
                ["data.import", "history.read", "rectifications.request"],
            )
            self.assertEqual(matrice.diff["data.import"], [["admin", "super_admin"], None])

            self._le_circuit_reprend(pk)
        finally:
            # Les autres tests attendent la base au dernier état.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def _le_circuit_reprend(self, pk):
        """Après la reprise, le circuit va jusqu'au bout sur ces brouillons.

        Le pays soumet le brouillon rendu, et en devient l'auteur ;
        l'administrateur peut alors le contrôler — une ligne sans auteur ne
        se contrôlerait jamais. Un dossier déjà déclaré puis rouvert, lui,
        ne se supprime pas, même sans auteur.
        """
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

        from django.contrib.auth.models import User

        from accounts.models import Role
        from accounts.permissions import get_access
        from accounts.tests.test_scoping import make_user
        from core.regles import RegleViolee
        from core.tests.aides import trace
        from expenses import transitions
        from expenses.models import Dossier, Expense
        from expenses.workflow import Status

        pays = User.objects.get(username="togo.innov")
        rh = User.objects.get(username="rh.innov")
        rendu = Dossier.objects.get(pk=pk["du_siege"])

        transitions.executer(rendu, "submit", get_access(pays), trace(pays))

        rendu.refresh_from_db()
        ligne = Expense.objects.get(pk=pk["ligne_du_siege"])
        self.assertEqual(rendu.created_by, "togo.innov")
        self.assertEqual(ligne.created_by, "togo.innov")
        transitions.executer(ligne, "justify", get_access(rh), trace(rh))
        transitions.cloturer(Expense.objects.get(pk=ligne.pk), get_access(rh), trace(rh))
        self.assertEqual(Expense.objects.get(pk=ligne.pk).status, Status.CLOSED)

        collegue = make_user("kofi.togo", Role.MANAGER, [rendu.country])
        with self.assertRaises(RegleViolee):
            transitions.retirer_brouillon(
                Dossier.objects.get(pk=pk["rouvert"]), get_access(collegue), trace(collegue)
            )
        self.assertTrue(Dossier.objects.filter(pk=pk["rouvert"]).exists())
