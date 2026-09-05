"""Droits dérivés du rôle du profil : la matrice des capacités.

Chaque action que l'API permet — créer un compte, modifier une enveloppe,
supprimer un brouillon, mettre en contrôle, exporter — est une **capacité**
nommée (``CAPACITES``). Une vue déclare la capacité que chaque écriture
exige (``write_capability``, ``action_write_capabilities``), une lecture
réservée déclare la sienne (``read_capability``, ``action_read_capabilities``),
et ``RolePermission`` tranche à chaque requête.

Les rôles qui portent une capacité viennent de la **configuration**
(``WorkflowConfiguration.capability_roles``, modifiable par les
administrateurs dans « Configuration › Permissions »), sinon du défaut
inscrit ici (décision 43). Deux verrous ne se configurent pas, parce qu'ils
tiennent la raison d'être de l'application :

- le super administrateur a toujours toutes les capacités (``fixes``) ;
- le pays ne contrôle jamais ce qu'il déclare, n'administre rien (comptes,
  configuration, journal d'audit, ouverture ou modification d'un pays) et ne
  fixe pas ses propres enveloppes (``verrouillees``) ; les comptes et la
  configuration ne s'ouvrent qu'aux administrateurs, jamais à un rôle
  restrictible à des pays, qui pourrait sinon se créer un administrateur.

Décrire les rôles ailleurs qu'ici les ferait diverger de ce qui est
réellement appliqué : ``/api/permissions/`` et ``/api/me/`` lisent cette
table, la configuration ne fait que la remplir.
"""

import json
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.models import WorkflowConfiguration
from core.regles import PermissionRefusee

from .models import Role


@dataclass(frozen=True)
class Access:
    """Vue immuable des droits d'un utilisateur pour la requête en cours."""

    role: str
    country_ids: list | None  # ``None`` = tous les pays
    #: Équipes auxquelles un manager est restreint ; ``None`` = pas de
    #: restriction par équipe (autre rôle, ou manager sans équipe).
    team_ids: list | None = None
    #: Nom du compte, immuable (décision 27) : c'est sur lui que les quatre
    #: yeux et la propriété d'un brouillon se jugent. Vide pour un accès
    #: construit sans compte (une commande qui lit comme le siège).
    username: str = ""

    @property
    def has_global_scope(self):
        return self.country_ids is None


#: Attribut posé sur l'instance utilisateur pour mémoriser ses droits.
_ATTRIBUT_MEMO = "_acces_memorise"
_ABSENT = object()


def get_access(user):
    """Droits de l'utilisateur, ou ``None`` s'il n'en a aucun.

    Un compte sans profil — le superutilisateur d'amorçage, un compte hérité —
    n'a **aucun** accès à l'API, fût-il superutilisateur Django : le rôle et
    le périmètre viennent du profil, jamais des drapeaux du compte.

    Le résultat est mémorisé sur l'instance utilisateur, donc pour la durée de
    la requête : permission, filtrage du queryset et revalidation de l'écriture
    y font chacun appel, et chaque appel coûtait deux requêtes SQL.
    """
    if user is None or not user.is_authenticated:
        return None
    memo = getattr(user, _ATTRIBUT_MEMO, _ABSENT)
    if memo is not _ABSENT:
        return memo
    # L'accesseur inverse d'un OneToOne lève une exception dérivant
    # d'AttributeError : ``getattr`` avec défaut est donc sûr.
    profile = getattr(user, "profile", None)
    access = (
        None
        if profile is None
        else Access(
            role=profile.role,
            country_ids=profile.country_ids(),
            team_ids=profile.team_ids(),
            username=user.username,
        )
    )
    setattr(user, _ATTRIBUT_MEMO, access)
    return access


# --- Rôles structurels ------------------------------------------------------
# Ils décrivent l'organisation, pas un droit : ils ne se configurent pas.

#: Le pays : le manager, seul rôle qui déclare. C'est lui que l'on prévient
#: quand une pièce manque ou qu'un dossier lui revient (décision 20), et
#: lui seul que le cloisonnement par équipe concerne.
COUNTRY_ROLES = frozenset({Role.MANAGER})


# --- Matrice des capacités ---------------------------------------------------

_ADMINISTRATEURS = frozenset({Role.SUPER_ADMIN, Role.ADMIN})
_DIRECTION = frozenset({Role.SUPER_ADMIN})
_SIEGE = frozenset({Role.SUPER_ADMIN, Role.ADMIN, Role.DF, Role.DM})
_CONTROLE = frozenset({Role.SUPER_ADMIN, Role.ADMIN, Role.DF})
_PAYS_ET_ADMINISTRATEURS = frozenset({Role.SUPER_ADMIN, Role.ADMIN, Role.MANAGER})
_TOUS = frozenset(Role)


