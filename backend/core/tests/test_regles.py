"""Traduction HTTP des refus métier (décision 41) : trois refus, trois codes."""

from django.test import SimpleTestCase
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.regles import HorsPerimetre, PermissionRefusee, RegleViolee, traduire_les_regles


class TraduireLesReglesTests(SimpleTestCase):
    def test_une_regle_violee_repond_400_sur_son_champ(self):
        with self.assertRaises(ValidationError) as refus:
            with traduire_les_regles():
                raise RegleViolee("note", "Un refus doit être motivé.")

        self.assertEqual(refus.exception.status_code, 400)
        self.assertEqual(refus.exception.detail, {"note": ["Un refus doit être motivé."]})
        self.assertIsInstance(refus.exception.__cause__, RegleViolee)

    def test_une_permission_refusee_repond_403_avec_le_message(self):
        with self.assertRaises(PermissionDenied) as refus:
            with traduire_les_regles():
                raise PermissionRefusee("Il faut deux personnes.")

        self.assertEqual(refus.exception.status_code, 403)
        self.assertEqual(str(refus.exception.detail), "Il faut deux personnes.")

    def test_hors_perimetre_repond_404_sans_rien_reveler(self):
        """Le 404 est celui d'un objet inexistant : rien de ce que le service
        savait de l'objet ne transparaît dans la réponse."""
        with self.assertRaises(NotFound) as refus:
            with traduire_les_regles():
                raise HorsPerimetre("le dossier TG-7 existe chez le voisin")

        self.assertEqual(refus.exception.status_code, 404)
        self.assertEqual(refus.exception.detail, NotFound().detail)
        self.assertNotIn("TG-7", str(refus.exception.detail))

    def test_les_autres_exceptions_passent(self):
        with self.assertRaises(KeyError):
            with traduire_les_regles():
                raise KeyError("x")

    def test_sans_refus_rien_ne_change(self):
        with traduire_les_regles():
            resultat = 1 + 1
        self.assertEqual(resultat, 2)
