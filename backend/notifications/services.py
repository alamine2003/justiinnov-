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
    d'alertes est rejoué à chaque consultation du tableau de bord.
    """
    level = level or Notification.Level.INFO
    created = []
    for recipient in recipients:
        notification, is_new = Notification.objects.get_or_create(
            recipient=recipient,
            dedup_key=dedup_key,
            defaults={
                "kind": kind,
                "level": level,
                "title": title,
                "body": body,
                "link": link,
                "country": country,
            },
        )
        if is_new:
            created.append(notification)

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
