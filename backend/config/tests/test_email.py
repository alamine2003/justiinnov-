"""Hors debug, un transport d'e-mail doit être choisi explicitement."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings import choisir_email_backend

SMTP = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"
COUPE = "core.courrier.CourrierCoupe"


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

    def test_un_serveur_nomme_et_la_console_se_contredisent(self):
        """Un hôte de remplissage posé en attendant le vrai serveur, avec
        EMAIL_BACKEND_CONSOLE=1 pour « au moins garder les messages » :
        l'hôte l'emportait, et rien n'arrivait nulle part."""
        with self.assertRaisesMessage(ImproperlyConfigured, "se contredisent"):
            choisir_email_backend("smtp.example.org", debug=False, console=True)

    def test_la_contradiction_vaut_aussi_en_developpement(self):
        """Le mode debug n'excuse pas la contradiction : elle se corrige là où
        elle a été écrite, avant d'être recopiée dans un `.env` de serveur."""
        with self.assertRaisesMessage(ImproperlyConfigured, "se contredisent"):
            choisir_email_backend("smtp.example.org", debug=True, console=True)


class CourrierCoupeTests(SimpleTestCase):
    """Décision 88 : coupé, rien ne part, quel que soit le reste du réglage."""

    def test_coupe_un_serveur_nomme_ne_sert_plus(self):
        self.assertEqual(
            choisir_email_backend("smtp.example.org", debug=False, console=False, actif=False),
            COUPE,
        )

    def test_coupe_le_serveur_n_est_plus_exige_hors_debug(self):
        """Sans envoi, exiger un SMTP n'aurait pas de sens : le serveur démarre."""
        self.assertEqual(
            choisir_email_backend("", debug=False, console=False, actif=False), COUPE
        )

    def test_le_transport_coupe_n_envoie_rien_et_le_dit(self):
        from django.core.mail import EmailMessage, get_connection

        connexion = get_connection(COUPE)
        with self.assertLogs("core.courrier", "WARNING") as journaux:
            envoyes = EmailMessage(
                "Sujet", "Corps", "a@innovpharma.net", ["b@innovpharma.net"],
                connection=connexion,
            ).send()
        self.assertEqual(envoyes, 0)
        self.assertIn("non envoyé", journaux.output[0])

    def test_le_serveur_est_coupe_par_defaut(self):
        """La suite tourne sur le défaut du serveur, sans DJANGO_EMAIL_ENABLED :
        le courrier y est coupé. Un défaut rebasculé à « ouvert » casserait ici."""
        from django.conf import settings

        self.assertFalse(settings.EMAIL_ENABLED)
