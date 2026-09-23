"""Transport de courrier coupé : rien ne part, et les journaux le disent.

Posé par ``config.settings.choisir_email_backend`` quand l'envoi est coupé
(``DJANGO_EMAIL_ENABLED`` absent ou à ``0``, décision 88). Les deux chemins
d'envoi de l'application — notifications et rapport périodique — vérifient
eux-mêmes ``settings.EMAIL_ENABLED`` et n'arrivent jamais jusqu'ici ; ce
transport est le filet pour tout le reste : un ``send_mail`` lancé depuis
un shell, un envoi ajouté plus tard sans passer par l'interrupteur.

Il rend ``0`` sans lever : un envoi refusé n'a pas à faire échouer l'action
qui l'a déclenché. Il ne prétend pas non plus avoir envoyé — ``0`` message
parti, c'est ce que Django attend d'un transport qui n'a rien transmis.
"""

import logging

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class CourrierCoupe(BaseEmailBackend):
    def send_messages(self, email_messages):
        nombre = len(list(email_messages or []))
        if nombre:
            logger.warning(
                "Courrier coupé (DJANGO_EMAIL_ENABLED=0) : %d e-mail(s) non envoyé(s).",
                nombre,
            )
        return 0
