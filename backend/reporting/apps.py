from django.apps import AppConfig
from django.db.models.signals import post_migrate, pre_migrate


def _avant_migration(sender, using, plan=None, **kwargs):
    # ``migrate`` tourne à chaque démarrage du backend, le plus souvent sans
    # rien à migrer. Retirer les vues demande alors un verrou exclusif qu'une
    # requête du BI ou une session pgAdmin peut tenir plus longtemps que le
    # ``lock_timeout`` des migrations : le backend ne démarrerait plus. Sans
    # migration, rien ne bouge sous les vues ; ``post_migrate`` les repose de
    # toute façon, et rattrape lui-même son échec.
    if not plan:
        return
    from django.db import connections

    from .bi import retirer_les_vues

    retirer_les_vues(connections[using])


def _apres_migration(sender, using, plan=None, **kwargs):
    # ``flush`` (vidage des tables, tests transactionnels compris) émet aussi
    # ``post_migrate``, sans plan : les vues n'ont alors pas bougé, et le
    # schéma peut être celui d'une migration intermédiaire.
    if plan is None:
        return
    from django.db import connections

    from .bi import installer_les_vues

    installer_les_vues(connections[using])


class ReportingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reporting"
    verbose_name = "Pilotage et rapports"

    def ready(self):
        # Les vues du BI (décision 122) ne bloquent aucune migration : elles
        # sont retirées avant, et reposées après sur le schéma à jour.
        pre_migrate.connect(_avant_migration, sender=self, dispatch_uid="bi_avant")
        post_migrate.connect(_apres_migration, sender=self, dispatch_uid="bi_apres")
