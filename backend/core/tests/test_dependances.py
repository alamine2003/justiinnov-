"""L'ordre des applications est strict, et c'est un test qui le garde.

Décision 40 : ``core < accounts < notifications < budget < expenses <
reporting``. Un module n'importe, en tête de module, que des applications
de rang inférieur ou égal au sien. ``core`` n'importe donc aucune autre app ;
``notifications`` n'en importe que deux — c'est un service que ``budget``
et ``expenses`` appellent, pas l'inverse. Les tests et les migrations sont
hors champ : un test traverse tout, une migration ne dépend que de son état.

Les imports paresseux (dans une fonction) sont comptés aussi (décision
125) : ils cachaient une dépendance à rebours — ``accounts`` importait
``expenses`` dans quatre fonctions de la vue des projets. Un import
paresseux vers un rang supérieur n'est toléré que s'il est nommé dans
:data:`PARESSEUX_TOLERES`, avec sa raison.
"""

import ast
from pathlib import Path

from django.apps import apps
from django.test import SimpleTestCase

ORDRE = ["core", "accounts", "notifications", "budget", "expenses", "reporting"]
RANG = {app: rang for rang, app in enumerate(ORDRE)}
RACINE = Path(__file__).resolve().parents[2]


def _modules(app):
    for chemin in sorted((RACINE / app).rglob("*.py")):
        parties = chemin.relative_to(RACINE).parts
        if "tests" in parties or "migrations" in parties:
            continue
        yield chemin


def _imports_de_premier_niveau(chemin):
    """Les modules importés en tête de fichier, avec leur ligne."""
    arbre = ast.parse(chemin.read_text(), filename=str(chemin))
    for noeud in arbre.body:
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                yield alias.name, noeud.lineno
        elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
            yield noeud.module, noeud.lineno


#: (fichier, module importé) → pourquoi l'import reste paresseux. Une
#: entrée de plus se décide, elle ne s'ajoute pas.
PARESSEUX_TOLERES = {
    ("accounts/views.py", "budget.models"): (
        "la configuration affiche la devise de consolidation, définie par "
        "``budget`` ; une constante lue à la demande, aucune logique"
    ),
}


def _imports_paresseux(chemin):
    """Les modules importés dans une fonction, avec leur ligne."""
    arbre = ast.parse(chemin.read_text(), filename=str(chemin))
    for fonction in ast.walk(arbre):
        if not isinstance(fonction, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for noeud in ast.walk(fonction):
            if isinstance(noeud, ast.Import):
                for alias in noeud.names:
                    yield alias.name, noeud.lineno
            elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
                yield noeud.module, noeud.lineno


class OrdreDesApplicationsTests(SimpleTestCase):
    def test_les_six_applications_sont_installees(self):
        installees = {config.label for config in apps.get_app_configs()}
        self.assertTrue(set(ORDRE) <= installees, set(ORDRE) - installees)

    def test_aucun_module_n_importe_une_application_de_rang_superieur(self):
        fautes = []
        for app in ORDRE:
            for chemin in _modules(app):
                for module, ligne in _imports_de_premier_niveau(chemin):
                    racine = module.split(".")[0]
                    if racine in RANG and RANG[racine] > RANG[app]:
                        fautes.append(
                            f"{chemin.relative_to(RACINE)}:{ligne}: {app} importe {module}"
                        )
        self.assertEqual(
            fautes, [],
            "Ordre des applications violé (" + " < ".join(ORDRE) + ") :\n" + "\n".join(fautes),
        )

    def test_core_n_importe_aucune_autre_application(self):
        """Le cas qui a motivé la décision : ``core`` est le socle."""
        for chemin in _modules("core"):
            for module, ligne in _imports_de_premier_niveau(chemin):
                self.assertNotIn(
                    module.split(".")[0], set(ORDRE) - {"core"},
                    f"{chemin.relative_to(RACINE)}:{ligne} importe {module}",
                )

    def test_aucun_import_paresseux_vers_un_rang_superieur_hors_tolerance(self):
        fautes, vus = [], set()
        for app in ORDRE:
            for chemin in _modules(app):
                relatif = chemin.relative_to(RACINE).as_posix()
                for module, ligne in _imports_paresseux(chemin):
                    racine = module.split(".")[0]
                    if racine in RANG and RANG[racine] > RANG[app]:
                        if (relatif, module) in PARESSEUX_TOLERES:
                            vus.add((relatif, module))
                            continue
                        fautes.append(f"{relatif}:{ligne}: {app} importe {module} dans une fonction")
        self.assertEqual(
            fautes, [],
            "Import paresseux vers une application de rang supérieur : déplacez le "
            "code au bon rang, ou nommez l'exception dans PARESSEUX_TOLERES.\n"
            + "\n".join(fautes),
        )
        self.assertEqual(
            set(PARESSEUX_TOLERES) - vus, set(),
            "Une tolérance ne sert plus : retirez-la de PARESSEUX_TOLERES.",
        )
