"""Une variable posée vide, et l'entrée publique ne démarre plus.

Caddy lit ses variables d'environnement sous la forme ``{$NOM}``. Si la
variable arrive **vide**, le placeholder disparaît et la directive se
retrouve sans argument : ``email`` seul, ``trusted_proxies static`` seul.
Selon la directive, Caddy refuse alors de démarrer — et l'erreur ne nomme
que la directive, jamais la variable — ou démarre en ayant silencieusement
perdu le réglage. Les deux sont mauvais ; le second est pire.

**Le défaut ``{$NOM:valeur}`` ne protège pas de ce cas.** Mesuré sur Caddy
2.8.4 : il ne joue que si la variable est **absente**. Posée vide, elle reste
vide, et le défaut n'est jamais consulté. Or Compose la pose vide dès qu'on
écrit ``${NOM:-}``, et la pose vide aussi avec ``${NOM}`` nu que rien ne
renseigne.

Deux écritures tiennent :

* **côté Caddyfile**, entourer le placeholder de guillemets — l'argument
  existe alors, vide, et la directive reste analysable ;
* **côté Compose**, garantir une valeur non vide, avec ``${NOM:?…}`` (refusé
  vide comme absent) ou un défaut non vide ``${NOM:-0}``.

Ce test vérifie qu'au moins l'une des deux est en place pour chaque variable
de chaque Caddyfile. Il est écrit après coup : ``email {$ACME_EMAIL}``
n'était pas entre guillemets et ``docker-compose.derriere-balanceur.yml``
posait ``${ACME_EMAIL:-}``, c'est-à-dire vide. Rien ne l'avait vu, parce que
l'intégration continue renseigne une adresse factice alors qu'elle ne termine
pas TLS : le seul chemin qui aurait révélé le défaut était celui que personne
ne joue.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

RACINE = Path(__file__).resolve().parents[3]
CADDYFILES = (
    RACINE / "deploy" / "Caddyfile",
    RACINE / "deploy" / "balanceur" / "Caddyfile",
)
COMPOSES = sorted(RACINE.glob("docker-compose*.yml")) + sorted(
    (RACINE / "deploy").glob("docker-compose*.yml")
)

# {$NOM} ou {$NOM:défaut} — le défaut est traversé sans être retenu, puisqu'il
# ne joue pas sur une variable posée vide.
PLACEHOLDER = re.compile(r"\{\$(?P<nom>[A-Z_][A-Z0-9_]*)(?::[^}]*)?\}")
# NOM: valeur (forme mapping) et - NOM=valeur (forme liste).
AFFECTATION = re.compile(
    r"^\s*(?:-\s*)?(?P<nom>[A-Z_][A-Z0-9_]*)\s*[:=]\s*(?P<valeur>.*?)\s*$"
)
INTERPOLATION = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)(?::([-?])(.*))?\}$")


def _placeholders(caddyfile):
    """Chaque placeholder d'un Caddyfile, hors commentaires : un ``{$NOM}``
    cité dans une explication n'est pas un réglage."""
    for numero, ligne in enumerate(caddyfile.read_text().splitlines(), 1):
        if ligne.lstrip().startswith("#"):
            continue
        for trouve in PLACEHOLDER.finditer(ligne):
            yield numero, ligne, trouve


def _entre_guillemets(ligne, position):
    """Le placeholder est-il dans une chaîne entre guillemets doubles ? On
    compte ceux qui le précèdent : un nombre impair veut dire dedans."""
    return ligne[:position].count('"') % 2 == 1


def _peut_etre_vide(valeur):
    """Cette valeur d'un fichier Compose peut-elle arriver vide au conteneur ?"""
    valeur = valeur.strip()
    if len(valeur) > 1 and valeur[0] in ('"', "'") and valeur[-1] == valeur[0]:
        valeur = valeur[1:-1]
    interpolation = INTERPOLATION.fullmatch(valeur)
    if interpolation is None:
        # Valeur littérale, ou composition de plusieurs morceaux : seule la
        # chaîne vide pose problème.
        return valeur == ""
    _, operateur, defaut = interpolation.groups()
    if operateur == "?":
        return False  # Compose refuse la variable vide comme absente.
    if operateur == "-":
        return defaut == ""  # ${NOM:-} la pose, vide.
    return True  # ${NOM} nu : rien ne la renseigne, elle arrive vide.


def _affectations():
    """Toutes les valeurs que les fichiers Compose donnent à une variable."""
    valeurs = {}
    for compose in COMPOSES:
        for numero, ligne in enumerate(compose.read_text().splitlines(), 1):
            if ligne.lstrip().startswith("#"):
                continue
            affectation = AFFECTATION.match(ligne)
            if affectation is None or not affectation.group("valeur"):
                continue
            valeurs.setdefault(affectation.group("nom"), []).append(
                (f"{compose.relative_to(RACINE)}:{numero}", affectation.group("valeur"))
            )
    return valeurs


class VariablesDesCaddyfileTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.affectations = _affectations()

    def test_aucun_placeholder_nu_ne_peut_recevoir_une_valeur_vide(self):
        """La règle, et la seule qui compte : un placeholder sans guillemets
        n'est acceptable que si Compose garantit une valeur non vide. Le défaut
        ``{$NOM:…}`` ne compte pas — il ne joue pas sur une variable posée
        vide."""
        for caddyfile in CADDYFILES:
            for numero, ligne, trouve in _placeholders(caddyfile):
                nom = trouve.group("nom")
                if _entre_guillemets(ligne, trouve.start()):
                    continue
                for origine, valeur in self.affectations.get(nom, []):
                    with self.subTest(variable=nom, pose_par=origine):
                        self.assertFalse(
                            _peut_etre_vide(valeur),
                            f"{caddyfile.relative_to(RACINE)}:{numero} emploie "
                            f"{{${nom}}} sans guillemets, et {origine} lui donne "
                            f"« {valeur} », qui peut arriver vide. Caddy verrait la "
                            f"directive sans argument : au mieux il perd le réglage "
                            f"en silence, au pire il refuse de démarrer. Entourez le "
                            f"placeholder de guillemets, ou exigez la valeur avec "
                            f"${{{nom}:?…}}.",
                        )

    def test_toute_variable_d_un_caddyfile_est_bien_fournie(self):
        """Un placeholder que personne ne renseigne est un réglage mort : la
        directive part avec son défaut, ou sans argument, sans que rien ne le
        dise."""
        connues = set(self.affectations) | {
            ligne.split("=", 1)[0].strip()
            for ligne in (RACINE / "deploy" / ".env.example").read_text().splitlines()
            if "=" in ligne and not ligne.lstrip().startswith("#")
        }
        for caddyfile in CADDYFILES:
            for _, _, trouve in _placeholders(caddyfile):
                with self.subTest(fichier=caddyfile.name, variable=trouve.group("nom")):
                    self.assertIn(trouve.group("nom"), connues)
