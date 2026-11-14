"""Chaque pays retrouve son fuseau (décision 128, ``core.0020``)."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase

from reporting.tests.sans_vues_bi import SansVuesBI

AVANT = [("core", "0019_interrupteur_de_la_corbeille")]
APRES = [("core", "0020_fuseaux_des_filiales")]
AUTEUR = "migration core.0020_fuseaux_des_filiales"


class CorrectionDesFuseauxTests(SansVuesBI, TransactionTestCase):
    def _migrer(self, cible):
        executor = MigrationExecutor(connection)
        executor.migrate(cible)
        executor.loader.build_graph()
        return executor.loader.project_state(cible).apps

    def test_un_fuseau_faux_est_corrige_et_trace_un_fuseau_juste_reste(self):
        apps = self._migrer(AVANT)
        try:
            Country = apps.get_model("core", "Country")
            for nom, code, devise, fuseau in (
                ("Bénin", "BJ", "XOF", "UTC"),
                ("Gabon", "GA", "XAF", "GMT"),
                ("Togo", "TG", "XOF", "Africa/Lome"),
                # Le second fuseau de la RDC est l'un des siens : il reste.
                ("RDC", "CD", "CDF", "Africa/Lubumbashi"),
            ):
                Country.objects.create(
                    name=nom, code=code, country_ref=f"{code}-01", currency=devise,
                    timezone=fuseau,
                )

            apps = self._migrer(APRES)
            Country = apps.get_model("core", "Country")
            ChangeLog = apps.get_model("core", "ChangeLog")

            self.assertEqual(
                dict(Country.objects.values_list("code", "timezone")),
                {
                    "BJ": "Africa/Porto-Novo",
                    "GA": "Africa/Libreville",
                    "TG": "Africa/Lome",
                    "CD": "Africa/Lubumbashi",
                },
            )
            traces = {
                t.label: t for t in ChangeLog.objects.filter(performed_by=AUTEUR)
            }
            self.assertEqual(set(traces), {"Bénin", "Gabon"})
            self.assertEqual(traces["Gabon"].diff, {"timezone": ["GMT", "Africa/Libreville"]})
            self.assertEqual(traces["Gabon"].action, "updated")
            self.assertEqual(traces["Gabon"].model_name, "country")
            self.assertIn("décision 128", traces["Bénin"].motif)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


class CopieFigeeDesFuseauxTests(SimpleTestCase):
    def test_la_migration_corrige_vers_un_fuseau_que_le_serveur_accepte(self):
        """Sa table est figée ; chaque fuseau officiel qu'elle pose doit
        rester accepté par ``core.africa``, sinon un pays corrigé ne serait
        plus modifiable que vers un autre fuseau."""
        import importlib

        from core.africa import FUSEAUX

        migration = importlib.import_module("core.migrations.0020_fuseaux_des_filiales")
        for code, fuseaux in migration.FUSEAUX.items():
            with self.subTest(code=code):
                self.assertIn(fuseaux[0], FUSEAUX[code])
