"""Émission des notifications : destinataires, in-app puis e-mail.

Chaque destinataire lit sa notification et son e-mail dans **sa** langue :
titre et corps sont rendus au moment de l'écriture, sous la langue du
profil. Un titre rendu en amont l'aurait été dans la langue du processus
émetteur — celle de l'ordonnanceur, pour tout le monde.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMessage, get_connection
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from accounts.models import ALWAYS_GLOBAL_ROLES, HEADQUARTERS_ROLES

from .models import Notification

logger = logging.getLogger(__name__)

#: Langue des destinataires dont le profil n'en déclare pas.
LANGUE_PAR_DEFAUT = "fr"


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


def recipients_for(roles, country=None):
    """Comptes actifs portant l'un des rôles et couvrant le pays visé.

    Un rôle du siège sans périmètre couvre tous les pays ; un rôle pays — ou
    un rôle du siège au périmètre restreint — n'est concerné que si le pays
    fait partie de son périmètre : la même règle que le cloisonnement des
    données. Sans ``country``, tous les comptes du rôle sont renvoyés, et
    c'est à l'appelant de cloisonner ce qu'il leur envoie.
    """
    roles = list(roles)
    users = User.objects.filter(
        is_active=True, profile__role__in=roles
    ).select_related("profile")

    if country is None:
        return users.distinct()

    global_roles = [r for r in roles if r in ALWAYS_GLOBAL_ROLES]
    hq_roles = [r for r in roles if r in HEADQUARTERS_ROLES]
    return users.filter(
        # Rattaché explicitement au pays…
        Q(profile__countries=country)
        # …ou rôle du siège sans périmètre restreint…
        | Q(profile__role__in=hq_roles, profile__countries__isnull=True)
        # …ou rôle toujours global.
        | Q(profile__role__in=global_roles)
    ).distinct()


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

    if send_email and created:
        _send_emails(created, link)
    return created


def _sujet(title):
    """Sujet sur une seule ligne : un retour à la ligne dans un libellé de
    dépense ferait lever ``BadHeaderError`` — ou, pire, injecter un en-tête."""
    return _("[Contrôle budgétaire]") + " " + " ".join(title.split())


def _send_emails(notifications, link):
    """Envoie l'e-mail associé, sans jamais faire échouer l'action métier.

    Le sujet et le corps reprennent la ligne enregistrée, déjà rendue dans
    la langue du destinataire ; seul le préfixe du sujet reste à traduire.

    Les lignes à envoyer sont d'abord **réclamées** : ``emailed_at`` est posé
    en une seule mise à jour filtrée sur les lignes encore vierges. L'ordonnanceur
    et une requête web peuvent notifier le même événement au même moment ;
    avec ``ignore_conflicts``, chacun relisait ensuite la même ligne et
    envoyait le même e-mail deux fois. Un seul des deux gagne la mise à jour.

    Un message par destinataire : un envoi groupé exposait à chacun les
    adresses de tous les autres.
    """
    addressed = [n for n in notifications if n.recipient.email]
    if not addressed:
        return

    stamped = timezone.now()
    Notification.objects.filter(
        pk__in=[n.pk for n in addressed], emailed_at__isnull=True
    ).update(emailed_at=stamped)
    reclamees = [
        n for n in Notification.objects.filter(
            pk__in=[n.pk for n in addressed], emailed_at=stamped
        ).select_related("recipient", "recipient__profile")
    ]
    if not reclamees:
        return

    url = f"{settings.APP_BASE_URL}{link}" if link else settings.APP_BASE_URL
    try:
        with get_connection() as connection:
            for notification in reclamees:
                with translation.override(langue_de(notification.recipient)):
                    message = (
                        f"{notification.body}\n\n{url}" if notification.body else url
                    )
                    EmailMessage(
                        subject=_sujet(notification.title),
                        body=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[notification.recipient.email],
                        connection=connection,
                    ).send(fail_silently=False)
    except Exception:
        # Une notification in-app reste enregistrée : l'utilisateur la verra.
        # L'horodatage est retiré : rien n'est parti, il ne faut pas le
        # prétendre.
        logger.exception("Envoi d'e-mail de notification impossible")
        Notification.objects.filter(
            pk__in=[n.pk for n in reclamees], emailed_at=stamped
        ).update(emailed_at=None)
