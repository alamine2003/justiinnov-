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

import shutil
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

#: Copies hors machine confrontées à leur réussite locale. Le marqueur
#: ``distant`` ne dit que la base : un miroir de pièces jamais parti, une
#: sauvegarde physique jamais copiée, ne se voyaient dans aucun marqueur —
#: et la reprise à un instant donné ne survit à la perte du serveur que si
#: les segments partent aussi. Chaque famille a désormais le sien
#: (``sauvegarder.sh``, ``marqueur_distant_de``).
COPIES = {
    "pieces": "distant-pieces",
    "base-physique": "distant-base-physique",
}
#: Ce que chaque copie atteste, dans les notifications.
COPIES_LIBELLES = {
    "pieces": SAUVEGARDES["pieces"],
    "base-physique": SAUVEGARDES["base-physique"],
    "wal": _("les segments de journal archivés"),
}
#: Retard toléré entre une réussite locale et sa copie : le service distant
#: consomme une demande dans la minute, réessaie au quart d'heure ; deux
#: heures laissent passer une copie longue sans crier pour rien.
MARGE_DE_COPIE = timedelta(hours=2)

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


def dernier_segment(dossier):
    """Instant du segment archivé le plus récent, ou ``None`` sans archive.

    C'est la « réussite locale » des segments : Postgres n'écrit pas de
    marqueur, il dépose un fichier. Un ``.partiel`` est en cours d'écriture
    et ne compte pas.
    """
    try:
        segments = [
            fichier for fichier in (Path(dossier) / "base" / "wal").iterdir()
            if fichier.is_file() and not fichier.name.endswith(".partiel")
        ]
    except OSError:
        return None
    if not segments:
        return None
    plus_recent = max(fichier.stat().st_mtime for fichier in segments)
    return datetime.fromtimestamp(plus_recent, tz=fuseaux.utc)


def retards_de_copie(dossier, *, marge=MARGE_DE_COPIE):
    """``[(quoi, réussite locale, dernière copie ou None)]`` pour ce qui a
    réussi ici sans partir là-bas dans la marge.

    Ne dit rien tant que la copie de la base n'a jamais réussi : le marqueur
    ``distant`` manque alors, et c'est lui qui le signale — quatre
    notifications pour une seule cause (pas de distant configuré) ne
    diraient rien de plus.
    """
    if lire_marqueur(dossier, "distant") is None:
        return []
    trouves = []
    for local, distant in COPIES.items():
        ici = lire_marqueur(dossier, local)
        if ici is None:
            continue
        la_bas = lire_marqueur(dossier, distant)
        if la_bas is None or ici - la_bas > marge:
            trouves.append((local, ici, la_bas))
    segment = dernier_segment(dossier)
    if segment is not None:
        la_bas = lire_marqueur(dossier, "distant-wal")
        if la_bas is None or segment - la_bas > marge:
            trouves.append(("wal", segment, la_bas))
    return trouves


def espace_disque(dossier):
    """``(libre en %, libre en octets)`` du disque qui porte le volume, ou
    ``None`` s'il ne se lit pas.

    C'est le disque de la base, de ses segments et des sauvegardes : celui
    qu'un archivage cassé remplit, et le seul dont le manque arrête tout.
    """
    try:
        usage = shutil.disk_usage(dossier)
    except OSError:
        return None
    if usage.total == 0:
        return None
    return usage.free * 100 / usage.total, usage.free


def disque_trop_plein(dossier, *, minimum_pourcent):
    """``(libre en %, libre en octets)`` sous le seuil, sinon ``None``."""
    etat = espace_disque(dossier)
    if etat is None:
        return None
    pourcent, _ = etat
    return etat if pourcent < minimum_pourcent else None


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


