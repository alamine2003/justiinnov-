"""Jeu de recette : dix-sept pays, trente-sept comptes, chaque état du circuit.

La recette manuelle (docs/recette.md) promet des cas précis — un brouillon de
collègue qu'on ne soumet pas, un Mali qui bloque, des décisions en attente.
Ce test garde ces promesses, et les deux garde-fous qui empêchent de lancer
la commande sur une base réelle, où rien ne s'efface.
"""

from collections import Counter
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.permissions import get_access
from budget.aggregates import budget_figures
from budget.models import Budget, BudgetReallocation
from core.journal import Trace
from core.models import Country
from core.regles import RegleViolee
from expenses import transitions
from expenses.models import Dossier, Rectification
from expenses.tests.base import in_memory_storage
from expenses.workflow import dossier_allowed_actions
from reporting.management.commands import seed_recette


@in_memory_storage
@override_settings(DEBUG=True)
class SeedRecetteTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp = TemporaryDirectory()
        cls.fichier = Path(cls.temp.name) / "recette.local.md"
        cls.patch = mock.patch.object(seed_recette, "FICHIER", cls.fichier)
        cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.temp.cleanup()
        super().tearDownClass()

    def _lancer(self):
        sortie = StringIO()
        call_command("seed_recette", "--base-jetable", stdout=sortie)
        return sortie.getvalue()

    def test_sans_drapeau_rien_n_est_ecrit(self):
        with self.assertRaisesMessage(CommandError, "--base-jetable"):
            call_command("seed_recette")
        self.assertFalse(Dossier.objects.exists())

    @override_settings(DEBUG=False)
    def test_hors_du_mode_debug_rien_n_est_ecrit(self):
        """La production et la préproduction tournent sans debug : le jeu
        y resterait pour toujours."""
        with self.assertRaisesMessage(CommandError, "mode debug"):
            call_command("seed_recette", "--base-jetable")
        self.assertFalse(Dossier.objects.exists())

    def test_le_jeu_couvre_les_pays_les_roles_et_les_etats(self):
        sortie = self._lancer()

        self.assertEqual(Country.objects.count(), 17)
        # Deux comptes au siège, deux par pays (décision 89).
        self.assertEqual(User.objects.filter(username__startswith="recette.").count(), 37)
        self.assertEqual(
            set(User.objects.filter(username__startswith="recette.")
                .values_list("profile__role", flat=True)),
            {"super_admin", "admin", "manager"},
        )
        etats = Counter(Dossier.objects.values_list("status", flat=True))
        self.assertEqual(etats, {"draft": 34, "submitted": 34, "in_review": 34,
                                 "unjustified": 17, "closed": 17})
        self.assertEqual(Rectification.objects.filter(status="pending").count(), 17)
        self.assertEqual(
            Counter(BudgetReallocation.objects.values_list("status", flat=True)),
            {"pending": 3, "approved": 1, "rejected": 1},
        )
        # Le mot de passe est dit une fois, et il ouvre les comptes.
        mot_de_passe = sortie.split("recette.* : ")[1].split()[0]
        self.assertTrue(User.objects.get(username="recette.rh").check_password(mot_de_passe))
        self.assertIn(mot_de_passe, self.fichier.read_text())

    def test_les_niveaux_d_alerte_annonces(self):
        self._lancer()
        niveaux = {
            (b.country.code, b.team_id is None): budget_figures(b)["execution_level"]
            for b in Budget.objects.select_related("country")
        }
        for code in ("SN", "CM", "MG"):
            self.assertEqual(niveaux[(code, True)], "warning", code)
        for code in ("GN", "CD"):
            self.assertEqual(niveaux[(code, True)], "exceeded", code)
        self.assertEqual(niveaux[("TG", True)], "ok")

    def test_le_mali_bloque_et_le_brouillon_du_collegue_ne_se_soumet_pas(self):
        self._lancer()
        manager = User.objects.get(username="recette.ml.manager")
        with self.assertRaises(RegleViolee):
            transitions.executer(Dossier.objects.get(number="R-ML-01"), "submit",
                                 get_access(manager), Trace.depuis_compte(manager))

        collegue = Dossier.objects.get(number="R-TG-02")
        self.assertNotIn("submit", dossier_allowed_actions(
            collegue, role="manager", username="recette.tg.manager"))
        self.assertIn("submit", dossier_allowed_actions(
            collegue, role="manager", username="recette.tg.equipe"))

    def test_deux_executions_meme_etat(self):
        self._lancer()
        avant = Dossier.objects.count()

        sortie = self._lancer()

        self.assertIn("rien à faire", sortie)
        self.assertEqual(Dossier.objects.count(), avant)
