"""L'aiguillage devant les deux machines, et ce qui le rend sûr.

Ce n'est pas une répartition de charge, et le nom prête à confusion : les
deux machines ne sont pas interchangeables. La première porte la base en
écriture, la seconde une réplique **en lecture seule** dont l'application
est à l'arrêt (décision 75). Partager le trafic reviendrait à refuser la
moitié des enregistrements.

C'est un aiguillage : tout va à la machine qui se déclare primaire. Ce
qu'il apporte est précis — sans lui, une bascule oblige à changer le DNS, et
c'est le TTL du cache qui décide du retour du service, bien après que la
base a basculé.

**Ce qui le rend sûr tient à `/api/health/`**, qui ne répond 200 que si la
base accepte les écritures. Une réplique répond parfaitement au `SELECT 1` ;
sans ce contrôle, l'aiguillage y enverrait du monde. Mesuré : pendant les
dix-sept secondes où la primaire était perdue et la réplique pas encore
promue, aucune requête n'est partie vers la réplique.

Ce contrôle **ne protège pas** du retour d'une ancienne primaire : redémarrée
telle quelle, elle accepte les écritures, répond 200, et `lb_policy first` la
remet en tête — mesuré, 5,1 s après son retour. Ce qui protège là est une
consigne d'exploitation, pas ce fichier (`docs/audit-resilience.md` §9).

Trois réglages doivent être vrais **ensemble** ; deux d'entre eux cassent
quelque chose en silence s'ils manquent, et c'est là que ce test sert.
"""

from pathlib import Path

import yaml
from django.test import SimpleTestCase

RACINE = Path(__file__).resolve().parents[3]
BALANCEUR = RACINE / "deploy" / "docker-compose.balanceur.yml"
DERRIERE = RACINE / "deploy" / "docker-compose.derriere-balanceur.yml"
CADDYFILE_BALANCEUR = RACINE / "deploy" / "balanceur" / "Caddyfile"
CADDYFILE_MACHINE = RACINE / "deploy" / "Caddyfile"
EXEMPLE = RACINE / "deploy" / ".env.example"


class _LecteurCompose(yaml.SafeLoader):
    """Compose a ses propres étiquettes — ``!reset``, ``!override`` — que
    PyYAML ne connaît pas et sur lesquelles il s'arrête. On les traverse."""


_LecteurCompose.add_multi_constructor(
    "",
    lambda lecteur, suffixe, noeud: (
        lecteur.construct_sequence(noeud, deep=True)
        if isinstance(noeud, yaml.SequenceNode)
        else lecteur.construct_mapping(noeud, deep=True)
        if isinstance(noeud, yaml.MappingNode)
        else noeud.value
    ),
)


def _charger(chemin):
    return yaml.load(chemin.read_text(), _LecteurCompose)["services"]


class AiguillageTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.balanceur = _charger(BALANCEUR)
        cls.derriere = _charger(DERRIERE)
        cls.caddy_balanceur = CADDYFILE_BALANCEUR.read_text()
        cls.caddy_machine = CADDYFILE_MACHINE.read_text()

    # --- Ce qui rend l'aiguillage sûr -------------------------------------

    def test_il_demande_si_la_machine_accepte_les_ecritures(self):
        """Le contrôle n'est pas « le serveur répond-il » mais « est-ce la
        primaire ». Une réplique répond parfaitement au premier."""
        self.assertIn("health_uri /api/health/", self.caddy_balanceur)
        self.assertIn("health_status 200", self.caddy_balanceur)

    def test_il_ne_partage_jamais_le_trafic(self):
        """Deux machines qui écriraient chacune dans leur base donneraient
        deux histoires qu'on ne réunirait pas."""
        self.assertIn("lb_policy first", self.caddy_balanceur)

    def test_une_machine_qui_vient_d_echouer_n_est_pas_rappelee_aussitot(self):
        """Sans cela, une machine à demi vivante recevrait une requête sur
        deux."""
        self.assertIn("fail_duration", self.caddy_balanceur)

    def test_il_laisse_le_temps_aux_longues_requetes(self):
        """Un export d'année complète ou une pièce de 20 Mo dépassent
        largement les délais par défaut ; couper ici annulerait une requête
        que la machine allait servir."""
        self.assertIn("response_header_timeout 120s", self.caddy_balanceur)

    # --- Ce qui casse en silence si on l'oublie ---------------------------

    def test_un_mandataire_de_plus_est_declare(self):
        """``client_ip`` prend le n-ième élément de ``X-Forwarded-For`` en
        partant de la fin. Laissé à 2 avec trois mandataires, il lirait
        l'adresse de l'aiguillage pour **tout le monde** : la limite
        anti-bourrage (décision 68) deviendrait un seul compteur commun, et
        le journal d'audit noterait la même adresse pour chaque action. Une
        protection qui compte faux ne protège pas."""
        for service in ("backend", "scheduler"):
            with self.subTest(service=service):
                # Compose rend ses valeurs d'environnement en chaînes.
                self.assertEqual(
                    str(self.derriere[service]["environment"]["DJANGO_NUM_PROXIES"]),
                    "3",
                )

    def test_caddy_conserve_le_protocole_annonce_en_amont(self):
        """Sans mandataire de confiance, Caddy réécrit ``X-Forwarded-Proto``
        avec le protocole qu'il a reçu — « http » derrière l'aiguillage.
        Django se croit en clair, redirige vers HTTPS, donc vers
        l'aiguillage, qui revient ici : une boucle, c'est-à-dire une panne."""
        self.assertIn("trusted_proxies static", self.caddy_machine)
        self.assertIn(
            "MANDATAIRES_DE_CONFIANCE",
            self.derriere["caddy"]["environment"],
        )

    def test_la_machine_ne_publie_plus_sur_l_internet(self):
        """Deux portes d'entrée là où l'on en veut une, et la seconde sans
        TLS."""
        ports = self.derriere["caddy"]["ports"]

        self.assertEqual(len(ports), 1, "la machine publie encore plusieurs ports")
        self.assertIn("ADRESSE_PRIVEE", ports[0])
        self.assertNotIn("443", " ".join(ports))

    def test_la_machine_ne_termine_plus_tls(self):
        """C'est l'aiguillage qui porte le nom de domaine et le certificat.
        Le mode sans TLS du Caddyfile est celui que l'intégration continue
        emploie déjà : pas une ligne à changer."""
        self.assertEqual(
            self.derriere["caddy"]["environment"]["APP_DOMAIN"], "http://:80"
        )

    # --- Où il tourne ------------------------------------------------------

    def test_l_aiguillage_ne_porte_ni_base_ni_application(self):
        """Il doit pouvoir se perdre et se refaire en une minute. S'il
        portait autre chose, il deviendrait une machine à sauvegarder."""
        self.assertEqual(list(self.balanceur), ["balanceur"])

    def test_ses_certificats_survivent_a_un_redemarrage(self):
        """Sans volume, Caddy redemanderait un certificat à chaque
        redémarrage, et Let's Encrypt finirait par refuser."""
        volumes = self.balanceur["balanceur"]["volumes"]

        self.assertTrue(any("/data" in v for v in volumes))

    def test_le_fichier_d_exemple_dit_ou_il_ne_doit_pas_tourner(self):
        """Posé sur la primaire, il meurt avec elle le jour où il servirait."""
        exemple = EXEMPLE.read_text()

        self.assertIn("MACHINE_PRIMAIRE", exemple)
        self.assertIn("ADRESSE_PRIVEE", exemple)
        self.assertIn("DJANGO_NUM_PROXIES", exemple)
