"""Le contrôle à passer avant de demander un certificat à Let's Encrypt.

L'émission ne se répète pas à volonté : Let's Encrypt compte cinq validations
échouées par heure et par nom, et cinq certificats identiques par semaine. Un
DNS qui pointe ailleurs, un CAA oublié, un port 80 fermé — et les essais sont
brûlés avant qu'on ait compris.

``deploy/verifier_tls.sh`` pose les questions dans l'ordre, sur la machine où
la réponse se trouve. Ce test tient ce qu'il doit couvrir, parce que chacun
de ces points correspond à une panne réelle qui ne se voit pas depuis le
serveur :

* un CAA qui n'autorise pas ``letsencrypt.org`` fait échouer l'émission sans
  qu'aucun journal local ne l'explique ;
* une sortie bloquée vers l'ACME donne le même silence ;
* et surtout, **Caddy se replie sur son autorité interne quand l'ACME
  échoue** : le site répond en TLS, le serveur paraît sain, et tous les
  navigateurs refusent. C'est la panne qu'on ne voit pas de l'intérieur.

Le script dit aussi ce qu'il ne peut pas vérifier — qu'Internet atteint la
machine sur le port 80, puisque c'est Let's Encrypt qui ouvre la connexion.
Un contrôle qui tairait sa propre limite serait pire qu'aucun contrôle.
"""

import os
from pathlib import Path

from django.test import SimpleTestCase

RACINE = Path(__file__).resolve().parents[3]
SCRIPT = RACINE / "deploy" / "verifier_tls.sh"
README = RACINE / "deploy" / "README.md"


class ControlePrealableTLSTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = SCRIPT.read_text()

    def test_le_script_existe_et_s_execute(self):
        self.assertTrue(SCRIPT.exists(), "deploy/verifier_tls.sh a disparu")
        self.assertTrue(
            os.access(SCRIPT, os.X_OK), "deploy/verifier_tls.sh n'est pas exécutable"
        )

    def test_il_verifie_le_caa(self):
        """Un CAA qui n'autorise pas Let's Encrypt fait échouer l'émission, et
        rien sur le serveur ne le dira."""
        self.assertIn("CAA", self.source)
        self.assertIn("letsencrypt.org", self.source)

    def test_il_verifie_la_sortie_vers_les_deux_environnements(self):
        """Celui d'essai ne consomme aucun quota : c'est là qu'on répète."""
        self.assertIn("acme-staging-v02.api.letsencrypt.org", self.source)
        self.assertIn("acme-v02.api.letsencrypt.org", self.source)

    def test_il_signale_le_repli_sur_l_autorite_interne(self):
        """La panne invisible : le site répond en TLS et tous les navigateurs
        refusent, parce que Caddy a signé lui-même après un échec ACME."""
        self.assertIn("autorité interne", self.source)

    def test_il_dit_ce_qu_il_ne_peut_pas_verifier(self):
        """Personne, depuis la machine, ne peut prouver qu'Internet l'atteint."""
        self.assertIn("Ce que le script n'a pas pu vérifier", self.source)

    def test_il_rappelle_les_quotas_et_la_repetition(self):
        """Cinq échecs par heure, cinq certificats identiques par semaine : on
        répète sur l'environnement d'essai, jamais en production."""
        self.assertIn("quotas", self.source)
        self.assertIn("RÉPÉTITION", self.source)

    def test_il_ne_s_applique_pas_a_une_machine_derriere_l_aiguillage(self):
        """``APP_DOMAIN`` en forme ``http://:80`` veut dire que cette machine
        ne termine pas TLS : c'est l'aiguillage qui porte le certificat."""
        self.assertIn("ne termine pas TLS", self.source)

    def test_le_readme_y_renvoie(self):
        """Un script que la documentation ignore ne sera pas lancé."""
        self.assertIn("verifier_tls.sh", README.read_text())
