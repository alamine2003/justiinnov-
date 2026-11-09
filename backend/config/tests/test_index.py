"""La carte des index : chaque index sert une requête nommée, et la sert encore.

Décision 123. Un index se paie à chaque écriture ; il ne se justifie que par
une requête réelle qu'il accélère. La décision 72 l'a montré : un index
« au cas où » sur les dépenses n'était jamais choisi par le planificateur, et
se serait pourtant payé à chaque ligne saisie. D'où deux règles, gardées
ici dans les deux sens :

- **tout index déclaré dans un modèle figure sur la carte**, avec la requête
  qu'il sert et l'endroit du code qui l'émet — un index sans requête se
  retire, il ne s'accumule pas ;
- **chaque requête de la carte emprunte bien son index** : un ``EXPLAIN``,
  parcours séquentiel coupé (sur les quelques lignes d'une base de test,
  Postgres le préférerait toujours et le plan ne dirait rien de ce qui se
  passe à des centaines de milliers de lignes), doit le nommer. Changer une
  requête, un tri ou un index sans l'autre ne casse rien de visible — la
  réponse reste juste et redevient lente, en silence ; c'est ce test qui le
  dit.

S'ajoute une garde de forme : aucun filtre de période ne s'écrit en
``__date`` sur une colonne horodatée — Postgres ne peut pas s'aider d'un
index pour l'expression ``(colonne AT TIME ZONE …)::date`` ; on écrit des
bornes (``core.periodes``).

Les mesures qui justifient chaque index ajouté sont dans
``docs/model-de-donnees.md`` (décisions 72 et 123).
"""

import ast
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from django.apps import apps
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase

from budget.models import Budget
from core.models import ChangeLog
from core.periodes import entre_les_jours
from core.statuts import Status
from expenses.models import (
    AuditLog,
    Dossier,
    ElementSupprime,
    Expense,
    FichierASupprimer,
    Proof,
)
from notifications.models import Notification

APPLICATIONS = ("core", "accounts", "notifications", "budget", "expenses", "reporting")
RACINE = Path(__file__).resolve().parents[2]

JOUR = date(2026, 3, 15)
INSTANT = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def trente_jours():
    return entre_les_jours("created_at", JOUR - timedelta(days=29), JOUR)


