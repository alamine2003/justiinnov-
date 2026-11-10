"""Double authentification par code à usage unique (TOTP, RFC 6238).

Tous les comptes y sont soumis : un mot de passe seul, réutilisé ou
intercepté, suffirait à signer une justification au nom d'un autre. Le
secret est généré ici, remis une seule fois au titulaire sous forme de QR
(compatible avec les applications d'authentification usuelles), puis
confirmé par un premier code valide avant que la plateforme ne s'ouvre.

Les gestes qui changent l'état du profil — connexion, enrôlement,
confirmation, réinitialisation — vivent ici aussi, et non dans les vues
(décision 124) : les services ne connaissent ni la requête ni le journal ;
la vue répond et trace.
"""

import base64
import hmac
import io

import pyotp
import qrcode
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from core.regles import RegleViolee

from .authentication import revoquer_jeton

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
    # ``isdigit`` accepte les chiffres arabo-indiens et les exposants, que
    # ``compare_digest`` refuse (TypeError, donc 500) : chiffres ASCII seuls.
    if not (code.isascii() and code.isdigit()):
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


#: Verdicts du second facteur à la connexion (:func:`verifier_a_la_connexion`).
CODE_REQUIS = "requis"
CODE_INVALIDE = "invalide"


def verifier_a_la_connexion(profile, code):
    """Second facteur d'une connexion dont le mot de passe est déjà vérifié.

    ``None`` si la connexion peut se poursuivre — compte non enrôlé, ou
    code accepté —, :data:`CODE_REQUIS` si le compte est enrôlé et que le
    code manque, :data:`CODE_INVALIDE` s'il est faux ou déjà servi. Un
    compte enrôlé présente son code que la politique l'exige ou non : un
    second facteur qu'on a choisi d'activer ne se contourne pas.
    """
    if profile is None or not profile.totp_confirmed:
        return None
    if code in (None, ""):
        return CODE_REQUIS
    # Le code est consommé, pas seulement vérifié : présenté une seconde
    # fois, il est refusé.
    if not consommer_code(profile, code):
        return CODE_INVALIDE
    return None


def enroler(profile):
    """Pose un nouveau secret, pas encore confirmé, et le rend.

    Le secret n'est engagé qu'à la confirmation : rappeler l'enrôlement
    remplace un secret jamais confirmé. Un compte confirmé ne se réenrôle
    pas (``RegleViolee`` sur ``detail``) — le secret actif ne se remplace
    que par une réinitialisation, tracée.
    """
    if profile.totp_confirmed:
        raise RegleViolee(
            "detail",
            _(
                "La double authentification est déjà active sur ce compte. "
                "Demandez sa réinitialisation à un administrateur."
            ),
        )
    secret = generer_secret()
    profile.totp_secret = secret
    # Nouveau secret, nouveaux compteurs : la mémoire anti-rejeu repart.
    profile.totp_last_counter = None
    profile.save(update_fields=["totp_secret", "totp_last_counter", "updated_at"])
    return secret


def confirmer(profile, code):
    """Confirme l'enrôlement par un premier code valide ; faux si le code ne l'est pas.

    Refuse (``RegleViolee`` sur ``detail``) un compte déjà confirmé ou sans
    enrôlement en cours. Le code est consommé et non seulement vérifié : il
    ne doit pas pouvoir resservir à la connexion qui suit.
    """
    if profile.totp_confirmed:
        raise RegleViolee(
            "detail", _("La double authentification est déjà active sur ce compte.")
        )
    if not profile.totp_secret:
        raise RegleViolee(
            "detail", _("Aucun enrôlement en cours : commencez par l'enrôlement.")
        )
    if not consommer_code(profile, code):
        return False
    profile.totp_confirmed_at = timezone.now()
    profile.save(update_fields=["totp_confirmed_at", "updated_at"])
    return True


def reinitialiser(profile):
    """Efface l'enrôlement et révoque le jeton ; rend l'état confirmé d'avant.

    Le compte redevient « à enrôler », et son jeton tombe : qui le détenait
    n'est plus forcément le titulaire.
    """
    etait_confirme = profile.totp_confirmed
    profile.totp_secret = ""
    profile.totp_confirmed_at = None
    profile.totp_last_counter = None
    profile.save(
        update_fields=[
            "totp_secret", "totp_confirmed_at", "totp_last_counter", "updated_at",
        ]
    )
    revoquer_jeton(profile.user)
    return etait_confirme
