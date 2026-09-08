"""Le stockage des justificatifs, sans jamais perdre un fichier.

Un stockage objet n'a pas de retour arrière : un fichier effacé dans une
transaction que la base défait ensuite est perdu pour de bon, et sa fiche
— revenue avec la transaction — pointe dans le vide. Trois règles, tenues
ici (audit du 8 septembre 2026, §4.4) :

- **Rien ne s'efface tant que la transaction peut être annulée.** La seule
  suppression tolérée — les pièces d'un brouillon retiré par son auteur —
  est *demandée* dans la transaction (:class:`~expenses.models.FichierASupprimer`,
  qui n'existe que si le retrait est acquis) et *exécutée* après le commit
  (:func:`programmer_la_suppression`), puis reprise par l'ordonnanceur
  (:func:`supprimer_les_fichiers`, ``manage.py supprimer_fichiers``).
- **Un dépôt qui échoue ne laisse pas d'objet orphelin** : le fichier écrit
  par ``FileField`` avant un ``INSERT`` refusé est retiré aussitôt
  (:func:`effacer_sans_bruit`, depuis ``ProofSerializer.create``).
- **Ce qui reste malgré tout se voit** : :func:`pieces_orphelines` inventorie
  les objets du stockage qu'aucune fiche ne référence, sans rien effacer.
"""

import logging
from datetime import timedelta

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import FichierASupprimer, Proof

logger = logging.getLogger(__name__)

#: Une demande réclamée (``attempted_at`` posé) n'est reprise par un autre
#: processus qu'après ce délai.
DELAI_DE_REPRISE = timedelta(minutes=10)

#: Au-delà, on n'insiste plus : la ligne reste, avec sa dernière erreur, et
#: l'inventaire des orphelins la montrera.
ESSAIS_MAX = 10

#: Préfixe des justificatifs dans le stockage (``models.proof_upload_path``).
PREFIXE = "justificatifs"


def programmer_la_suppression(piece, *, trace, dossier):
    """Enregistre la demande d'effacement du fichier de ``piece`` ; l'exécute
    après le commit de la transaction en cours.

    Appelé sous verrou, dans la transaction du retrait : si elle est
    défaite, la demande l'est aussi et le fichier reste à sa place — avec
    la fiche, revenue elle aussi.
    """
    demande = FichierASupprimer.objects.create(
        name=piece.file.name,
        sha256=piece.sha256,
        dossier_number=dossier.number,
        country=dossier.country,
        requested_by=trace.user,
    )
    transaction.on_commit(lambda: supprimer_les_fichiers([demande.pk]), robust=True)
    return demande


def reclamer(pks=None, *, maintenant):
    """Réclame les demandes à exécuter, en une mise à jour conditionnelle."""
    a_reprendre = FichierASupprimer.objects.filter(
        deleted_at__isnull=True, attempts__lt=ESSAIS_MAX
    ).filter(
        Q(attempted_at__isnull=True) | Q(attempted_at__lt=maintenant - DELAI_DE_REPRISE)
    )
    if pks is not None:
        a_reprendre = a_reprendre.filter(pk__in=pks)
    a_reprendre.update(attempted_at=maintenant, attempts=F("attempts") + 1)
    reclamees = FichierASupprimer.objects.filter(
        attempted_at=maintenant, deleted_at__isnull=True
    )
    if pks is not None:
        reclamees = reclamees.filter(pk__in=pks)
    return list(reclamees)


def supprimer_les_fichiers(pks=None):
    """Efface les fichiers demandés ; rend ``(effacés, échecs)``.

    Chaque demande est vérifiée avant d'agir : un fichier qu'une fiche
    référence encore n'est **jamais** effacé — la demande est marquée en
    erreur et l'inventaire la montrera. L'effacement n'est acquis
    (``deleted_at``) que lorsque le stockage ne connaît plus l'objet.
    Aucune exception ne sort d'ici.
    """
    demandes = reclamer(pks, maintenant=timezone.now())
    effaces = echecs = 0
    for demande in demandes:
        if Proof.objects.filter(file=demande.name).exists():
            _echec(demande, "une fiche référence encore ce fichier : conservé")
            echecs += 1
            continue
        try:
            if default_storage.exists(demande.name):
                default_storage.delete(demande.name)
            if default_storage.exists(demande.name):
                raise OSError("le stockage a répondu sans effacer l'objet")
        except Exception as exc:
            logger.exception(
                "Effacement impossible de %s (essai %d/%d)",
                demande.name, demande.attempts, ESSAIS_MAX,
            )
            _echec(demande, str(exc)[:1000])
            echecs += 1
            continue
        FichierASupprimer.objects.filter(pk=demande.pk).update(
            deleted_at=timezone.now(), last_error=""
        )
        effaces += 1
    return effaces, echecs


def _echec(demande, message):
    FichierASupprimer.objects.filter(pk=demande.pk).update(last_error=message)


def effacer_sans_bruit(champ_fichier):
    """Retire du stockage le fichier d'un ``FileField``, sans jamais lever.

    Pour un dépôt refusé par la base après l'écriture du fichier : l'objet
    ne doit pas rester orphelin. Un échec ici est journalisé — et
    l'inventaire des orphelins le rattrapera.
    """
    nom = getattr(champ_fichier, "name", "")
    if not nom:
        return
    try:
        champ_fichier.delete(save=False)
    except Exception:
        logger.exception("Fichier d'un dépôt refusé laissé dans le stockage : %s", nom)


def _parcourir(prefixe):
    """Tous les objets du stockage sous ``prefixe``, chemin complet."""
    try:
        repertoires, fichiers = default_storage.listdir(prefixe)
    except (FileNotFoundError, NotADirectoryError):
        return
    for fichier in fichiers:
        yield f"{prefixe}/{fichier}" if prefixe else fichier
    for repertoire in repertoires:
        yield from _parcourir(f"{prefixe}/{repertoire}" if prefixe else repertoire)


def pieces_orphelines(*, age_minimal=timedelta(hours=24), maintenant=None):
    """Objets du stockage qu'aucune fiche ne référence, plus vieux qu'``age_minimal``.

    Inventaire seulement : rien n'est effacé. Le délai de sécurité écarte
    un dépôt en cours, dont la fiche n'est pas encore écrite. Une demande
    d'effacement en attente n'est pas un orphelin : elle est en cours.
    Rend une liste de ``(chemin, date de modification ou None)``.
    """
    maintenant = maintenant or timezone.now()
    references = set(Proof.objects.values_list("file", flat=True))
    en_attente = set(
        FichierASupprimer.objects.filter(deleted_at__isnull=True).values_list(
            "name", flat=True
        )
    )
    orphelins = []
    for chemin in _parcourir(PREFIXE):
        if chemin in references or chemin in en_attente:
            continue
        try:
            modifie = default_storage.get_modified_time(chemin)
        except (NotImplementedError, OSError):
            modifie = None
        if modifie is not None and maintenant - modifie < age_minimal:
            continue
        orphelins.append((chemin, modifie))
    return orphelins
