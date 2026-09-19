"""Contrôle de fraîcheur des sauvegardes : une sauvegarde qui manque se dit.

Les services de sauvegarde (``deploy/sauvegarder.sh``) écrivent un
marqueur daté dans le volume après chaque réussite — ``base``, ``pieces``
et ``distant`` (la copie hors machine). Ce volume est monté en lecture
seule dans l'ordonnanceur (``SAUVEGARDES_MARQUEURS``), et cette commande,
chaque matin (``SCHEDULE_VERIF_SAUVEGARDES``), lit les trois marqueurs :
un marqueur absent, ou plus vieux que ``SAUVEGARDES_AGE_MAX_HEURES`` (26 h
par défaut, une nuit et une marge), devient une notification **critique**
aux administrateurs, in-app et par e-mail — parce qu'un « ✘ » dans le
journal d'un conteneur, personne ne le lit un dimanche.

Une seule notification par jour et par sauvegarde (clé d'unicité datée) :
un manque qui dure se rappelle chaque matin, pas toutes les heures.

Sans ``SAUVEGARDES_MARQUEURS`` (développement, CI), la commande le dit et
ne vérifie rien.
"""

from datetime import datetime, timedelta, timezone as fuseaux
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from accounts.models import Role
from notifications.models import Notification
from notifications.services import notify, recipients_for

#: Ce que chaque marqueur atteste, dans l'ordre où l'on veut le lire.
SAUVEGARDES = {
    "base": _("la sauvegarde de la base"),
    "pieces": _("le miroir des justificatifs"),
    "distant": _("la copie hors machine"),
    "base-physique": _("la sauvegarde physique"),
}

#: Seuils propres à certaines sauvegardes. La sauvegarde physique est
#: hebdomadaire : lui appliquer le seuil quotidien la déclarerait en retard
#: six jours sur sept, et une alerte qui crie tous les jours n'est plus lue.
#: Huit jours laissent passer un retard d'un jour sans rien dire.
AGES_MAX_HEURES = {"base-physique": 24 * 8}

#: Suffixe du service à consulter dans les journaux, par sauvegarde.
SERVICES = {
    "base": "", "base-physique": "", "pieces": "-pieces", "distant": "-distante",
}

#: Qui est prévenu : ceux qui tiennent l'exploitation.
DESTINATAIRES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})


def lire_marqueur(dossier, quoi):
    """Instant de la dernière réussite, ou ``None`` si le marqueur manque."""
    marqueur = Path(dossier) / f".derniere-reussite-{quoi}"
    try:
        texte = marqueur.read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except (OSError, ValueError):
        return None


def dernier_dump(dossier):
    """Repli pour ``base`` avant le premier marqueur : la date du dump le
    plus récent du volume — les dumps existaient avant les marqueurs."""
    try:
        dumps = list((Path(dossier) / "base").glob("*.dump"))
    except OSError:
        return None
    if not dumps:
        return None
    plus_recent = max(dump.stat().st_mtime for dump in dumps)
    return datetime.fromtimestamp(plus_recent, tz=fuseaux.utc)


def anomalies(dossier, *, age_max, maintenant=None):
    """``[(quoi, dernière réussite ou None)]`` pour ce qui manque ou vieillit."""
    maintenant = maintenant or timezone.now()
    trouvees = []
    for quoi in SAUVEGARDES:
        seuil = age_max
        if quoi in AGES_MAX_HEURES:
            seuil = timedelta(hours=AGES_MAX_HEURES[quoi])
        derniere = lire_marqueur(dossier, quoi)
        if derniere is None and quoi == "base":
            derniere = dernier_dump(dossier)
        if derniere is None or maintenant - derniere > seuil:
            trouvees.append((quoi, derniere))
    return trouvees


def archivage_en_panne():
    """L'archivage des segments est-il cassé *en ce moment* ?

    On ne regarde pas l'ancienneté du dernier segment archivé : une nuit
    sans écriture n'en produit aucun, et alerter là-dessus crierait au loup
    tous les week-ends. Le signal juste est la comparaison des deux
    horodatages de ``pg_stat_archiver`` — un échec **postérieur** au dernier
    succès veut dire que Postgres réessaie et n'y arrive pas.

    Cela n'attend pas : tant que l'archivage échoue, Postgres conserve ses
    segments dans ``pg_wal``, où ils s'accumulent jusqu'à remplir le disque
    de la base — et l'arrêter.

    Rend ``(segment, instant)`` de l'échec, ou ``None`` si tout va bien ou
    si l'archivage n'est pas activé.
    """
    with connection.cursor() as curseur:
        curseur.execute("SHOW archive_mode")
        if (curseur.fetchone() or [""])[0] not in ("on", "always"):
            return None
        curseur.execute(
            "SELECT last_failed_wal, last_failed_time, last_archived_time "
            "FROM pg_stat_archiver"
        )
        ligne = curseur.fetchone()
    if not ligne or ligne[1] is None:
        return None
    segment, echoue_a, archive_a = ligne
    if archive_a is not None and archive_a >= echoue_a:
        return None
    return segment, echoue_a


