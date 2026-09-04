"""Configuration singleton du workflow et droits du back-office."""

import json
from decimal import Decimal

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from rest_framework import status

from accounts.tests.test_scoping import ScopingTestCase
from core.models import ChangeLog, WorkflowConfiguration


class WorkflowConfigurationTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        WorkflowConfiguration.objects.all().delete()
        cache.clear()

    def test_une_seule_instance_peut_exister(self):
        """``objects.create()`` deux fois ne fait pas deux lignes : la seconde
        modifie l'unique, au lieu d'échouer sur l'insertion forcée."""
        WorkflowConfiguration.objects.create(require_review_step=True)
        WorkflowConfiguration.objects.create(require_review_step=False)

        self.assertEqual(WorkflowConfiguration.objects.count(), 1)
        self.assertFalse(WorkflowConfiguration.objects.get().require_review_step)

    def test_la_base_refuse_une_seconde_ligne(self):
        """La contrainte tient même en contournant ``save()``."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkflowConfiguration.objects.bulk_create(
                [WorkflowConfiguration(id=2)]
            )

    def test_la_suppression_est_refusee(self):
        configuration = WorkflowConfiguration.charger()

        with self.assertRaises(ProtectedError):
            configuration.delete()

    def test_les_valeurs_par_defaut_sont_celles_du_modele(self):
        """Des littéraux, pas ``settings`` : l'environnement n'intervient
        qu'au moment de l'amorçage par migration."""
        configuration = WorkflowConfiguration.charger()

        self.assertEqual(configuration.alert_thresholds, [80, 90, 100])
        self.assertEqual(configuration.unusual_expense_factor, Decimal("5"))
        self.assertEqual(configuration.unjustified_alert_days, 0)
        self.assertTrue(configuration.warn_without_proof_submission)
        self.assertEqual(configuration.default_overrun_policy, "block")

    def test_le_cache_est_invalide_a_l_enregistrement(self):
        configuration = WorkflowConfiguration.charger()
        # Le cache de base dépickle : égal, jamais identique.
        self.assertEqual(WorkflowConfiguration.charger(), configuration)

        configuration.require_review_step = True
        configuration.save()

        self.assertTrue(WorkflowConfiguration.charger().require_review_step)

    def test_un_pays_ne_peut_pas_lire_la_configuration(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/configuration/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_un_pays_ne_peut_pas_la_modifier(self):
        self.login(self.rep_togo)

        response = self.client.patch(
            "/api/workflow-configuration/", {"require_review_step": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_lecture_de_la_politique(self):
        self.login(self.siege)

        response = self.client.get("/api/workflow-configuration/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unusual_expense_factor"], "5.00")
        self.assertEqual(response.data["default_overrun_policy_display"], "Bloquer")

    def test_une_modification_laisse_une_entree_changelog(self):
        self.login(self.siege)

        response = self.client.patch(
            "/api/workflow-configuration/",
            {"require_review_step": True, "alert_thresholds": [75, 90, 100]},
            format="json",
            REMOTE_ADDR="203.0.113.7",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["require_review_step"])
        entry = ChangeLog.objects.get(
            model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION
        )
        self.assertEqual(entry.performed_by, self.siege.username)
        self.assertEqual(entry.ip_address, "203.0.113.7")
        self.assertEqual(
            set(entry.changed_fields), {"require_review_step", "alert_thresholds"}
        )
        self.assertEqual(
            entry.diff,
            {
                "require_review_step": [False, True],
                "alert_thresholds": [[80, 90, 100], [75, 90, 100]],
            },
        )
        # Du JSON, relisible par une machine, pas un ``repr`` Python.
        self.assertEqual(json.loads(entry.from_value)["require_review_step"], False)
        self.assertEqual(json.loads(entry.to_value)["alert_thresholds"], [75, 90, 100])

    def test_une_modification_sans_changement_ne_journalise_rien(self):
        self.login(self.siege)

        response = self.client.patch(
            "/api/workflow-configuration/", {"require_review_step": False}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ChangeLog.objects.filter(
                model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION
            ).exists()
        )

    def test_le_facteur_decimal_est_conserve_tel_quel(self):
        self.login(self.siege)

        response = self.client.patch(
            "/api/workflow-configuration/", {"unusual_expense_factor": "3.5"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            WorkflowConfiguration.charger().unusual_expense_factor, Decimal("3.5")
        )
        entry = ChangeLog.objects.get(model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION)
        self.assertEqual(entry.diff, {"unusual_expense_factor": ["5.00", "3.50"]})

    def test_les_charges_invalides_sont_refusees(self):
        self.login(self.siege)
        cas = {
            "seuil booleen": {"alert_thresholds": [True, 90]},
            "seuil negatif": {"alert_thresholds": [-1]},
            "seuils non liste": {"alert_thresholds": 80},
            "delai booleen": {"unjustified_alert_days": True},
            "delai negatif": {"unjustified_alert_days": -3},
            "facteur nul": {"unusual_expense_factor": "0"},
            "facteur negatif": {"unusual_expense_factor": "-2"},
            "facteur nan": {"unusual_expense_factor": "NaN"},
            "facteur infini": {"unusual_expense_factor": "Infinity"},
            "facteur texte": {"unusual_expense_factor": "beaucoup"},
            "politique inconnue": {"default_overrun_policy": "ignore"},
            "booleen laxiste": {"require_review_step": "yes"},
            "booleen entier": {"warn_without_proof_submission": 1},
            "parametre inconnu": {"require_reviw_step": True},
            "champ en lecture seule": {"updated_at": "2026-01-01T00:00:00Z"},
        }
        for nom, charge in cas.items():
            with self.subTest(nom):
                response = self.client.patch(
                    "/api/workflow-configuration/", charge, format="json"
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(next(iter(charge)), response.data)
        self.assertFalse(
            ChangeLog.objects.filter(
                model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION
            ).exists()
        )

    def test_la_configuration_generale_expose_la_politique(self):
        self.login(self.siege)

        response = self.client.get("/api/configuration/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["workflow"]["default_overrun_policy"], "block")
        self.assertEqual(response.data["alertes"]["seuils"], [80, 90, 100])

    def test_le_profil_annonce_l_etape_de_controle(self):
        """Le frontend ne doit pas proposer une étape que le serveur refusera."""
        self.login(self.siege)
        self.assertFalse(self.client.get("/api/me/").data["workflow"]["require_review_step"])

        self.client.patch(
            "/api/workflow-configuration/", {"require_review_step": True}, format="json"
        )

        self.assertTrue(self.client.get("/api/me/").data["workflow"]["require_review_step"])
