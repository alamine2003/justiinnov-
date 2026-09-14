"""``lire_version`` : forme attendue de ``APP_VERSION``, ou repli sur ``dev``."""

from django.test import SimpleTestCase

from config.settings import lire_version


class LireVersionTests(SimpleTestCase):
    def test_chaine_vide_replie_sur_dev(self):
        self.assertEqual(lire_version(""), "dev")

    def test_uniquement_des_espaces_replie_sur_dev(self):
        """Un ``.env`` avec ``APP_VERSION=   `` transmet une chaîne non vide,
        mais sans aucun caractère significatif."""
        self.assertEqual(lire_version("   "), "dev")

    def test_sha_court_est_accepte(self):
        self.assertEqual(lire_version("sha-abc123def456"), "sha-abc123def456")

    def test_tag_semantique_avec_sha_est_accepte(self):
        self.assertEqual(lire_version("1.0.6+sha.abc123"), "1.0.6+sha.abc123")

    def test_balise_html_replie_sur_dev(self):
        """Aucune forme d'injection ne doit se retrouver affichée telle
        quelle dans le menu du compte."""
        self.assertEqual(lire_version("<img src=x>"), "dev")

    def test_valeur_trop_longue_replie_sur_dev(self):
        self.assertEqual(lire_version("a" * 10_000), "dev")

    def test_tag_v_est_accepte(self):
        self.assertEqual(lire_version("v1.0.6"), "v1.0.6")

    def test_quarante_et_un_caracteres_replie_sur_dev(self):
        """Borne exacte : quarante caractères passent, quarante et un non
        (durcissement pentest, cycle 3 : ``re.fullmatch`` remplace
        ``re.match`` ancré par ``$``, qui accepte aussi — hors ``.strip()``
        — la position juste avant un unique saut de ligne terminal ;
        ``fullmatch`` n'a pas ce cas particulier)."""
        self.assertEqual(lire_version("a" * 40), "a" * 40)
        self.assertEqual(lire_version("a" * 41), "dev")

    def test_saut_de_ligne_interne_replie_sur_dev(self):
        """Un saut de ligne au milieu de la valeur n'est pas une forme
        attendue : rien qui ressemble à une étiquette d'image ne l'exige."""
        self.assertEqual(lire_version("v1\n0"), "dev")
