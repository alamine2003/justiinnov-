"""Surveillance des erreurs : Sentry, muet tant qu'on ne lui donne pas d'adresse.

Grafana et Prometheus disent **que** la plateforme va mal — un taux d'erreur
qui monte, une file qui s'allonge. Ils ne disent pas **pourquoi** : il faut
alors retrouver la requête dans les journaux du conteneur, et une trace
d'exception y est déjà partie à la rotation. Sentry garde la trace, la pile,
la version du code et la requête qui a échoué, et regroupe les occurrences
d'une même cause. C'est le seul outil de la pile qui réponde à « qu'est-ce
qui a cassé, chez qui, depuis quelle version ».

**Il est désactivé par défaut, et il le reste sans décision explicite.**
Sans ``SENTRY_DSN``, rien n'est installé, aucune requête ne sort, aucune
dépendance réseau n'apparaît. Le renseigner est une décision : une donnée de
la plateforme part alors chez un tiers.

CE QUI NE SORT PAS, ET POURQUOI C'EST RÉGLÉ ICI PLUTÔT QUE PROMIS

JUSTI INNOV suit des dépenses de filiales : qui a déclaré quoi, pour quel
bénéficiaire, avec quelle pièce. Un rapport d'erreur ne doit pas en devenir
une seconde copie, hors du périmètre, hors du journal d'audit, chez un
hébergeur que personne n'a choisi pour cela.

* ``send_default_pii=False`` : ni compte identifié, ni témoins de connexion,
  et la valeur de l'en-tête ``Authorization`` est remplacée par
  ``[Filtered]``. Sentry enverrait tout cela par défaut.
* ``max_request_body_size="never"`` : le corps des requêtes ne part jamais.
  Il porte les montants, les intitulés, les bénéficiaires — et, sur un dépôt
  de justificatif, jusqu'à 20 Mo de pièce.
* ``include_local_variables=False``, **et c'est celui qui a été ajouté après
  mesure**. Sentry joint par défaut les variables locales de chaque cadre de
  pile. Un événement capturé sur un banc portait ainsi
  ``uploaded_by='manager.banc'`` et le ``validated_data`` du sérialiseur —
  soit le compte, le dossier et les montants, précisément ce que les deux
  réglages ci-dessus retenaient. Les promesses ne suffisaient pas : il a
  fallu regarder ce qui partait sur le réseau.
* ``before_send`` retire deux choses que les réglages ne couvrent pas, et
  que seule la lecture d'un événement réel a révélées :

  - **les en-têtes qui portent une adresse** (``X-Forwarded-For``,
    ``X-Real-Ip``, ``X-Forwarded-Host``) et les témoins.
    ``send_default_pii=False`` ne retire que l'adresse vue de la socket ;
    derrière deux mandataires, la vraie adresse du client est dans
    l'en-tête, et elle partait. Sur cette plateforme, elle est une donnée du
    journal d'audit (décision 68) : elle n'a pas à vivre ailleurs ;
  - **la chaîne de requête** (``?search=…``, ``?dossier__number=…``) et
    les témoins joints à la requête. Sentry garde ``query_string`` et
    recopie les paramètres dans ``url`` : une recherche par nom de
    bénéficiaire ou par N°ORDRE partait avec l'événement. Ne reste que le
    chemin, qui dit quelle vue a échoué ;
  - **le compte et l'adresse joints à chaque ligne de journal** par
    ``core.journalisation``. Ce contexte est voulu — c'est lui qui rend un
    incident lisible en local —, mais Sentry recopie les attributs d'un
    enregistrement dans ``extra`` : mesuré, ``extra.compte`` valait
    « manager.banc ». ``requete`` y reste : c'est l'identifiant que
    l'utilisateur cite quand il signale un incident, et il n'identifie
    personne.
* Les fils d'Ariane s'arrêtent aux avertissements : un journal de niveau
  ``INFO`` emporterait le détail des requêtes en cours.
* ``traces_sample_rate`` vaut zéro : la mesure des performances est un second
  flux, plus volumineux que les erreurs, et Prometheus la fait déjà sans rien
  faire sortir de la machine.

Ce qui part, donc : le type et le message de l'exception, sa pile, le chemin
de la requête et sa méthode, la version et l'environnement. De quoi corriger,
pas de quoi reconstituer un dossier.

L'INTERFACE N'EST PAS SURVEILLÉE, ET C'EST UN CHOIX

La politique de sécurité du contenu n'autorise les requêtes que vers
l'origine (``connect-src 'self'``, ``frontend/nginx.conf``). Un client Sentry
dans le navigateur ne pourrait rien envoyer sans l'ouvrir à un domaine tiers
— ou sans un relais côté serveur. Les deux se décident, ils ne se glissent
pas dans un correctif : voir ``deploy/README.md``, « Surveillance des
erreurs ».
"""

import logging
import os

