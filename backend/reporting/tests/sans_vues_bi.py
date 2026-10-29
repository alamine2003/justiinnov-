"""Pour les tests qui rejouent des migrations à la main (``MigrationExecutor``).

``migrate`` retire les vues du schéma ``bi`` avant de migrer et les repose
après (``reporting.apps``). Un test qui pilote l'exécuteur directement ne
passe pas par ces signaux : une vue bloquerait alors la modification d'une
colonne qu'elle lit. Ce mélange les retire au début du test et les repose
à la fin, une fois la base revenue à son dernier état.
"""

from django.db import connection

from reporting.bi import installer_les_vues, retirer_les_vues


class SansVuesBI:
    def setUp(self):
        super().setUp()
        retirer_les_vues(connection)
        self.addCleanup(installer_les_vues, connection)
