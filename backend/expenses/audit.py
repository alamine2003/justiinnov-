"""Écriture du journal d'audit.

Chaque action sensible doit produire une trace : qui, quoi, quand, depuis
quelle session, et l'ancienne/nouvelle valeur le cas échéant (§6).
"""

from .models import AuditLog


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        # Le premier élément est l'adresse d'origine.
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def record(request, action, instance, *, label="", country=None, **detail):
    """Journalise une action sur une instance."""
    user = getattr(request, "user", None)
    return AuditLog.objects.create(
        user=user.username if user and user.is_authenticated else "",
        action=action,
        object_type=instance.__class__.__name__,
        object_id=instance.pk,
        label=label or str(instance),
        country=country if country is not None else getattr(instance, "country", None),
        detail=detail,
        ip_address=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
    )