class Command(BaseCommand):
    help = "Vérifie que chaque sauvegarde a réussi récemment ; prévient sinon."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche l'état sans notifier personne.",
        )

    def handle(self, *args, **options):
        dossier = settings.SAUVEGARDES_MARQUEURS
        if not dossier:
            self.stdout.write(
                "SAUVEGARDES_MARQUEURS n'est pas défini : aucun contrôle de "
                "fraîcheur des sauvegardes (normal hors production)."
            )
            return
        age_max = timedelta(hours=settings.SAUVEGARDES_AGE_MAX_HEURES)
        maintenant = timezone.now()
        trouvees = anomalies(dossier, age_max=age_max, maintenant=maintenant)

        for quoi in SAUVEGARDES:
            derniere = lire_marqueur(dossier, quoi)
            etat = derniere.isoformat(timespec="minutes") if derniere else "jamais (aucun marqueur)"
            self.stdout.write(f"{quoi:<14} dernière réussite : {etat}")

        panne = archivage_en_panne()
        if panne is not None:
            segment, echoue_a = panne
            self.stdout.write(self.style.ERROR(
                f"✘ archivage des segments en échec depuis {echoue_a:%d/%m/%Y %H:%M} "
                f"(segment {segment or '?'})"
            ))
            if not options["dry_run"]:
                self._prevenir_de_l_archivage(segment, echoue_a, maintenant)

        if not trouvees:
            if panne is None:
                self.stdout.write(self.style.SUCCESS("✔ Sauvegardes à jour."))
            return

        for quoi, derniere in trouvees:
            self.stdout.write(self.style.ERROR(f"✘ {quoi} : en retard ou absente"))
        if options["dry_run"]:
            return

        jour = maintenant.date().isoformat()
        destinataires = recipients_for(DESTINATAIRES)
        for quoi, derniere in trouvees:
            if derniere is None:
                detail = _("Aucune réussite enregistrée : le service ne tourne pas, ou n'a jamais abouti.")
            else:
                detail = format_lazy(
                    _("Dernière réussite le {quand} ; plus de {heures} h sans sauvegarde."),
                    quand=timezone.localtime(derniere).strftime("%d/%m/%Y %H:%M"),
                    heures=settings.SAUVEGARDES_AGE_MAX_HEURES,
                )
            notify(
                destinataires,
                kind=Notification.Kind.STORAGE_ERROR,
                level=Notification.Level.CRITICAL,
                title=format_lazy(_("Sauvegarde en défaut — {quoi}"), quoi=SAUVEGARDES[quoi]),
                body=format_lazy(
                    _("{detail} Vérifiez « docker compose logs sauvegarde{suffixe} » sur le serveur (deploy/README.md, « Sauvegardes et restauration »)."),
                    detail=detail,
                    suffixe=SERVICES[quoi],
                ),
                link="/configuration",
                dedup_key=f"sauvegardes:{jour}:{quoi}",
            )
        self.stdout.write(f"{len(trouvees)} notification(s) émise(s).")

    def _prevenir_de_l_archivage(self, segment, echoue_a, maintenant):
        """Un archivage cassé ne se contente pas d'interrompre la reprise :
        Postgres garde ses segments et finit par remplir le disque."""
        notify(
            recipients_for(DESTINATAIRES),
            kind=Notification.Kind.STORAGE_ERROR,
            level=Notification.Level.CRITICAL,
            title=_("Archivage des journaux en échec"),
            body=format_lazy(
                _(
                    "Depuis le {quand}, Postgres n'arrive plus à archiver ses "
                    "journaux (segment {segment}). Deux conséquences : la reprise "
                    "à un instant donné s'arrête à la dernière réussite, et les "
                    "segments s'accumulent sur le disque de la base jusqu'à la "
                    "bloquer. Vérifiez « docker compose logs db » et l'espace "
                    "libre du volume des sauvegardes (deploy/README.md, "
                    "« Reprise à un instant donné »)."
                ),
                quand=timezone.localtime(echoue_a).strftime("%d/%m/%Y %H:%M"),
                segment=segment or "?",
            ),
            link="/configuration",
            dedup_key=f"archivage:{maintenant.date().isoformat()}",
        )
