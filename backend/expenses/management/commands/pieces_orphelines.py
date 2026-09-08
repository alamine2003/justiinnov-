"""Inventaire des objets du stockage qu'aucune fiche ne référence.

Un dépôt refusé par la base après l'écriture du fichier, un effacement qui
a échoué dix fois : ce qui reste dans le stockage sans fiche se voit ici.
Inventaire seulement — rien n'est effacé : un objet du stockage peut être
la seule copie d'une preuve dont la fiche a été perdue, et l'effacer sans
regarder serait pire que le garder. Les objets plus récents que le délai
de sécurité (24 h par défaut) sont écartés : un dépôt en cours n'a pas
encore sa fiche.

    manage.py pieces_orphelines            # liste, un chemin par ligne
    manage.py pieces_orphelines --age 1    # objets de plus d'une heure
"""

from datetime import timedelta

from django.core.management.base import BaseCommand

from expenses.stockage import pieces_orphelines


class Command(BaseCommand):
    help = "Liste les fichiers du stockage qu'aucun justificatif ne référence (sans rien effacer)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--age", type=float, default=24.0,
            help="Âge minimal en heures pour compter un objet comme orphelin (24 par défaut).",
        )

    def handle(self, *args, **options):
        orphelins = pieces_orphelines(age_minimal=timedelta(hours=options["age"]))
        for chemin, modifie in orphelins:
            quand = modifie.isoformat(timespec="seconds") if modifie else "date inconnue"
            self.stdout.write(f"{quand}  {chemin}")
        if orphelins:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(orphelins)} objet(s) sans fiche dans le stockage : "
                    "à examiner avant toute décision."
                )
            )
        elif options["verbosity"] > 0:
            self.stdout.write("aucun objet orphelin")
