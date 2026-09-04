"""Le parseur maison de ``DATABASE_URL`` (``config.settings``)."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings import parse_database_url


class ParseDatabaseUrlTests(SimpleTestCase):
    def test_url_complete(self):
        config = parse_database_url(
            "postgresql://justi_app:secret@db.example.org:5433/justi_innov"
            "?sslmode=require&channel_binding=require"
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "justi_innov")
        self.assertEqual(config["USER"], "justi_app")
        self.assertEqual(config["PASSWORD"], "secret")
        self.assertEqual(config["HOST"], "db.example.org")
        self.assertEqual(config["PORT"], "5433")
        self.assertEqual(
            config["OPTIONS"], {"sslmode": "require", "channel_binding": "require"}
        )

    def test_mot_de_passe_encode(self):
        # `p@ss/w%rd` encodé : `@` et `/` ne doivent pas couper l'URL, et le
        # mot de passe transmis à psycopg est la valeur décodée.
        config = parse_database_url("postgres://u:p%40ss%2Fw%25rd@h/base")
        self.assertEqual(config["USER"], "u")
        self.assertEqual(config["PASSWORD"], "p@ss/w%rd")
        self.assertEqual(config["HOST"], "h")

    def test_schema_postgres_court(self):
        config = parse_database_url("postgres://u:p@h/base")
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "base")

    def test_sans_port_ni_query(self):
        config = parse_database_url("postgresql://u:p@h/base")
        self.assertEqual(config["PORT"], "")
        self.assertNotIn("OPTIONS", config)

    def test_hote_ipv6(self):
        config = parse_database_url("postgresql://u:p@[::1]:5432/base")
        self.assertEqual(config["HOST"], "::1")
        self.assertEqual(config["PORT"], "5432")

    def test_schema_refuse(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_database_url("mysql://u:p@h/base")
        with self.assertRaises(ImproperlyConfigured):
            parse_database_url("db.example.org/base")

    def test_base_absente_refusee(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_database_url("postgresql://u:p@h/")
        with self.assertRaises(ImproperlyConfigured):
            parse_database_url("postgresql://u:p@h")

    def test_ne_touche_pas_a_l_environnement(self):
        # Fonction pure : deux appels identiques, deux résultats égaux et
        # indépendants (pas d'état partagé modifiable).
        url = "postgresql://u:p@h/base?sslmode=require"
        premier = parse_database_url(url)
        premier["OPTIONS"]["sslmode"] = "disable"
        self.assertEqual(parse_database_url(url)["OPTIONS"], {"sslmode": "require"})
