"""Émission des notifications : destinataires, in-app puis e-mail."""

import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from accounts.models import ALWAYS_GLOBAL_ROLES, HEADQUARTERS_ROLES

from .models import Notification

logger = logging.getLogger(__name__)


def recipients_for(roles, country=None):
    """Comptes actifs portant l'un des rôles et couvrant le pays visé.

    Un rôle du siège sans périmètre couvre tous les pays ; un rôle pays n'est
    concerné que si le pays fait partie de son périmètre — la même règle que
    le cloisonnement des données.
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

    # Une seule requête pour savoir qui a déjà été averti de cet événement.
    deja_avertis = set(
        Notification.objects.filter(
            dedup_key=dedup_key, recipient__in=recipients
        ).values_list("recipient_id", flat=True)
    )
    manquants = [r for r in recipients if r.pk not in deja_avertis]
    if not manquants:
        return []

    Notification.objects.bulk_create(
        [
            Notification(
                recipient=recipient,
                dedup_key=dedup_key,
                kind=kind,
                level=level,
                title=title,
                body=body,
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
        ).select_related("recipient")
    )

    if send_email and created:
        _send_emails(created, title, body, link)
    return created


def _send_emails(notifications, title, body, link):
    """Envoie l'e-mail associé, sans jamais faire échouer l'action métier."""
    addressed = [n for n in notifications if n.recipient.email]
    if not addressed:
        return

    url = f"{settings.APP_BASE_URL}{link}" if link else settings.APP_BASE_URL
    message = f"{body}\n\n{url}" if body else url
    try:
        send_mail(
            subject=f"[Contrôle budgétaire] {title}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[n.recipient.email for n in addressed],
            fail_silently=False,
        )
    except Exception:
        # Une notification in-app reste enregistrée : l'utilisateur la verra.
        logger.exception("Envoi d'e-mail de notification impossible")
        return

    stamped = timezone.now()
    Notification.objects.filter(pk__in=[n.pk for n in addressed]).update(
        emailed_at=stamped
    )