def replication_en_panne():
    """La réplique suit-elle encore ?

    Deux défauts, tous deux muets. Un emplacement **perdu**
    (``wal_status = 'lost'``) : la primaire a cessé de garder ce que la
    réplique n'a pas lu — c'est la borne ``max_slot_wal_keep_size`` qui a
    joué, et elle a bien fait, puisque sans elle le disque de la primaire se
    serait rempli. Mais la réplique est alors inutilisable : elle doit être
    **refaite**, pas attendue. Un emplacement **inactif** : la seconde
    machine ne se connecte plus.

    Dans les deux cas, la plateforme tourne parfaitement, et l'on croit
    avoir une réplique qu'on n'a plus. Cela ne se découvre que le jour de la
    bascule, c'est-à-dire le pire.

    Rend ``[(nom, état)]``, vide quand tout va bien — ou qu'aucune réplique
    n'est déclarée, ce qui est le cas tant qu'il n'y a qu'une machine.
    """
    with connection.cursor() as curseur:
        curseur.execute(
            "SELECT slot_name, active, wal_status FROM pg_replication_slots "
            "WHERE slot_type = 'physical'"
        )
        emplacements = curseur.fetchall()
    ennuis = []
    for nom, actif, etat in emplacements:
        if etat == "lost":
            ennuis.append((nom, "perdu"))
        elif not actif:
            ennuis.append((nom, "inactif"))
    return ennuis


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

        replication = replication_en_panne()
        for nom, etat in replication:
            self.stdout.write(self.style.ERROR(
                f"✘ réplique « {nom} » : {etat}"
            ))
            if not options["dry_run"]:
                self._prevenir_de_la_replique(nom, etat, maintenant)

        plein = disque_trop_plein(dossier, minimum_pourcent=settings.SAUVEGARDES_DISQUE_MIN_POURCENT)
        if plein is not None:
            pourcent, octets = plein
            self.stdout.write(self.style.ERROR(
                f"✘ disque des sauvegardes : {pourcent:.0f} % libre "
                f"({octets // (1024 * 1024)} Mo), sous {settings.SAUVEGARDES_DISQUE_MIN_POURCENT} %"
            ))
            if not options["dry_run"]:
                self._prevenir_du_disque(pourcent, octets, maintenant)

        retards = retards_de_copie(dossier)
        for quoi, ici, la_bas in retards:
            etat = la_bas.isoformat(timespec="minutes") if la_bas else "jamais"
            self.stdout.write(self.style.ERROR(
                f"✘ copie hors machine en retard — {quoi} : réussite locale "
                f"{ici.isoformat(timespec='minutes')}, copiée {etat}"
            ))
            if not options["dry_run"]:
                self._prevenir_du_retard_de_copie(quoi, ici, la_bas, maintenant)

        if not trouvees:
            if panne is None and not replication and not retards and plein is None:
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

    def _prevenir_du_disque(self, pourcent, octets, maintenant):
        """Le disque plein n'est pas une panne parmi d'autres : la base
        s'arrête, et les sauvegardes avec elle."""
        notify(
            recipients_for(DESTINATAIRES),
            kind=Notification.Kind.STORAGE_ERROR,
            level=Notification.Level.CRITICAL,
            title=_("Disque du serveur presque plein"),
            body=format_lazy(
                _(
                    # « % d » ressemble à un format Python pour xgettext : sans
                    # ce drapeau, msgfmt --check refuserait une traduction sans lui.
                    # xgettext:no-python-format
                    "Il reste {pourcent} % d'espace libre ({mo} Mo) sur le disque "
                    "qui porte la base, ses journaux archivés et les sauvegardes. "
                    "Plein, il arrête la base. Regardez d'abord « docker compose "
                    "logs db » (un archivage qui échoue garde ses segments) et "
                    "« docker system df » (deploy/README.md, « Reprise à un "
                    "instant donné » et « Revenir en arrière »)."
                ),
                pourcent=f"{pourcent:.0f}",
                mo=octets // (1024 * 1024),
            ),
            link="/configuration",
            dedup_key=f"disque:{maintenant.date().isoformat()}",
        )

    def _prevenir_du_retard_de_copie(self, quoi, ici, la_bas, maintenant):
        """Une sauvegarde réussie qui reste sur la machine n'en est pas une :
        elle brûle avec le serveur. La copie de la base partait ; les autres
        pouvaient échouer chaque nuit sans qu'aucun marqueur ne le dise."""
        if la_bas is None:
            detail = _("Aucune copie hors machine n'a jamais abouti pour cette famille.")
        else:
            detail = format_lazy(
                _("Dernière copie hors machine le {quand}, antérieure à la dernière réussite locale."),
                quand=timezone.localtime(la_bas).strftime("%d/%m/%Y %H:%M"),
            )
        notify(
            recipients_for(DESTINATAIRES),
            kind=Notification.Kind.STORAGE_ERROR,
            level=Notification.Level.CRITICAL,
            title=format_lazy(_("Copie hors machine en retard — {quoi}"), quoi=COPIES_LIBELLES[quoi]),
            body=format_lazy(
                _(
                    "{detail} Réussite locale le {ici}. Tant que la copie ne "
                    "suit pas, cette sauvegarde brûle avec le serveur. Vérifiez "
                    "« docker compose logs sauvegarde-distante » (deploy/README.md, "
                    "« Copie hors machine »)."
                ),
                detail=detail,
                ici=timezone.localtime(ici).strftime("%d/%m/%Y %H:%M"),
            ),
            link="/configuration",
            dedup_key=f"copie:{maintenant.date().isoformat()}:{quoi}",
        )

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

    def _prevenir_de_la_replique(self, nom, etat, maintenant):
        """Une réplique qu'on croit avoir et qu'on n'a plus ne se découvre
        que le jour de la bascule — c'est-à-dire trop tard."""
        if etat == "perdu":
            detail = _(
                "La primaire a cessé de lui garder ses journaux : la réplique "
                "ne peut plus rattraper son retard et doit être **refaite** "
                "(preparer_replique.sh), pas attendue. La plateforme, elle, "
                "n'a rien risqué — c'est précisément ce que cette borne protège."
            )
        else:
            detail = _(
                "La seconde machine ne se connecte plus. Tant qu'elle est "
                "absente, la primaire garde ses journaux pour elle ; au-delà "
                "de la marge, l'emplacement sera déclaré perdu et la réplique "
                "devra être refaite."
            )
        notify(
            recipients_for(DESTINATAIRES),
            kind=Notification.Kind.STORAGE_ERROR,
            level=Notification.Level.CRITICAL,
            title=format_lazy(_("Réplique en défaut — {nom}"), nom=nom),
            body=format_lazy(
                _("{detail} Voir deploy/README.md, « Réplique en attente chaude »."),
                detail=detail,
            ),
            link="/configuration",
            dedup_key=f"replique:{maintenant.date().isoformat()}:{nom}",
        )
