"""`manage.py mesurer_les_temps` (décision 130) : jamais hors base jetable."""

import json
import tempfile
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TransactionTestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from reporting.management.commands.mesurer_les_temps import ROUTES


class MesurerLesTempsTests(TransactionTestCase):
    # Chaque appel tourne dans un fil, avec sa connexion : il doit voir les
    # données du test, que seul un test non transactionnel a validées.

    def test_refuse_sans_base_jetable(self):
        with self.assertRaisesMessage(CommandError, "--base-jetable"):
            call_command("mesurer_les_temps", compte="personne", stdout=StringIO())

    def test_refuse_un_compte_inconnu(self):
        with self.assertRaisesMessage(CommandError, "Aucun compte actif"):
            call_command("mesurer_les_temps", base_jetable=True, compte="personne", stdout=StringIO())

    def test_chaque_ecran_repond_et_se_mesure(self):
        make_user("mesure.rh", Role.ADMIN, [])
        with tempfile.NamedTemporaryFile(suffix=".json") as sortie:
            call_command(
                "mesurer_les_temps", base_jetable=True, compte="mesure.rh",
                repetitions=2, simultanes=2, sortie=sortie.name, stdout=StringIO(),
            )
            mesures = json.load(open(sortie.name, encoding="utf-8"))["mesures"]

        self.assertEqual([m["ecran"] for m in mesures], [nom for nom, _chemin in ROUTES])
        for mesure in mesures:
            with self.subTest(ecran=mesure["ecran"]):
                self.assertEqual(mesure["statuts"], [200])
                self.assertLessEqual(mesure["p50_ms"], mesure["p95_ms"])
                self.assertLessEqual(mesure["p95_ms"], mesure["max_ms"])
