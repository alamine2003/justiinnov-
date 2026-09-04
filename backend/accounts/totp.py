"""Double authentification par code à usage unique (TOTP, RFC 6238).

Tous les comptes y sont soumis : un mot de passe seul, réutilisé ou
intercepté, suffirait à signer une justification au nom d'un autre. Le
secret est généré ici, remis une seule fois au titulaire sous forme de QR
(compatible avec les applications d'authentification usuelles), puis
confirmé par un premier code valide avant que la plateforme ne s'ouvre.
"""

import base64
import io

import pyotp
import qrcode
from django.conf import settings

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


def verifier_code(secret, code):
    """Le code présenté correspond-il au secret, à la fenêtre près ?

    Un code absent, vide ou mal formé vaut faux, sans exception : l'appelant
    répond de la même façon quel que soit le défaut.
    """
    if not secret or code is None:
        return False
    code = "".join(str(code).split())
    if not code.isdigit():
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=FENETRE_DE_VALIDITE)
