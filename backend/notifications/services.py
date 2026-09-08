"""Émission des notifications : destinataires, in-app puis e-mail.

Chaque destinataire lit sa notification et son e-mail dans **sa** langue :
titre et corps sont rendus au moment de l'écriture, sous la langue du
profil. Un titre rendu en amont l'aurait été dans la langue du processus
émetteur — celle de l'ordonnanceur, pour tout le monde.

**La notification et l'e-mail sont deux choses.** La ligne in-app est
écrite dans la transaction de l'action qu'elle signale : une transition
annulée ne laisse pas de notification derrière elle. L'e-mail, lui, part
**après** la validation de cette transaction (``transaction.on_commit``),
hors de tout verrou métier : un serveur SMTP lent bloquait l'enveloppe du
pays le temps de cinq envois, et un serveur en panne faisait de chaque
soumission une attente de dix secondes. ``on_commit`` ne garantit pas la
livraison — un processus qui meurt entre le commit et l'envoi perd le
rappel — : la ligne elle-même est l'enregistrement durable du travail
restant (``emailed_at`` vide), et ``envoyer_les_emails`` reprend ces lignes
depuis l'ordonnanceur (``manage.py envoyer_emails``, toutes les cinq
minutes) jusqu'à ``ESSAIS_MAX`` essais.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from accounts.perimetre import comptes_couvrant

from .models import Notification

logger = logging.getLogger(__name__)

#: Langue des destinataires dont le profil n'en déclare pas.
LANGUE_PAR_DEFAUT = "fr"

#: Une ligne réclamée pour un envoi (``email_attempted_at`` posé) n'est
#: reprise par un autre processus qu'après ce délai : le temps qu'un envoi
#: en cours aboutisse, ou qu'un processus mort soit tenu pour tel. Un envoi
#: interrompu entre la réclamation et ``send()`` est donc rejoué — au pire
#: en double, jamais perdu.
DELAI_DE_REPRISE = timedelta(minutes=10)

#: Au-delà, on n'insiste plus : une adresse invalide ou un serveur qui
#: refuse durablement se lisent dans les journaux, pas dans une boucle.
ESSAIS_MAX = 5

#: L'ordonnanceur ne reprend pas les lignes plus anciennes : une
#: notification d'il y a un mois dont l'e-mail n'est jamais parti n'a plus
#: à partir, et les lignes antérieures à la reprise (``emailed_at`` vide
#: parce que le destinataire n'avait pas d'adresse) ne doivent pas se
#: mettre à partir en bloc au premier passage.
AGE_MAX_DE_REPRISE = timedelta(days=3)


def langue_de(user):
    """Langue du profil, ou le français à défaut.

    Le champ ``language`` du profil peut ne pas exister encore (il relève
    du référentiel des comptes) : l'absence vaut « fr », jamais une erreur.
    """
    profile = getattr(user, "profile", None)
    return getattr(profile, "language", None) or LANGUE_PAR_DEFAUT


def rendre(texte, langue):
    """Texte — chaîne ou chaîne paresseuse — rendu dans la langue donnée."""
    with translation.override(langue):
        return str(texte)


def recipients_for(roles, country=None, team=None):
    """Comptes actifs portant l'un des rôles et couvrant le pays — et l'équipe — visés.

    Un rôle du siège sans périmètre couvre tous les pays ; un rôle pays — ou
    un rôle du siège au périmètre restreint — n'est concerné que si le pays
    fait partie de son périmètre : la même règle que le cloisonnement des
    données. Sans ``country``, tous les comptes du rôle sont renvoyés, et
    c'est à l'appelant de cloisonner ce qu'il leur envoie.

    ``team`` — l'équipe d'un dossier ou d'une ligne — applique le second
    cloisonnement, celui des managers : rattaché à des équipes, un manager
    n'est prévenu que de ce qui touche les siennes ; sans équipe, il couvre
    tout son pays (``UserProfile.team_ids``). Les rôles du siège ne sont
    jamais cloisonnés par équipe : le DM et le DF contrôlent le pays entier,
    et une équipe posée sur leur profil ne porte aucun droit. Une alerte
    d'enveloppe, qui se lit par pays, ne passe pas d'équipe.

    La règle est celle du cloisonnement des lectures, lue depuis l'objet :
    ``accounts.perimetre.comptes_couvrant`` (décision 39).
    """
    users = User.objects.filter(
        is_active=True, profile__role__in=list(roles)
    ).select_related("profile")

    if country is None:
        return users.distinct()
    return comptes_couvrant(users, country, team)


def _deja_avertis(dedup_key, recipients):
    """Destinataires déjà notifiés de cet événement, en une requête."""
    return set(
        Notification.objects.filter(
            dedup_key=dedup_key, recipient__in=recipients
        ).values_list("recipient_id", flat=True)
    )


def notify(recipients, *, kind, title, dedup_key, body="", level=None, link="",
           country=None, send_email=True):
    """Crée les notifications manquantes et envoie les e-mails correspondants.

    ``dedup_key`` garantit qu'un même événement — un seuil budgétaire franchi,
    par exemple — ne notifie qu'une fois par destinataire, même si le calcul
    d'alertes est rejoué.

    L'écriture est groupée : un ``get_or_create`` par destinataire coûtait deux
    requêtes chacun, ce qui devient ruineux dès qu'une centaine de dossiers
    déclenchent chacun une alerte.
    """
    level = level or Notification.Level.INFO
    recipients = list(recipients)
    if not recipients:
        return []

    deja = _deja_avertis(dedup_key, recipients)
    manquants = [r for r in recipients if r.pk not in deja]
    if not manquants:
        return []

    Notification.objects.bulk_create(
        [
            Notification(
                recipient=recipient,
                dedup_key=dedup_key,
                kind=kind,
                level=level,
                # Rendus ici, destinataire par destinataire : la ligne en
                # base est déjà dans la langue de celui qui la lira.
                title=rendre(title, langue_de(recipient)),
                body=rendre(body, langue_de(recipient)),
                link=link,
                country=country,
            )
            for recipient in manquants
        ],
        # Deux processus peuvent notifier le même événement en même temps :
        # la contrainte d'unicité tranche, sans faire échouer l'appel.
        ignore_conflicts=True,
    )
    created = list(
        Notification.objects.filter(
            dedup_key=dedup_key, recipient__in=manquants
        ).select_related("recipient", "recipient__profile")
    )

    if send_email:
        a_envoyer = [n.pk for n in created if n.recipient.email]
        if a_envoyer:
            # Après la validation de la transaction de l'appelant — hors
            # transaction, tout de suite. ``robust`` : un échec ici ne
            # remonte pas à l'appelant, la ligne reste à reprendre.
            transaction.on_commit(lambda: envoyer_les_emails(a_envoyer), robust=True)
    return created


def _sujet(title):
    """Sujet sur une seule ligne : un retour à la ligne dans un libellé de
    dépense ferait lever ``BadHeaderError`` — ou, pire, injecter un en-tête."""
    return _("[Contrôle budgétaire]") + " " + " ".join(title.split())


def reclamer(pks=None, *, maintenant):
    """Réclame les lignes dont l'e-mail reste à envoyer, en une mise à jour.

    Une seule requête conditionnelle : la ligne n'est prise que si l'e-mail
    n'est pas parti, si personne ne l'a réclamée depuis moins de
    ``DELAI_DE_REPRISE`` et si les essais ne sont pas épuisés. Deux
    processus — la requête qui vient de commiter et l'ordonnanceur — ne
    peuvent pas la prendre tous les deux : le second ne voit plus la
    condition vraie. Sans ``pks`` (ordonnanceur), les lignes plus vieilles
    que ``AGE_MAX_DE_REPRISE`` sont laissées.
    """
    a_reprendre = Notification.objects.filter(
        emailed_at__isnull=True,
        recipient__email__gt="",
        email_attempts__lt=ESSAIS_MAX,
    ).filter(
        Q(email_attempted_at__isnull=True)
        | Q(email_attempted_at__lt=maintenant - DELAI_DE_REPRISE)
    )
    if pks is not None:
        a_reprendre = a_reprendre.filter(pk__in=pks)
    else:
        a_reprendre = a_reprendre.filter(created_at__gte=maintenant - AGE_MAX_DE_REPRISE)
    a_reprendre.update(
        email_attempted_at=maintenant, email_attempts=F("email_attempts") + 1
    )
    reclamees = Notification.objects.filter(
        email_attempted_at=maintenant, emailed_at__isnull=True
    ).select_related("recipient", "recipient__profile")
    if pks is not None:
        reclamees = reclamees.filter(pk__in=pks)
    return list(reclamees)


def envoyer_les_emails(pks=None):
    """Envoie les e-mails des notifications réclamées ; rend ``(envoyés, échecs)``.

    Appelé tout de suite après le commit de l'action (``notify``), puis par
    l'ordonnanceur pour ce qui n'est pas parti. Chaque message est envoyé et
    marqué **un par un** : trois envois réussis sur cinq restent acquis
    quand le quatrième échoue, et ne repartent pas. ``emailed_at`` n'est
    posé qu'après ``send()`` — jamais avant : un horodatage posé d'avance
    prétendait qu'un e-mail était parti quand le processus mourait entre
    les deux.

    Un message par destinataire : un envoi groupé exposait à chacun les
    adresses de tous les autres. Le sujet et le corps reprennent la ligne
    enregistrée, déjà rendue dans la langue du destinataire ; seul le
    préfixe du sujet reste à traduire. Aucune exception ne sort d'ici : un
    échec est journalisé, la ligne reste à reprendre.
    """
    reclamees = reclamer(pks, maintenant=timezone.now())
    if not reclamees:
        return 0, 0

    envoyes = echecs = 0
    try:
        connection = get_connection()
        connection.open()
    except Exception:
        logger.exception(
            "Serveur de courrier injoignable : %d e-mail(s) à reprendre", len(reclamees)
        )
        return 0, len(reclamees)
    try:
        for notification in reclamees:
            if _envoyer_un(notification, connection):
                envoyes += 1
            else:
                echecs += 1
    finally:
        try:
            connection.close()
        except Exception:
            logger.exception("Fermeture de la connexion de courrier impossible")
    return envoyes, echecs


def _envoyer_un(notification, connection):
    """Un e-mail ; ``True`` s'il est parti et marqué comme tel."""
    lien = notification.link
    url = f"{settings.APP_BASE_URL}{lien}" if lien else settings.APP_BASE_URL
    try:
        with translation.override(langue_de(notification.recipient)):
            message = f"{notification.body}\n\n{url}" if notification.body else url
            EmailMessage(
                subject=_sujet(notification.title),
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[notification.recipient.email],
                connection=connection,
            ).send(fail_silently=False)
    except Exception:
        # La notification in-app reste enregistrée : l'utilisateur la verra.
        # Rien n'est parti, rien ne le prétend ; l'ordonnanceur reprendra.
        logger.exception(
            "Envoi d'e-mail de notification impossible (notification %s, essai %d/%d)",
            notification.pk, notification.email_attempts, ESSAIS_MAX,
        )
        return False
    Notification.objects.filter(pk=notification.pk).update(emailed_at=timezone.now())
    return True