@dataclass(frozen=True)
class Capacite:
    """Une action de l'API, ses rôles par défaut et ses verrous."""

    key: str
    groupe: str
    label: str
    description: str
    #: Rôles qui la portent tant que la configuration n'en dit pas autrement.
    defaut: frozenset
    #: Rôles qui ne peuvent jamais la recevoir, quelle que soit la
    #: configuration : la case reste vide et grisée.
    verrouillees: frozenset = frozenset()
    #: Rôles qui l'ont toujours : le super administrateur, partout — sinon
    #: une configuration malheureuse n'aurait plus personne pour la défaire.
    fixes: frozenset = _DIRECTION
    #: Rôles qui peuvent modifier cette ligne de la matrice. La RH règle
    #: tout, sauf ce qui touche à l'argent : attribuer, arbitrer, tenir les
    #: taux se règlent par la direction seule (« la RH tient les comptes,
    #: pas l'argent »).
    reglable_par: frozenset = _ADMINISTRATEURS

    def roles_effectifs(self, choix):
        """Rôles retenus pour ``choix`` (configuration), verrous appliqués.

        Une valeur mal formée — glissée par l'admin Django ou un shell — vaut
        le défaut : une matrice qui lèverait une exception fermerait toute
        l'API, y compris la route qui permet de la réparer.
        """
        if isinstance(choix, (list, tuple, set, frozenset)):
            roles = {role for role in choix if role in _TOUS}
        else:
            roles = set(self.defaut)
        return frozenset((roles | self.fixes) - (self.verrouillees - self.fixes))


GROUPE_ADMINISTRATION = _("Comptes et administration")
GROUPE_REFERENTIEL = _("Référentiel")
GROUPE_ENVELOPPES = _("Enveloppes")
GROUPE_DECLARATION = _("Déclaration")
GROUPE_CONTROLE = _("Contrôle")
GROUPE_FICHIERS = _("Fichiers")

#: Le pays ne contrôle pas ce qu'il déclare, n'administre rien et n'arbitre
#: pas ses propres enveloppes : ces cases ne s'ouvrent pas.
_JAMAIS_LE_PAYS = COUNTRY_ROLES

#: Les comptes ne s'administrent que depuis un rôle global : un DM ou un DF
#: restreint à des pays qui créerait des comptes pourrait se donner un
#: administrateur, donc la configuration.
_JAMAIS_HORS_ADMINISTRATEURS = _TOUS - _ADMINISTRATEURS