#: Nom de l'index → (requête qui l'emprunte, où le code l'émet).
#: Une requête est une fonction sans argument : les modèles ne se lisent
#: qu'une fois l'application prête. Un comptage ou un agrégat n'a pas de
#: tri : ``order_by()`` le dit, comme ``count()`` le fait dans le code.
CARTE = {
    # Historique du référentiel (``ChangeLog``) : il grossit d'une entrée par
    # connexion, déconnexion et échec.
    "core_changelog_cree_idx": (
        lambda: ChangeLog.objects.filter(trente_jours()),
        "/api/history/?debut=&fin= (accounts/referentiel.py), synthèse d'audit",
    ),
    "core_changelog_pays_cree_idx": (
        lambda: ChangeLog.objects.filter(country_id=1).order_by("-created_at")[:25],
        "/api/history/?country= (accounts/referentiel.py)",
    ),
    "core_changelog_entite_idx": (
        lambda: ChangeLog.objects.filter(model_name="project", object_id=1),
        "historique d'un projet (expenses/historique.py)",
    ),
    # Enveloppes.
    "budget_pays_annee_actif": (
        lambda: Budget.objects.filter(country_id=1, year=2026, is_active=True).order_by(),
        "enveloppes d'un pays pour l'exercice (reporting/scope.py, expenses/services.py)",
    ),
    # Dossiers.
    "dossier_pays_statut": (
        lambda: Dossier.objects.filter(country_id=1, status=Status.SUBMITTED).order_by(),
        "liste des dossiers d'un pays, alertes de preuve (reporting/alerts.py)",
    ),
    "dossier_date": (
        lambda: Dossier.objects.filter(date__range=(date(2026, 1, 1), date(2026, 12, 31))),
        "?exercice= (expenses/filtres.py)",
    ),
    # Lignes de dépense.
    "depense_enveloppe_statut": (
        lambda: Expense.objects.filter(
            budget_id=1, status__in=[Status.SUBMITTED, Status.JUSTIFIED]
        ).order_by(),
        "consommation d'une enveloppe (budget/aggregates.py)",
    ),
    "depense_pays_statut_date": (
        lambda: Expense.objects.filter(
            country_id=1, status=Status.JUSTIFIED, date__range=(INSTANT - timedelta(days=30), INSTANT)
        ).order_by(),
        "périmètre et période d'un pays (reporting/scope.py, reporting/alerts.py)",
    ),
    "depense_tri_liste": (
        lambda: Expense.objects.order_by(*Expense._meta.ordering)[:25],
        "/api/expenses/ et le registre (expenses/views.py), décision 72",
    ),
    # Pièces.
    "piece_dossier_statut": (
        lambda: Proof.objects.filter(dossier_id=1, status="received"),
        "pièces d'un dossier par état (expenses/views.py, reporting/alerts.py)",
    ),
    "fichier_a_supprimer_idx": (
        lambda: FichierASupprimer.objects.filter(attempted_at=INSTANT, deleted_at__isnull=True),
        "effacement des fichiers en attente (expenses/stockage.py)",
    ),
    # Journal d'audit.
    "expenses_au_object__ba7244_idx": (
        lambda: AuditLog.objects.filter(object_type="Dossier", object_id=1).order_by(),
        "trace d'un objet (expenses/historique.py, expenses/workflow.py)",
    ),
    "audit_date": (
        lambda: AuditLog.objects.filter(trente_jours()),
        "/api/audit/?debut=&fin= (expenses/filtres.py), synthèse d'audit",
    ),
    "audit_pays_date": (
        lambda: AuditLog.objects.filter(country_id=1).order_by("-created_at")[:25],
        "/api/audit/?country= et le périmètre d'un manager (expenses/views.py)",
    ),
    "audit_utilisateur": (
        lambda: AuditLog.objects.filter(user="recette.tg.manager").order_by(),
        "/api/audit/?user= (expenses/filtres.py), vue bi.comptes",
    ),
    # Corbeille.
    "corbeille_pays_date": (
        lambda: ElementSupprime.objects.filter(country_id=1).order_by("-supprime_le")[:25],
        "/api/corbeille/?country= (expenses/views.py)",
    ),
    "corbeille_objet": (
        lambda: ElementSupprime.objects.filter(nature="dossier", objet_id=1).order_by(),
        "copies d'un objet retiré (expenses/historique.py, expenses/corbeille.py)",
    ),
    # Notifications.
    "notificatio_recipie_564b1f_idx": (
        lambda: Notification.objects.filter(recipient_id=1, read_at__isnull=True).order_by(),
        "compteur des non lues (notifications/views.py)",
    ),
    "notification_liste": (
        lambda: Notification.objects.filter(recipient_id=1).order_by("-created_at")[:25],
        "liste d'une personne (notifications/views.py), décision 123",
    ),
    "notification_dedup_key_idx": (
        lambda: Notification.objects.filter(dedup_key="alerte-1"),
        "qui a déjà été averti d'un événement (notifications/services.py)",
    ),
    "notification_email_a_faire_idx": (
        lambda: Notification.objects.filter(email_attempted_at=INSTANT, emailed_at__isnull=True),
        "reprise des e-mails, quand ils sont ouverts (notifications/services.py)",
    ),
}


def index_declares():
    """``{nom: modèle}`` de chaque index déclaré dans ``Meta.indexes``."""
    return {
        index.name: modele.__name__
        for modele in apps.get_models()
        if modele._meta.app_label in APPLICATIONS
        for index in modele._meta.indexes
    }


class _Annuler(Exception):
    """Sort de la transaction du plan : rien de ce qui a été retiré ne reste."""


def plan_avec_le_seul_index(nom, requete):
    """Le plan de ``requete`` quand ``nom`` est le seul index de sa table.

    Sur une base de test, quelques lignes : tous les index se valent et le
    planificateur en choisit un au hasard. On ne lui laisse donc que celui
    qu'on éprouve (et la clé primaire), le temps d'un ``EXPLAIN``, dans une
    transaction annulée ; parcours séquentiel coupé, il ne prend l'index que
    si celui-ci *peut* servir — mêmes colonnes en tête, même sens de tri,
    même condition partielle. Que le planificateur le **préfère** à volume
    réel se mesure, et la mesure est consignée (décisions 72 et 123).
    """
    sql, params = requete().query.sql_with_params()
    plan = None
    try:
        with transaction.atomic(), connection.cursor() as curseur:
            curseur.execute(
                """
                SELECT i.relname, c.conname, t.relname
                FROM pg_index x
                JOIN pg_class i ON i.oid = x.indexrelid
                JOIN pg_class t ON t.oid = x.indrelid
                LEFT JOIN pg_constraint c ON c.conindid = x.indexrelid
                WHERE t.relname = (SELECT tt.relname FROM pg_index xx
                                   JOIN pg_class ii ON ii.oid = xx.indexrelid
                                   JOIN pg_class tt ON tt.oid = xx.indrelid
                                   WHERE ii.relname = %s)
                  AND NOT x.indisprimary AND i.relname <> %s
                """,
                [nom, nom],
            )
            for index, contrainte, table in curseur.fetchall():
                if contrainte:
                    curseur.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT "{contrainte}" CASCADE')
                else:
                    curseur.execute(f'DROP INDEX IF EXISTS "{index}" CASCADE')
            curseur.execute("SET LOCAL enable_seqscan = off")
            curseur.execute("EXPLAIN (FORMAT JSON) " + sql, params)
            plan = curseur.fetchone()[0]
            plan = (json.loads(plan) if isinstance(plan, str) else plan)[0]["Plan"]
            raise _Annuler
    except _Annuler:
        pass
    return plan


