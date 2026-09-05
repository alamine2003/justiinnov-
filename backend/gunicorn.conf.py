"""Réglages gunicorn qui ne tiennent pas sur la ligne de commande.

Chargé par ``entrypoint.sh`` (``gunicorn -c gunicorn.conf.py``). Les options
de service — workers, threads, délais — restent sur la ligne de commande,
réglables par l'environnement sans reconstruire l'image.
"""

import os


def child_exit(server, worker):
    """Retire de la collecte les compteurs d'un worker qui s'arrête.

    En mode multi-processus (``PROMETHEUS_MULTIPROC_DIR``), chaque worker
    écrit ses compteurs dans des fichiers à son nom. Les workers sont
    recyclés régulièrement (``--max-requests``) : sans ce nettoyage, les
    fichiers des workers morts s'accumulent et ``/metrics`` les additionne
    indéfiniment.
    """
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        return
    from prometheus_client import multiprocess

    multiprocess.mark_process_dead(worker.pid)
