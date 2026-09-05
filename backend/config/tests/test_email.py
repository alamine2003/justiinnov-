"""Hors debug, un transport d'e-mail doit être choisi explicitement."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings import choisir_email_backend

SMTP = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"


class ChoixDuTransportTests(SimpleTestCase):
    def test_un_serveur_nomme_est_utilise(self):
        self.assertEqual(
            choisir_email_backend("smtp.example.org", debug=False, console=False), SMTP
        )

    def test_en_developpement_la_console_suffit(self):
        self.assertEqual(choisir_email_backend("", debug=True, console=False), CONSOLE)

    def test_hors_debug_sans_serveur_le_demarrage_est_refuse(self):
        """Un EMAIL_HOST oublié ferait disparaître les alertes dans les
        journaux sans que personne ne s'en aperçoive."""
        with self.assertRaisesMessage(ImproperlyConfigured, "EMAIL_BACKEND_CONSOLE"):
            choisir_email_backend("", debug=False, console=False)

    def test_la_console_se_demande_explicitement(self):
        self.assertEqual(choisir_email_backend("", debug=False, console=True), CONSOLE)
