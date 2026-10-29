"""Le schéma ``bi`` du BI de pilotage (décision 122).

Grafana lit des **vues** PostgreSQL, sous un rôle qui ne voit qu'elles
(``deploy/creer_role_bi.sql``). Elles vivent dans ``vues.sql``, un gabarit
dont les jetons (entre doubles arobases) viennent d'ici, donc du code : ensembles de statuts,
libellés des choix, seuils par défaut, fuseau du serveur. Changer un statut
ou un libellé dans un modèle change les vues au prochain ``migrate``.

Les vues ne sont pas des migrations : elles sont **retirées avant** chaque
``migrate`` (``pre_migrate``) et **reposées après** (``post_migrate``). Une
vue qui lit une colonne bloquerait sinon toute migration qui la modifie,
et une vue figée dans une migration divergerait de ce que fait le code.
Le schéma lui-même reste en place : les droits du rôle BI y sont attachés,
et ``ALTER DEFAULT PRIVILEGES`` les reporte sur chaque vue recréée.
"""

import logging
from pathlib import Path

from django.conf import settings
from django.utils import translation

logger = logging.getLogger(__name__)

GABARIT = Path(__file__).with_name("vues.sql")
SCHEMA = "bi"


def _litteral(valeur):
    return "'" + str(valeur).replace("'", "''") + "'"


def _liste(valeurs):
    return ", ".join(_litteral(v) for v in sorted(str(v) for v in valeurs))


def _cas(choix):
    """``CASE code WHEN … THEN 'libellé' … ELSE code END``, en français."""
    with translation.override("fr"):
        branches = " ".join(
            f"WHEN {_litteral(code)} THEN {_litteral(libelle)}" for code, libelle in choix
        )
    return f"CASE code {branches} ELSE code END"


def jetons():
    """Valeurs à substituer dans le gabarit, tirées des modèles."""
    import json

    from accounts.models import Role
    from budget.aggregates import SEUIL_D_ALERTE_PAR_DEFAUT
    from budget.models import CONSOLIDATION_CURRENCY
    from core.models import WorkflowConfiguration
    from core.statuts import CONSUMING_STATUSES, ENGAGING_STATUSES, Status
    from expenses.models import AuditLog, Beneficiary, Expense, Proof
    from expenses.synthese_audit import SENSIBLES_CIRCUIT

    champ = WorkflowConfiguration._meta.get_field
    return {
        "FUSEAU_SERVEUR": settings.TIME_ZONE,
        "DEVISE_CONSOLIDATION": CONSOLIDATION_CURRENCY,
        "ENGAGES": _liste(ENGAGING_STATUSES),
        "CONSOMMES": _liste(CONSUMING_STATUSES),
        "BROUILLON": Status.DRAFT,
        "CLOTURE": Status.CLOSED,
        "PIECES_INUTILISABLES": _liste(
            [Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED]
        ),
        "SEUILS_DEFAUT": json.dumps(champ("alert_thresholds").default()),
        "SEUIL_PAR_DEFAUT": str(SEUIL_D_ALERTE_PAR_DEFAUT),
        "FACTEUR_DEFAUT": str(champ("unusual_expense_factor").default),
        "ACTIONS_SENSIBLES": _liste(SENSIBLES_CIRCUIT),
        "CASE_STATUT": _cas(Status.choices),
        "CASE_PAIEMENT": _cas(Expense.PaymentMethod.choices),
        "CASE_BENEFICIAIRE": _cas(Beneficiary.Kind.choices),
        "CASE_TYPE_PIECE": _cas(Proof.Kind.choices),
        "CASE_ETAT_PIECE": _cas(Proof.ProofStatus.choices),
        "CASE_ACTION": _cas(AuditLog.Action.choices),
        "CASE_ROLE": _cas(Role.choices),
    }


def sql_des_vues():
    """Le gabarit, jetons remplacés. Un jeton oublié est une erreur."""
    sql = GABARIT.read_text(encoding="utf-8")
    for nom, valeur in jetons().items():
        sql = sql.replace(f"@@{nom}@@", valeur)
    if "@@" in sql:
        reste = sql[sql.index("@@"):].split("@@")[1]
        raise ValueError(f"Jeton sans valeur dans vues.sql : @@{reste}@@")
    return sql


#: Retire vues et fonctions du schéma, sans toucher au schéma ni à ses
#: droits. CASCADE : une vue qui en lit une autre part avec elle.
RETRAIT = f"""
DO $retrait$
DECLARE objet record;
BEGIN
  FOR objet IN SELECT viewname FROM pg_views WHERE schemaname = '{SCHEMA}' LOOP
    EXECUTE format('DROP VIEW IF EXISTS {SCHEMA}.%I CASCADE', objet.viewname);
  END LOOP;
  FOR objet IN
    SELECT p.oid::regprocedure AS signature
      FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace
     WHERE n.nspname = '{SCHEMA}'
  LOOP
    EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', objet.signature);
  END LOOP;
END
$retrait$;
"""


def _postgresql(connection):
    return connection.vendor == "postgresql"


def retirer_les_vues(connection):
    if not _postgresql(connection):
        return
    with connection.cursor() as curseur:
        curseur.execute(RETRAIT)


def installer_les_vues(connection):
    """Repose toutes les vues, dans une transaction : tout ou rien.

    Une vue qui ne se crée pas ne doit pas empêcher l'application de
    démarrer — ``migrate`` tourne à chaque démarrage du conteneur : le BI
    reste alors sans vues, l'erreur part au journal (et à Sentry), et
    l'application, elle, sert. Les tests du BI échouent, eux, sans appel.
    """
    if not _postgresql(connection):
        return
    from django.db import DatabaseError, transaction

    try:
        with transaction.atomic(using=connection.alias), connection.cursor() as curseur:
            curseur.execute(RETRAIT)
            curseur.execute(sql_des_vues())
    except DatabaseError:
        logger.exception("Vues du BI (schéma bi) non reposées : le BI est sans données.")
