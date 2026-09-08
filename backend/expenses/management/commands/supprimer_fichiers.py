"""Reprend l'effacement des fichiers de justificatifs retirés avec un brouillon.

La seule suppression que la plateforme tolère est celle d'un brouillon
jamais soumis, par son auteur ; ses pièces partent avec lui. Le fichier
s'efface après le commit du retrait (``expenses.stockage``) ; ce qui ne
s'est pas effacé — stockage injoignable, processus arrêté — est repris ici,
depuis l'ordonnanceur (``SCHEDULE_SUPPRESSIONS``). Aucune fiche, aucune
ligne, aucun dossier n'est touché : seuls des fichiers dont la demande
d'effacement a été enregistrée dans la transaction du retrait.
"""

from django.core.management.base import BaseCommand

from expenses.stockage import supprimer_les_fichiers


class Command(BaseCommand):
    help = "Efface les fichiers des pièces retirées avec leur brouillon, restés en attente."

    def handle(self, *args, **options):
        effaces, echecs = supprimer_les_fichiers()
        if effaces or echecs:
            self.stdout.write(f"fichiers : {effaces} effacé(s), {echecs} en échec")
        elif options["verbosity"] > 1:
            self.stdout.write("aucun fichier en attente")
