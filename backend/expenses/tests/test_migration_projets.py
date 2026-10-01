"""Reprise de la version 2.0 (décisions 101 et 103).

``core.0016`` pose la liste des types de dossiers et numérote les projets
existants ; ``expenses.0019`` range chaque dossier dans un projet, sans
toucher aux lignes.
"""

from datetime import date, datetime
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

AVANT = [("core", "0015_historique_des_beneficiaires"), ("expenses", "0018_contacts_des_beneficiaires")]
APRES = [("expenses", "0019_dossiers_dans_un_projet")]


class RepriseDesProjetsTests(TransactionTestCase):
    def _migrer(self, cible):
        executor = MigrationExecutor(connection)
        executor.migrate(cible)
        executor.loader.build_graph()
        return executor.loader.project_state(cible).apps

    def test_chaque_dossier_rejoint_un_projet_et_rien_d_autre_ne_bouge(self):
        apps = self._migrer(AVANT)
        try:
            Country = apps.get_model("core", "Country")
            Project = apps.get_model("core", "Project")
            Dossier = apps.get_model("expenses", "Dossier")
            Expense = apps.get_model("expenses", "Expense")
            togo = Country.objects.create(
                name="Togo", code="TG", currency="XOF", timezone="Africa/Lome",
            )
            benin = Country.objects.create(
                name="Bénin", code="BJ", currency="XOF", timezone="Africa/Porto-Novo",
            )
            pediatrie = Project.objects.create(country=togo, name="Gamme pédiatrique")
            cardio = Project.objects.create(country=togo, name="Gamme cardio")
            Project.objects.create(country=benin, name="Lancement Cotonou")
            # Les références suivent l'ordre de création, année comprise.
            Project.objects.filter(pk=pediatrie.pk).update(
                created_at=datetime(2025, 5, 2, tzinfo=dt_timezone.utc)
            )

            def dossier(numero, *projets_des_lignes):
                d = Dossier.objects.create(
                    number=numero, label=numero, country=togo, date=date(2026, 3, 1),
                )
                for projet in projets_des_lignes:
                    Expense.objects.create(
                        dossier=d, country=togo, date=datetime(2026, 3, 1, tzinfo=dt_timezone.utc),
                        title="Ligne", amount=Decimal("1000.00"), project=projet,
                    )
                return d

            unique = dossier("N-1", pediatrie, pediatrie)
            melange = dossier("N-2", pediatrie, cardio)
            sans_projet = dossier("N-3", pediatrie, None)
            vide = dossier("N-4")
            lignes_avant = sorted(Expense.objects.values_list("pk", "project_id", "budget_id"))

            apps = self._migrer(APRES)
            Project = apps.get_model("core", "Project")
            Dossier = apps.get_model("expenses", "Dossier")
            Expense = apps.get_model("expenses", "Expense")
            DossierKind = apps.get_model("core", "DossierKind")
            AuditLog = apps.get_model("expenses", "AuditLog")
            ChangeLog = apps.get_model("core", "ChangeLog")

            historique = Project.objects.get(country_id=togo.pk, is_historical=True)
            self.assertEqual(historique.reference, "TG-P-HIST")
            self.assertEqual(historique.kind, "")
            rangement = dict(Dossier.objects.values_list("number", "project_id"))
            self.assertEqual(rangement["N-1"], pediatrie.pk)
            for numero in ("N-2", "N-3", "N-4"):
                self.assertEqual(rangement[numero], historique.pk, numero)
            # Les dossiers gardent leur N°ORDRE, sans type ni rang.
            self.assertFalse(Dossier.objects.exclude(kind=None).exists())
            self.assertFalse(Dossier.objects.exclude(sequence=None).exists())

            # Les lignes ne bougent pas : ni projet, ni imputation.
            self.assertEqual(
                sorted(Expense.objects.values_list("pk", "project_id", "budget_id")),
                lignes_avant,
            )

            # Projets existants numérotés dans l'ordre de leur création,
            # restés sans type.
            references = dict(Project.objects.filter(is_historical=False).values_list("name", "reference"))
            self.assertEqual(references["Gamme pédiatrique"], "TG-P-2025-001")
            annee = Project.objects.get(name="Gamme cardio").created_at.year
            self.assertEqual(references["Gamme cardio"], f"TG-P-{annee}-001")
            self.assertEqual(references["Lancement Cotonou"], f"BJ-P-{annee}-001")
            self.assertFalse(Project.objects.exclude(kind="").exists())
            # Le Bénin n'a pas de dossier : pas de projet « Historique ».
            self.assertFalse(Project.objects.filter(country_id=benin.pk, is_historical=True).exists())

            # Liste de départ des types de dossiers.
            self.assertEqual(
                set(DossierKind.objects.filter(project_kind="voyage").values_list("name", flat=True)),
                {"Billets", "Carburant", "Hôtellerie", "Repas", "Forfait"},
            )
            self.assertEqual(DossierKind.objects.count(), 10)

            # Une trace par dossier rangé, par projet numéroté ou créé.
            self.assertEqual(
                AuditLog.objects.filter(object_type="Dossier", action="updated").count(), 4
            )
            self.assertEqual(ChangeLog.objects.filter(model_name="project").count(), 4)
            self.assertEqual(ChangeLog.objects.filter(model_name="dossier_kind").count(), 10)
            del unique, melange, sans_projet, vide
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