#: Matrice des capacités, source unique, dans l'ordre où l'interface les
#: présente. Les défauts sont les décisions du produit : le DM et le DF
#: n'administrent rien, les enveloppes sont à la direction, les fichiers
#: aux administrateurs.
CAPACITES = (
    Capacite(
        "users.read", GROUPE_ADMINISTRATION,
        _("Lire les comptes"),
        _("Consulter la liste des comptes, leurs rôles et leurs périmètres."),
        _ADMINISTRATEURS, verrouillees=_JAMAIS_HORS_ADMINISTRATEURS,
    ),
    Capacite(
        "users.create", GROUPE_ADMINISTRATION,
        _("Créer un compte"),
        _("Ouvrir un compte et lui donner un rôle et un périmètre."),
        _ADMINISTRATEURS, verrouillees=_JAMAIS_HORS_ADMINISTRATEURS,
    ),
    Capacite(
        "users.update", GROUPE_ADMINISTRATION,
        _("Modifier un compte"),
        _(
            "Changer le rôle, le périmètre, activer ou désactiver, "
            "réinitialiser la double authentification."
        ),
        _ADMINISTRATEURS, verrouillees=_JAMAIS_HORS_ADMINISTRATEURS,
    ),
    Capacite(
        "configuration.manage", GROUPE_ADMINISTRATION,
        _("Configurer la plateforme"),
        _(
            "Lire la configuration, régler la politique du circuit et cette "
            "matrice. Réservé aux administrateurs, sans exception."
        ),
        _ADMINISTRATEURS, verrouillees=_TOUS - _ADMINISTRATEURS, fixes=_ADMINISTRATEURS,
    ),
    Capacite(
        "audit.read", GROUPE_ADMINISTRATION,
        _("Journal d'audit"),
        _("Relire la trace des actions sensibles, décisions du siège comprises."),
        _ADMINISTRATEURS, verrouillees=_JAMAIS_LE_PAYS,
    ),
    Capacite(
        "history.read", GROUPE_ADMINISTRATION,
        _("Historique du référentiel"),
        _("Lire qui a modifié quoi dans le référentiel, sur son périmètre."),
        _SIEGE,
    ),
    Capacite(
        "countries.create", GROUPE_REFERENTIEL,
        _("Ouvrir un pays ou un manager"),
        _("Créer un pays parmi les filiales du groupe, ou un manager."),
        _ADMINISTRATEURS, verrouillees=_JAMAIS_LE_PAYS,
    ),
    Capacite(
        "countries.update", GROUPE_REFERENTIEL,
        _("Modifier un pays ou un manager"),
        _("Changer la devise, le fuseau, les managers ; activer ou désactiver."),
        _ADMINISTRATEURS, verrouillees=_JAMAIS_LE_PAYS,
    ),
    Capacite(
        "referentiel.create", GROUPE_REFERENTIEL,
        _("Créer dans le référentiel"),
        _("Ajouter une équipe, un centre de coûts, un projet, un intitulé, une catégorie, un bénéficiaire."),
        _ADMINISTRATEURS,
    ),
    Capacite(
        "referentiel.update", GROUPE_REFERENTIEL,
        _("Modifier le référentiel"),
        _("Renommer, rattacher, activer ou désactiver une entité du référentiel."),
        _ADMINISTRATEURS,
    ),
    Capacite(
        "budgets.create", GROUPE_ENVELOPPES,
        _("Attribuer une enveloppe"),
        _("Créer une enveloppe annuelle ou une sous-enveloppe."),
        _DIRECTION, verrouillees=_JAMAIS_LE_PAYS, reglable_par=_DIRECTION,
    ),
    Capacite(
        "budgets.update", GROUPE_ENVELOPPES,
        _("Modifier une enveloppe"),
        _(
            "Changer le montant, la politique de dépassement, désactiver ; "
            "valider une dépense qui dépasse son enveloppe."
        ),
        _DIRECTION, verrouillees=_JAMAIS_LE_PAYS, reglable_par=_DIRECTION,
    ),
    Capacite(
        "reallocations.request", GROUPE_ENVELOPPES,
        _("Demander une réallocation"),
        _("Proposer un transfert entre deux enveloppes."),
        _DIRECTION, reglable_par=_DIRECTION,
    ),
    Capacite(
        "reallocations.decide", GROUPE_ENVELOPPES,
        _("Arbitrer une réallocation"),
        _("Approuver ou refuser un transfert. Jamais le sien."),
        _DIRECTION, verrouillees=_JAMAIS_LE_PAYS, reglable_par=_DIRECTION,
    ),
    Capacite(
        "rates.manage", GROUPE_ENVELOPPES,
        _("Tenir les taux de change"),
        _("Ajouter ou corriger un taux vers la devise de consolidation."),
        _DIRECTION, verrouillees=_JAMAIS_LE_PAYS, reglable_par=_DIRECTION,
    ),
    Capacite(
        "expenses.create", GROUPE_DECLARATION,
        _("Saisir"),
        _("Ouvrir un dossier, y ajouter des lignes de dépense."),
        _PAYS_ET_ADMINISTRATEURS,
    ),
    Capacite(
        "expenses.update", GROUPE_DECLARATION,
        _("Modifier un brouillon"),
        _("Corriger un dossier ou une ligne tant qu'ils ne sont pas soumis."),
        _PAYS_ET_ADMINISTRATEURS,
    ),
    Capacite(
        "expenses.delete", GROUPE_DECLARATION,
        _("Supprimer un brouillon"),
        _("Retirer un dossier ou une ligne jamais soumis. Son auteur seulement."),
        _PAYS_ET_ADMINISTRATEURS,
    ),
    Capacite(
        "proofs.upload", GROUPE_DECLARATION,
        _("Déposer une pièce"),
        _("Joindre un justificatif, ou le remplacer, jusqu'à la clôture."),
        _PAYS_ET_ADMINISTRATEURS,
    ),
    Capacite(
        "dossiers.submit", GROUPE_DECLARATION,
        _("Soumettre"),
        _("Déclarer un dossier : ses lignes partent avec lui, sans retour."),
        _PAYS_ET_ADMINISTRATEURS,
    ),
    Capacite(
        "expenses.review", GROUPE_CONTROLE,
        _("Mettre en contrôle"),
        _("Prendre un dossier soumis en contrôle : le DM prépare, le DF tranche."),
        _SIEGE, verrouillees=_JAMAIS_LE_PAYS,
    ),
    Capacite(
        "expenses.validate", GROUPE_CONTROLE,
        _("Justifier ou refuser"),
        _("Constater qu'une pièce couvre une dépense, ou l'absence de preuve."),
        _CONTROLE, verrouillees=_JAMAIS_LE_PAYS,
    ),
    Capacite(
        "expenses.close", GROUPE_CONTROLE,
        _("Clôturer"),
        _("Déclarer l'affaire terminée une fois chaque ligne justifiée."),
        _CONTROLE, verrouillees=_JAMAIS_LE_PAYS,
    ),
    Capacite(
        "proofs.review", GROUPE_CONTROLE,
        _("Contrôler une pièce"),
        _("Valider, rejeter ou signaler incomplet un justificatif."),
        _CONTROLE, verrouillees=_JAMAIS_LE_PAYS,
    ),
    Capacite(
        "dossiers.reopen", GROUPE_CONTROLE,
        _("Rouvrir un dossier"),
        _("Renvoyer un dossier déclaré au pays pour demander des comptes, motif à l'appui."),
        _ADMINISTRATEURS, verrouillees=_JAMAIS_LE_PAYS,
    ),
    Capacite(
        "data.export", GROUPE_FICHIERS,
        _("Exporter"),
        _("Télécharger le registre en Excel, CSV, Word ou PDF."),
        _ADMINISTRATEURS,
    ),
    Capacite(
        "data.import", GROUPE_FICHIERS,
        _("Importer"),
        _("Charger un classeur de dépenses en brouillons."),
        _ADMINISTRATEURS,
    ),
)

