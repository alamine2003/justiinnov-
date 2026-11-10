"""Enregistrement de la matrice des droits, appelé sans passer par HTTP.

``permissions.enregistrer_la_matrice`` tient ce que la vue
``PermissionMatrixView.patch`` faisait elle-même (décision 124) : la
configuration ne garde que ce qui s'écarte du défaut, et l'appelant reçoit
les deux photographies qu'il trace.
"""

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase

from accounts.models import Role
from accounts.permissions import CAPACITES, enregistrer_la_matrice, roles_pour
from core.models import WorkflowConfiguration

DEFAUT_DE_L_EXPORT = sorted({Role.ADMIN, Role.SUPER_ADMIN})
EXPORT_OUVERT = sorted({Role.ADMIN, Role.SUPER_ADMIN, Role.MANAGER})


class EnregistrerLaMatriceTests(TestCase):
    def setUp(self):
        cache.clear()

    def _enregistrer(self, choix):
        with transaction.atomic():
            configuration = WorkflowConfiguration.verrouiller()
            return configuration, enregistrer_la_matrice(configuration, choix)

    def test_un_ecart_au_defaut_est_garde_et_photographie(self):
        configuration, (avant, apres) = self._enregistrer({"data.export": EXPORT_OUVERT})

        self.assertEqual(list(avant), [c.key for c in CAPACITES])
        self.assertEqual(list(apres), [c.key for c in CAPACITES])
        self.assertEqual(avant["data.export"], DEFAUT_DE_L_EXPORT)
        self.assertEqual(apres["data.export"], EXPORT_OUVERT)
        self.assertEqual(
            [cle for cle in apres if avant[cle] != apres[cle]], ["data.export"]
        )
        self.assertEqual(
            WorkflowConfiguration.objects.get(pk=1).capability_roles,
            {"data.export": EXPORT_OUVERT},
        )
        self.assertIn(Role.MANAGER, roles_pour("data.export"))

    def test_revenir_au_defaut_elague_le_choix(self):
        self._enregistrer({"data.export": EXPORT_OUVERT})

        _configuration, (avant, apres) = self._enregistrer(
            {"data.export": list(reversed(DEFAUT_DE_L_EXPORT))}
        )

        self.assertEqual(avant["data.export"], EXPORT_OUVERT)
        self.assertEqual(apres["data.export"], DEFAUT_DE_L_EXPORT)
        self.assertEqual(WorkflowConfiguration.objects.get(pk=1).capability_roles, {})
        self.assertNotIn(Role.MANAGER, roles_pour("data.export"))

    def test_les_autres_choix_sont_conserves(self):
        self._enregistrer({"data.export": EXPORT_OUVERT})
        self._enregistrer({"history.read": sorted(roles_pour("history.read") | {Role.MANAGER})})

        self.assertEqual(
            set(WorkflowConfiguration.objects.get(pk=1).capability_roles),
            {"data.export", "history.read"},
        )
