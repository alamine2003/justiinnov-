"""Écriture du journal d'audit.

Chaque action sensible doit produire une trace : qui, quoi, quand, depuis
quelle session, et l'ancienne/nouvelle valeur le cas échéant (§6).
"""

from core.requetes import client_ip

from .models import AuditLog


def preparer(request, action, instance, *, label="", country=None, **detail):
    """Construit une entrée sans l'enregistrer.

    Sert aux actions qui touchent beaucoup d'objets d'un coup (soumission
    d'un dossier de vingt lignes) : les entrées sont écrites ensemble par
    :func:`enregistrer`, en une requête, plutôt qu'une par ligne.
    """
    user = getattr(request, "user", None)
    return AuditLog(
        user=user.username if user and user.is_authenticated else "",
        action=action,
        object_type=instance.__class__.__name__,
        object_id=instance.pk,
        label=(label or str(instance))[:250],
        country=country if country is not None else getattr(instance, "country", None),
        detail=detail,
        # Adresse lue derrière les mandataires de confiance : ``REMOTE_ADDR``
        # seul ne donnerait que celle de nginx.
        ip_address=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
    )


def record(request, action, instance, *, label="", country=None, **detail):
    """Journalise une action sur une instance."""
    entree = preparer(
        request, action, instance, label=label, country=country, **detail
    )
    entree.save()
    return entree


def enregistrer(entrees):
    """Écrit d'un coup des entrées préparées."""
    return AuditLog.objects.bulk_create(list(entrees))
