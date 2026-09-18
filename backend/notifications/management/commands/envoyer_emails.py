"""Reprend les e-mails de notification qui ne sont pas partis.

L'e-mail d'une notification part juste après la validation de l'action qui
la crée (``notifications.services.notify``). Quand il ne part pas — serveur
de courrier en panne, processus arrêté entre le commit et l'envoi —, la
ligne reste avec ``emailed_at`` vide : c'est elle qui dit ce qui reste à
faire. Cette commande la reprend, depuis l'ordonnanceur, toutes les cinq
minutes (``SCHEDULE_EMAILS``), jusqu'à ``ESSAIS_MAX`` essais et pour les
notifications de moins de ``AGE_MAX_DE_REPRISE``.
"""

from django.core.management.base import BaseCommand

from notifications.services import abandonnees, envoyer_les_emails


class Command(BaseCommand):
    help = "Envoie les e-mails de notification restés en attente."

    def handle(self, *args, **options):
        envoyes, echecs = envoyer_les_emails()
        perdues = abandonnees().count()
        if envoyes or echecs:
            self.stdout.write(f"e-mails : {envoyes} envoyé(s), {echecs} en échec")
        if perdues:
            # Dit ici aussi : la sortie de la commande est ce que lit celui
            # qui la lance à la main pour comprendre un incident.
            self.stdout.write(
                self.style.WARNING(
                    f"{perdues} notification(s) abandonnée(s) : essais épuisés, "
                    "toujours lisibles dans l'application"
                )
            )
        elif options["verbosity"] > 1:
            self.stdout.write("aucun e-mail en attente")