def _noeuds(plan):
    yield plan
    for enfant in plan.get("Plans", []):
        yield from _noeuds(enfant)


def emprunte(plan, nom):
    """L'index ``nom`` sert-il vraiment ? Parcours séquentiel coupé,
    Postgres lit au besoin un index **en entier** et filtre chaque ligne :
    cela ne compte pas. L'index sert s'il borne la lecture (``Index Cond``)
    ou s'il donne l'ordre demandé sans tri."""
    a_trie = trie(plan)
    return any(
        n.get("Index Name") == nom and ("Index Cond" in n or not a_trie)
        and not ("Filter" in n and "Index Cond" not in n)
        for n in _noeuds(plan)
    )


def trie(plan):
    return any(n["Node Type"] in ("Sort", "Incremental Sort") for n in _noeuds(plan))


class CarteDesIndexTests(TestCase):
    def test_tout_index_declare_figure_sur_la_carte(self):
        sans_requete = sorted(set(index_declares()) - set(CARTE))
        self.assertEqual(
            sans_requete, [],
            "Index sans requête nommée sur la carte (config/tests/test_index.py) : "
            "un index se paie à chaque écriture — nommez la requête qu'il sert, "
            "ou retirez-le.",
        )

    def test_la_carte_ne_nomme_que_des_index_declares(self):
        self.assertEqual(sorted(set(CARTE) - set(index_declares())), [])

    def test_chaque_requete_peut_emprunter_son_index(self):
        for nom, (requete, site) in CARTE.items():
            with self.subTest(index=nom, site=site):
                self.assertTrue(
                    emprunte(plan_avec_le_seul_index(nom, requete), nom),
                    f"{site} ne peut plus emprunter {nom} : la requête et "
                    "l'index ne correspondent plus",
                )

    def test_les_index_de_liste_evitent_le_tri(self):
        """Ils servent à donner une page dans l'ordre sans tout relire."""
        for nom in ("depense_tri_liste", "notification_liste"):
            with self.subTest(index=nom):
                plan = plan_avec_le_seul_index(nom, CARTE[nom][0])
                self.assertTrue(emprunte(plan, nom))
                self.assertFalse(trie(plan), f"{nom} ne couvre plus l'ordre demandé")

    def test_l_annulation_ne_laisse_rien(self):
        """Les index retirés le temps d'un plan sont tous revenus."""
        avant = index_declares()
        plan_avec_le_seul_index("depense_tri_liste", CARTE["depense_tri_liste"][0])
        with connection.cursor() as curseur:
            curseur.execute(
                "SELECT count(*) FROM pg_indexes WHERE indexname = ANY(%s)", [list(avant)]
            )
            self.assertEqual(curseur.fetchone()[0], len(avant))


def _filtres_en_date(chemin):
    """Les ``__date`` d'un module : mots-clés de filtre et ``lookup_expr``."""
    arbre = ast.parse(chemin.read_text(), filename=str(chemin))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.keyword) and noeud.arg:
            # ``created_at__date…``, ``supprime_le__date…`` : la transformation
            # ``date`` appliquée à un horodatage. Un champ qui s'appelle
            # ``date`` (``date__range``) n'est pas visé.
            parties = noeud.arg.split("__")
            if any(
                partie == "date" and parties[i - 1].endswith(("_at", "_le"))
                for i, partie in enumerate(parties) if i
            ):
                yield noeud.lineno, noeud.arg
            if noeud.arg == "lookup_expr" and isinstance(noeud.value, ast.Constant) \
                    and str(noeud.value.value).startswith("date"):
                yield noeud.lineno, f"lookup_expr={noeud.value.value!r}"


class FiltresDePeriodeTests(SimpleTestCase):
    def test_aucun_filtre_de_periode_en_date(self):
        fautes = []
        for app in APPLICATIONS:
            for chemin in sorted((RACINE / app).rglob("*.py")):
                parties = chemin.relative_to(RACINE).parts
                if "tests" in parties or "migrations" in parties:
                    continue
                for ligne, motif in _filtres_en_date(chemin):
                    fautes.append(f"{chemin.relative_to(RACINE)}:{ligne}: {motif}")
        self.assertEqual(
            fautes, [],
            "Un filtre de période en __date ne peut pas emprunter d'index : "
            "écrivez des bornes avec core.periodes (décision 123).\n" + "\n".join(fautes),
        )
