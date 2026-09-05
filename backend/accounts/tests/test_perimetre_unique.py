"""``accounts.perimetre.filtrer`` est la seule écriture de la règle du périmètre.

Décision 39 : un ``team__in`` ou ``country__in`` récrit à la main dans une
vue applique *sa* version de la règle — et le jour où elle change (équipe
absente, rôle du siège), il ne suit pas. Le test parcourt les sources, sur
le modèle de ``core/tests/test_journal_unique.py``, et refuse ces filtres
hors de la primitive. Les cas légitimes qui subsistent sont nommés avec
leur raison ; un cas nommé qui disparaît fait échouer le test aussi, pour
que la liste ne vieillisse pas.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

RACINE = Path(__file__).resolve().parents[2]
PRIMITIVE = RACINE / "accounts" / "perimetre.py"
INTERDIT = re.compile(r"\b(team|team_id|country|country_id)__in\b")

#: Filtres ``__in`` qui ne sont pas la règle du périmètre d'un compte.
TOLERES = {
    # Un rôle du siège restreint garde la vue sur l'historique sans pays
    # (taux de change) : ``pays OU sans pays``, que ``filtrer`` ne sait pas
    # exprimer et qui n'a de sens que pour cette ressource.
    "accounts/referentiel.py": "historique du siège restreint : pays ou sans pays",
    # Les pays viennent du fichier d'amorçage, pas d'un périmètre de compte.
    "accounts/management/commands/seed_users.py": "équipes nommées dans les pays du fichier",
    # Sous-requête sur des dossiers déjà cloisonnés par ``querysets_pour``.
    "reporting/management/commands/send_periodic_report.py": "lignes des dossiers du rapport",
}


def _sources():
    for chemin in sorted(RACINE.rglob("*.py")):
        parties = chemin.relative_to(RACINE).parts
        if "tests" in parties or "migrations" in parties or ".venv" in parties:
            continue
        yield chemin


class PerimetreUniqueTests(SimpleTestCase):
    def test_aucun_filtre_de_perimetre_hors_de_la_primitive(self):
        fautifs = []
        toleres_vus = set()
        for chemin in _sources():
            if chemin == PRIMITIVE:
                continue
            relatif = chemin.relative_to(RACINE).as_posix()
            for numero, ligne in enumerate(chemin.read_text().splitlines(), 1):
                if not INTERDIT.search(ligne):
                    continue
                if relatif in TOLERES:
                    toleres_vus.add(relatif)
                    continue
                fautifs.append(f"{relatif}:{numero}: {ligne.strip()}")
        self.assertEqual(
            fautifs, [],
            "Règle du périmètre récrite hors de accounts/perimetre.py "
            "(passez par `filtrer`) :\n" + "\n".join(fautifs),
        )
        self.assertEqual(
            set(TOLERES), toleres_vus,
            "Un cas toléré n'existe plus : retirez-le de la liste.",
        )

    def test_la_primitive_porte_bien_la_regle(self):
        """Les chemins y sont des paramètres : la règle s'écrit ``{pays}__in``."""
        source = PRIMITIVE.read_text()
        self.assertIn("def filtrer(", source)
        self.assertIn('f"{pays}__in"', source)
        self.assertIn('f"{equipe}__in"', source)
