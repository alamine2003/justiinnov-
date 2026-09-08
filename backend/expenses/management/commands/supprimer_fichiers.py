"""Reprend l'effacement des fichiers de justificatifs retirés avec un brouillon.

La seule suppression que la plateforme tolère est celle d'un brouillon
jamais soumis, par son auteur ; ses pièces partent avec lui. Le fichier
s'efface après le commit du retrait (``expenses.stockage``) ; ce qui ne
s'est pas effacé — stockage injoignable, processus arrêté — est repris ici,
depuis l'ordonnanceur (``SCHEDULE_SUPPRESSIONS``). Aucune fiche, aucune
ligne, aucun dossier n'est touché : seuls des fichiers dont la demande
d'effacement a été enregistrée dans la transaction du retrait.
"""

import logging

from django.core.management.base import BaseCommand

from expenses.models import FichierASupprimer
from expenses.stockage import ESSAIS_MAX, supprimer_les_fichiers

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Efface les fichiers des pièces retirées avec leur brouillon, restés en attente."

    def handle(self, *args, **options):
        effaces, echecs = supprimer_les_fichiers()
        if effaces or echecs:
            self.stdout.write(f"fichiers : {effaces} effacé(s), {echecs} en échec")
        elif options["verbosity"] > 1:
            self.stdout.write("aucun fichier en attente")

        # L'échec doit se voir : la commande tourne dans l'ordonnanceur, dont
        # seule la sortie est lue. Un fichier qui a épuisé ses essais ne sera
        # plus repris — il reste dans le stockage, et personne ne le saurait.
        if echecs:
            logger.warning("%d effacement(s) de fichier en échec, à reprendre", echecs)
        abandonnes = FichierASupprimer.objects.filter(
            deleted_at__isnull=True, attempts__gte=ESSAIS_MAX
        ).count()
        if abandonnes:
            message = (
                f"{abandonnes} fichier(s) n'ont pas pu être effacés après "
                f"{ESSAIS_MAX} essais : ils restent dans le stockage. "
                "Voir « manage.py pieces_orphelines » et la colonne "
                "last_error de FichierASupprimer."
            )
            logger.error(message)
            self.stderr.write(self.style.ERROR(message))
