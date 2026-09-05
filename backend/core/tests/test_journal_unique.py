"""La façade ``core.journal`` est la seule porte d'écriture des journaux.

Décision 38 : une entrée d'audit ou d'historique écrite ailleurs remplirait
« qui, depuis quelle adresse » à sa façon — ou pas du tout. Le test parcourt
les sources et refuse toute création directe hors de la façade.
"""

import re

from django.test import SimpleTestCase

from .aides import RACINE, sources
FACADE = RACINE / "core" / "journal.py"
INTERDIT = re.compile(r"\b(AuditLog|ChangeLog)\.objects\.(create|bulk_create)\(")


class JournalUniqueTests(SimpleTestCase):
    def test_aucune_ecriture_directe_hors_de_la_facade(self):
        fautifs = []
        for chemin in sources():
            if chemin == FACADE:
                continue
            for numero, ligne in enumerate(chemin.read_text().splitlines(), 1):
                if INTERDIT.search(ligne):
                    fautifs.append(f"{chemin.relative_to(RACINE)}:{numero}: {ligne.strip()}")
        self.assertEqual(
            fautifs, [],
            "Écriture directe d'un journal hors de core/journal.py :\n" + "\n".join(fautifs),
        )

    def test_la_facade_existe_et_ecrit_les_deux_journaux(self):
        source = FACADE.read_text()
        self.assertIn("ChangeLog(", source)
        self.assertIn('get_model("expenses", "AuditLog")', source)
