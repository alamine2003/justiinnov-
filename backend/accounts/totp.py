"""Double authentification par code à usage unique (TOTP, RFC 6238).

Tous les comptes y sont soumis : un mot de passe seul, réutilisé ou
intercepté, suffirait à signer une justification au nom d'un autre. Le
secret est généré ici, remis une seule fois au titulaire sous forme de QR
(compatible avec les applications d'authentification usuelles), puis
confirmé par un premier code valide avant que la plateforme ne s'ouvre.
"""

import base64
import hmac
import io

import pyotp
import qrcode
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

#: Tolérance d'horloge : le code précédent et le suivant sont acceptés, soit
#: trente secondes de part et d'autre. Au-delà, un poste mal réglé bloque
#: le titulaire ; en deçà, un code intercepté vaudrait trop longtemps.
FENETRE_DE_VALIDITE = 1


def generer_secret():
    """Nouveau secret aléatoire, encodé en base32 comme l'attend l'application."""
    return pyotp.random_base32()


def uri_d_enrolement(secret, libelle):
    """URI ``otpauth://`` à encoder dans le QR d'enrôlement.

    Le libellé est l'adresse e-mail du titulaire, que l'application affiche
    à côté de l'émetteur : on la lit sur le téléphone sans ambiguïté.
    """
    return pyotp.TOTP(secret).provisioning_uri(
        name=libelle, issuer_name=settings.TOTP_ISSUER
    )


def qr_png_base64(uri):
    """QR de l'URI d'enrôlement, en PNG encodé en base64 pour l'interface."""
    image = qrcode.make(uri)
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")
    return base64.b64encode(tampon.getvalue()).decode("ascii")


def compteur_du_code(secret, code):
    """Compteur de temps (RFC 6238) auquel le code correspond, ou ``None``.

    Un code absent, vide ou mal formé vaut ``None``, sans exception :
    l'appelant répond de la même façon quel que soit le défaut. Le compteur
    est ce qui rend le code unique : deux codes valides à des instants
    différents portent des compteurs différents, et c'est lui que le profil
    mémorise pour refuser un rejeu.
    """
    if not secret or code is None:
        return None
    code = "".join(str(code).split())
    if not code.isdigit():
        return None
    generateur = pyotp.TOTP(secret)
    maintenant = timezone.now()
    for decalage in range(-FENETRE_DE_VALIDITE, FENETRE_DE_VALIDITE + 1):
        if hmac.compare_digest(code, generateur.at(maintenant, decalage)):
            return generateur.timecode(maintenant) + decalage
    return None


def consommer_code(profile, code):
    """Accepte le code une seule fois : vrai s'il est valide et jamais servi.

    Le compteur accepté est écrit sur le profil par une mise à jour
    conditionnelle — seulement s'il dépasse le dernier mémorisé — pour que
    deux requêtes simultanées portant le même code ne passent pas toutes
    les deux. Un code plus ancien que le dernier accepté est refusé aussi,
    même s'il est encore dans la fenêtre : c'est la règle de la RFC 6238.
    """
    compteur = compteur_du_code(profile.totp_secret, code)
    if compteur is None:
        return False
    accepte = (
        type(profile).objects.filter(pk=profile.pk)
        .filter(Q(totp_last_counter__isnull=True) | Q(totp_last_counter__lt=compteur))
        .update(totp_last_counter=compteur)
    )
    if not accepte:
        return False
    profile.totp_last_counter = compteur
    return True