CAPACITES_PAR_CLE = {capacite.key: capacite for capacite in CAPACITES}

#: Dernière matrice résolue, avec l'empreinte du choix dont elle vient : une
#: liste de cent lignes interroge la matrice cent fois, et ``charger()``
#: rend une instance neuve à chaque appel (dépicklée du cache), donc un
#: mémo sur l'instance ne servirait qu'au sérialiseur qui la garde. Un
#: choix modifié — empreinte différente — la recalcule.
_MEMO_MATRICE = {"empreinte": None, "matrice": None}


def matrice_effective(configuration=None):
    """Capacité → rôles, telle qu'appliquée : configuration puis verrous.

    Les verrous s'appliquent ici, et non seulement à l'enregistrement : une
    valeur glissée en base par un autre chemin ne rend pas au pays le droit
    de se justifier lui-même.
    """
    if configuration is None:
        configuration = WorkflowConfiguration.charger()
    choix = configuration.capability_roles
    if not isinstance(choix, dict):
        choix = {}
    empreinte = json.dumps(choix, sort_keys=True, default=str)
    if _MEMO_MATRICE["empreinte"] != empreinte:
        _MEMO_MATRICE["matrice"] = {
            capacite.key: capacite.roles_effectifs(choix.get(capacite.key))
            for capacite in CAPACITES
        }
        _MEMO_MATRICE["empreinte"] = empreinte
    return _MEMO_MATRICE["matrice"]


def roles_pour(cle, configuration=None):
    """Rôles qui portent la capacité ``cle``."""
    return matrice_effective(configuration)[cle]


def capacites_du_role(role, configuration=None):
    """Droits d'un rôle, sous la forme attendue par le frontend (``/api/me/``)."""
    return {cle: role in roles for cle, roles in matrice_effective(configuration).items()}


def exiger_la_capacite(cle, acteur, configuration=None):
    """Refus (``PermissionRefusee``) si l'acteur n'a pas la capacité.

    Une vue l'a déjà vérifiée par ``RolePermission`` ; un service la
    revérifie pour que l'import et les commandes ne contournent pas la
    matrice.
    """
    if acteur is None or acteur.role not in roles_pour(cle, configuration):
        raise PermissionRefusee(str(RolePermission.message))


class RolePermission(BasePermission):
    """Autorise la requête selon la capacité que la vue déclare.

    - lecture : ``view.read_capability`` (libre si non déclarée — le
      cloisonnement se fait sur le queryset) ;
    - écriture : ``view.write_capability``, qui doit être déclarée — une vue
      qui l'oublie est en lecture seule plutôt qu'ouverte à tous ;
    - ``view.action_write_capabilities`` et ``view.action_read_capabilities``
      surchargent par action. Indispensable : créer un compte et le modifier,
      valider une dépense et la saisir relèvent de capacités différentes
      alors qu'il s'agit de la même vue.
    """

    message = _("Votre rôle ne permet pas cette action.")

    @staticmethod
    def capacite_requise(view, method):
        """Clé de capacité exigée par la vue pour cette méthode, ou ``None``."""
        action = getattr(view, "action", None)
        if method in SAFE_METHODS:
            par_action = getattr(view, "action_read_capabilities", {})
            if action in par_action:
                return par_action[action]
            return getattr(view, "read_capability", None)
        par_action = getattr(view, "action_write_capabilities", {})
        if action in par_action:
            return par_action[action]
        return getattr(view, "write_capability", None)

    def has_permission(self, request, view):
        access = get_access(request.user)
        if access is None:
            return False
        cle = self.capacite_requise(view, request.method)
        if cle is None:
            return request.method in SAFE_METHODS
        return access.role in roles_pour(cle)
