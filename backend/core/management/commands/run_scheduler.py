"""Ordonnanceur des tâches périodiques.

Les alertes et les rapports étaient documentés comme des lignes de crontab à
poser sur l'hôte. Documentées, donc pas faites : rien ne les exécutait, et une
alerte non planifiée n'avertit personne — un dépassement survenu un dimanche
attendait que quelqu'un ouvre une page.

Cette commande tourne dans son propre conteneur, jamais dans un worker
gunicorn : trois workers déclencheraient trois fois chaque tâche.
"""

import logging
import signal

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger("scheduler")

#: Tâches et leur cadence, en syntaxe cron.
#:
#: L'heure est celle du fuseau du serveur ; le rapport hebdomadaire part donc
#: le lundi matin, avant que le siège n'ouvre.
JOBS = [
    {
        "id": "notify_alerts",
        "label": "Notification des alertes",
        "cron": "SCHEDULE_ALERTS",
        "default": "0 * * * *",
        "command": ("notify_alerts", {}),
    },
    {
        "id": "weekly_report",
        "label": "Rapport de rapprochement hebdomadaire",
        "cron": "SCHEDULE_WEEKLY_REPORT",
        "default": "0 7 * * 1",
        "command": ("send_periodic_report", {"period": "weekly"}),
    },
    {
        "id": "monthly_report",
        "label": "Rapport de rapprochement mensuel",
        "cron": "SCHEDULE_MONTHLY_REPORT",
        "default": "0 7 1 * *",
        "command": ("send_periodic_report", {"period": "monthly"}),
    },
]


def run_job(job):
    """Exécute une tâche sans jamais laisser l'ordonnanceur s'arrêter.

    Une commande qui lève — serveur SMTP injoignable, base momentanément
    indisponible — ne doit pas emporter avec elle les tâches suivantes.
    """
    name, options = job["command"]
    try:
        logger.info("→ %s", job["label"])
        call_command(name, **options)
        logger.info("✓ %s", job["label"])
    except Exception:
        logger.exception("✗ %s a échoué ; les autres tâches continuent", job["label"])


class Command(BaseCommand):
    help = "Exécute les tâches périodiques (alertes, rapports)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Exécute chaque tâche une fois puis sort, sans planifier.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Affiche le calendrier sans rien exécuter.",
        )

    def handle(self, *args, **options):
        planning = [
            (job, os_cron(job)) for job in JOBS
        ]

        if options["list"]:
            for job, expression in planning:
                self.stdout.write(f"{expression:<16} {job['label']}")
            return

        if options["once"]:
            for job, _ in planning:
                run_job(job)
            return

        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
        for job, expression in planning:
            scheduler.add_job(
                run_job,
                CronTrigger.from_crontab(expression, timezone=settings.TIME_ZONE),
                args=[job],
                id=job["id"],
                # Une tâche manquée pendant un redémarrage se rattrape dans
                # l'heure ; au-delà, elle est périmée et son exécution
                # tardive brouillerait plus qu'elle n'informerait.
                misfire_grace_time=3600,
                # Deux exécutions simultanées de la même tâche notifieraient
                # deux fois : une seule à la fois, la suivante attend.
                max_instances=1,
                coalesce=True,
            )
            self.stdout.write(f"planifié : {expression:<16} {job['label']}")

        # Un arrêt de conteneur doit laisser une tâche en cours se terminer,
        # pour ne pas couper un envoi au milieu de sa liste de destinataires.
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: scheduler.shutdown(wait=True))

        self.stdout.write(self.style.SUCCESS("Ordonnanceur démarré."))
        scheduler.start()


def os_cron(job):
    """Cadence de la tâche, surchargeable par l'environnement."""
    import os

    return os.environ.get(job["cron"], job["default"]).strip()