#: Niveau à partir duquel un enregistrement de journal devient un événement.
#: ``ERROR`` : une panne d'infrastructure (``core.exceptions``) en produit un,
#: un avertissement métier non.
NIVEAU_EVENEMENT = logging.ERROR

#: Niveau retenu comme fil d'Ariane, joint à l'événement suivant. Au-dessus de
#: ``INFO`` pour ne pas emporter le détail des requêtes servies.
NIVEAU_FIL = logging.WARNING

#: En-têtes retirés de chaque événement. Les trois premiers portent l'adresse
#: du client — ``send_default_pii=False`` ne retire que celle de la socket,
#: pas celle que les mandataires recopient. Mesuré : elles partaient.
EN_TETES_RETIRES = (
    "x-forwarded-for",
    "x-real-ip",
    "x-forwarded-host",
    "cookie",
    "set-cookie",
)

#: Champs retirés du contexte ``extra``. ``core.journalisation`` attache le
#: compte et l'adresse à **chaque ligne de journal** — c'est voulu, et c'est
#: ce qui rend un incident lisible en local. Sentry recopie ces attributs
#: dans l'événement : mesuré, ``extra.compte`` valait « manager.banc ».
#: ``requete`` reste : c'est l'identifiant que l'utilisateur cite quand il
#: signale un incident (``X-Requete-Id``), et il n'identifie personne.
CHAMPS_RETIRES = ("compte", "ip", "adresse")

#: Éléments gardés de la ligne de commande. Sentry joint ``sys.argv`` de
#: lui-même : le programme et la commande disent lequel des travaux de
#: l'ordonnanceur a échoué, ce qui est précieux. Les **arguments**, eux,
#: portent parfois un nom de compte — ``revoquer_sessions --compte <nom>`` —,
#: et la promesse « aucun nom de compte » ne souffre pas d'exception.
ARGUMENTS_GARDES = 2


def _retirer_ce_qui_identifie(evenement, indice):
    """Dernier filtre avant l'envoi, appliqué à chaque événement.

    Il ne remplace pas les réglages ci-dessus : il ferme ce qu'ils ne
    couvrent pas. Rendre ``None`` supprimerait l'événement ; on le garde, on
    l'allège."""
    requete = evenement.get("request") or {}
    entetes = requete.get("headers")
    if isinstance(entetes, dict):
        requete["headers"] = {
            nom: valeur
            for nom, valeur in entetes.items()
            if nom.lower() not in EN_TETES_RETIRES
        }
    # La chaîne de requête porte ce que l'on cherche — un bénéficiaire, un
    # N°ORDRE — et l'URL de Sentry la recopie : seul le chemin reste.
    if "query_string" in requete:
        requete["query_string"] = ""
    url = requete.get("url")
    if isinstance(url, str):
        requete["url"] = url.split("?", 1)[0]
    requete.pop("cookies", None)
    contexte = evenement.get("extra")
    if isinstance(contexte, dict):
        for champ in CHAMPS_RETIRES:
            contexte.pop(champ, None)
        arguments = contexte.get("sys.argv")
        if isinstance(arguments, list) and len(arguments) > ARGUMENTS_GARDES:
            contexte["sys.argv"] = arguments[:ARGUMENTS_GARDES] + ["…"]
    return evenement


def configurer_la_surveillance(*, en_test=False):
    """Installe Sentry si une adresse est donnée. Rend ce qui a été retenu.

    Le retour sert aux tests et au diagnostic ; il ne contient jamais
    l'adresse elle-même, qui porte une clé.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn or en_test:
        return {"actif": False, "raison": "test" if en_test else "aucune adresse"}

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:  # pragma: no cover - dépend de l'installation
        logging.getLogger(__name__).error(
            "SENTRY_DSN est renseigné mais sentry-sdk n'est pas installé : "
            "la surveillance des erreurs reste éteinte."
        )
        return {"actif": False, "raison": "sentry-sdk absent"}

    reglages = {
        "dsn": dsn,
        "environment": os.environ.get("SENTRY_ENVIRONMENT", "production"),
        # La version du code, pour savoir quelle livraison a introduit une
        # erreur. `IMAGE_TAG` est déjà l'étiquette des images (deploy/).
        "release": os.environ.get("SENTRY_RELEASE") or os.environ.get("IMAGE_TAG") or None,
        "send_default_pii": False,
        "max_request_body_size": "never",
        # Sans cela, chaque cadre de pile emporte ses variables locales :
        # mesuré, un dépôt raté envoyait le nom du déposant et les données
        # validées du sérialiseur.
        "include_local_variables": False,
        "before_send": _retirer_ce_qui_identifie,
        "traces_sample_rate": float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        "integrations": [
            DjangoIntegration(),
            LoggingIntegration(level=NIVEAU_FIL, event_level=NIVEAU_EVENEMENT),
        ],
    }
    sentry_sdk.init(**reglages)
    return {
        "actif": True,
        "environnement": reglages["environment"],
        "version": reglages["release"],
        "echantillon_traces": reglages["traces_sample_rate"],
    }
