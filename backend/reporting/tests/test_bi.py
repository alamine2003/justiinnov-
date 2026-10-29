"""Le BI de pilotage (décision 122) : mêmes chiffres, et rien de plus.

Les vues du schéma ``bi`` ne recalculent pas autrement que le serveur : sur
un même décor — plusieurs devises, une devise sans taux, des sous-enveloppes,
un dépassement, chaque statut, des pièces manquantes ou incomplètes, une
dépense hors norme, un arrondi « au pair » —, chacune rend les chiffres de
``budget.aggregates``, du tableau de bord et des alertes.

Et le rôle du BI ne lit que ces vues : ni les comptes, ni les jetons, ni les
secrets, ni l'écriture. Ses droits sont ceux de ``deploy/creer_role_bi.sql``,
rejoué ici tel quel.
"""

import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from accounts.models import Role
from budget.aggregates import (
    budget_figures,
    consolidation_par_pays,
    current_rates,
    date_de_reference,
)
from budget.models import Budget, ExchangeRate
from core import types_de_projets
from core.models import Country, Project, WorkflowConfiguration
from core.numerotation import creer_projet
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.utils import timezone
from expenses.models import AuditLog, Dossier, Expense, Proof
from expenses.tests.base import ExpenseTestCase
from expenses.workflow import Status

from reporting.alerts import budget_alerts, proof_alerts, unusual_expense_alerts
from reporting.bi import GABARIT, jetons, sql_des_vues
from reporting.scope import bornes_periode

SCRIPT_DU_ROLE = Path(settings.BASE_DIR).parent / "deploy" / "creer_role_bi.sql"


def lignes(sql, params=()):
    with connection.cursor() as curseur:
        curseur.execute(sql, params)
        colonnes = [c.name for c in curseur.description]
        return [dict(zip(colonnes, ligne)) for ligne in curseur.fetchall()]


class DecorBI(ExpenseTestCase):
    """Le décor du socle, plus ce qui met chaque règle à l'épreuve."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Un pays en francs congolais, au taux 0,25 : 0,10 CDF valent
        # 0,025 FCFA, une moitié exacte que Decimal arrondit au pair (0,02)
        # et round() de PostgreSQL vers le haut (0,03).
        cls.rdc = Country.objects.create(
            name="RDC", code="CD", currency="CDF", timezone="Africa/Kinshasa",
        )
        ExchangeRate.objects.create(
            currency="CDF", rate_to_xof=Decimal("0.250000"),
            valid_from=date(cls.year, 1, 1),
        )
        # Un taux daté de demain ne s'applique pas encore.
        ExchangeRate.objects.create(
            currency="CDF", rate_to_xof=Decimal("9.000000"),
            valid_from=timezone.localdate() + timedelta(days=1),
        )
        cls.budget_rdc = Budget.objects.create(
            country=cls.rdc, year=cls.year, amount=Decimal("0.10"),
        )
        # Un pays en dollars sans taux : exclu du consolidé, et nommé.
        cls.gabon = Country.objects.create(
            name="Gabon", code="GA", currency="USD", timezone="Africa/Libreville",
        )
        Budget.objects.create(country=cls.gabon, year=cls.year, amount=Decimal("5000.00"))
        # Une sous-enveloppe de projet au Togo, et une enveloppe désactivée
        # qui ne compte plus nulle part.
        cls.budget_projet = Budget.objects.create(
            country=cls.togo, year=cls.year, project=cls.projet, amount=Decimal("300000.00"),
        )
        Budget.objects.create(
            country=cls.togo, year=cls.year, team=cls.team,
            amount=Decimal("7.00"), is_active=False,
        )

    def setUp(self):
        super().setUp()
        maintenant = timezone.now()
        # Togo : chaque statut, des montants à décimales.
        self.brouillon = self.make_expense("12000.00", status=Status.DRAFT)
        self.soumise = self.make_expense("150000.50", status=Status.SUBMITTED)
        self.en_controle = self.make_expense("80000.25", status=Status.IN_REVIEW)
        self.justifiee = self.make_expense(
            "200000.00", status=Status.JUSTIFIED, justified_amount=Decimal("180000.00"),
        )
        self.non_justifiee = self.make_expense("50000.00", status=Status.UNJUSTIFIED)
        self.cloturee = self.make_expense(
            "90000.00", status=Status.CLOSED, justified_amount=Decimal("90000.00"),
        )
        # Une dépense hors norme, imputée sur la sous-enveloppe du projet.
        self.enorme = self.make_expense(
            "2500000.00", status=Status.JUSTIFIED, justified_amount=Decimal("1.00"),
            budget=self.budget_projet,
        )
        # Côte d'Ivoire : un dépassement.
        self.dossier_ivoire = Dossier.objects.create(
            number="CI-1", label="Abidjan", country=self.ivoire, project=self.projet_ivoire,
            date=date(self.year, 2, 1), status=Status.SUBMITTED,
        )
        for montant in ("300000.00", "300000.00"):
            self.make_expense(
                montant, dossier=self.dossier_ivoire, country=self.ivoire,
                project=self.projet_ivoire, team=None, status=Status.SUBMITTED,
            )
        # RDC : la moitié exacte.
        self.projet_rdc = creer_projet(Project(
            country=self.rdc, name="Congrès de Kinshasa", kind_id=types_de_projets.CONGRES,
        ))
        self.dossier_rdc = Dossier.objects.create(
            number="CD-1", label="Kinshasa", country=self.rdc, project=self.projet_rdc,
            date=date(self.year, 4, 1), status=Status.SUBMITTED,
        )
        self.make_expense(
            "0.10", dossier=self.dossier_rdc, country=self.rdc, project=self.projet_rdc,
            team=None, status=Status.JUSTIFIED, justified_amount=Decimal("0.05"),
            date=maintenant,
        )
        # Pièces : une ligne prouvée, une pièce incomplète sur un autre
        # dossier déclaré, et un dossier déclaré sans aucune pièce.
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.SUBMITTED)
        Proof.objects.create(
            dossier=self.dossier, expense=self.justifiee, original_name="r.pdf",
            sha256="a" * 64, size=10, content_type="application/pdf",
            status=Proof.ProofStatus.VALIDATED,
        )
        Proof.objects.create(
            dossier=self.dossier_rdc, expense=None, original_name="d.pdf",
            sha256="b" * 64, size=10, content_type="application/pdf",
            status=Proof.ProofStatus.INCOMPLETE,
        )
        AuditLog.objects.create(
            user="owner.togo", action=AuditLog.Action.SUBMITTED, object_type="Expense",
            object_id=self.justifiee.pk, country=self.togo,
        )

    def enveloppes_actives(self):
        return Budget.objects.filter(is_active=True, year=self.year).select_related(
            "country"
        ).with_consumption()


class PariteTests(DecorBI):
    def test_chaque_enveloppe_rend_les_chiffres_du_serveur(self):
        taux = current_rates(date_de_reference(self.year))
        vues = {v["id"]: v for v in lignes("SELECT * FROM bi.enveloppes")}

        attendues = list(self.enveloppes_actives())
        self.assertEqual(set(vues), {b.pk for b in attendues})
        for budget in attendues:
            with self.subTest(enveloppe=str(budget)):
                chiffres = budget_figures(budget, rates=taux)
                vue = vues[budget.pk]
                self.assertEqual(vue["engage"], chiffres["engaged"])
                self.assertEqual(vue["consomme"], chiffres["consumed"])
                self.assertEqual(vue["justifie"], chiffres["justified"])
                self.assertEqual(vue["ecart"], chiffres["gap"])
                self.assertEqual(vue["disponible"], chiffres["remaining"])
                self.assertEqual(vue["taux_execution"], chiffres["execution_rate"])
                self.assertEqual(vue["niveau_execution"], chiffres["execution_level"])
                self.assertEqual(vue["taux_justification"], chiffres["justification_rate"])
                self.assertEqual(vue["montant_xof"], chiffres["amount_xof"])
                self.assertEqual(vue["disponible_xof"], chiffres["remaining_xof"])

    def test_la_consolidation_par_pays_et_le_consolide(self):
        lignes_serveur, consolide = consolidation_par_pays(
            self.enveloppes_actives(), rates=current_rates(date_de_reference(self.year))
        )
        vues = {
            v["pays_id"]: v
            for v in lignes("SELECT * FROM bi.consolidation_pays WHERE annee = %s", [self.year])
        }
        correspondance = {
            "allocated": "attribue", "sub_allocated": "sous_enveloppes", "engaged": "engage",
            "consumed": "consomme", "justified": "justifie", "gap": "ecart",
            "unallocated": "non_reparti", "remaining": "disponible",
            "execution_rate": "taux_execution", "execution_level": "niveau_execution",
            "justification_rate": "taux_justification",
        }
        self.assertEqual(set(vues), {ligne["country"] for ligne in lignes_serveur})
        for ligne in lignes_serveur:
            vue = vues[ligne["country"]]
            for cle, colonne in correspondance.items():
                with self.subTest(pays=ligne["country_name"], cle=cle):
                    self.assertEqual(vue[colonne], ligne[cle])
            for cle in ("allocated", "sub_allocated", "engaged", "consumed", "justified",
                        "gap", "remaining"):
                with self.subTest(pays=ligne["country_name"], cle=f"{cle}_xof"):
                    self.assertEqual(vue[f"{correspondance[cle]}_xof"], ligne[f"{cle}_xof"])

        (total,) = lignes("SELECT * FROM bi.consolidation WHERE annee = %s", [self.year])
        for cle in ("allocated", "engaged", "consumed", "justified", "gap", "remaining"):
            with self.subTest(consolide=cle):
                self.assertEqual(total[f"{correspondance[cle]}_xof"], consolide[cle])
        self.assertEqual(total["taux_execution"], consolide["execution_rate"])
        self.assertEqual(total["niveau_execution"], consolide["execution_level"])
        self.assertEqual(total["taux_justification"], consolide["justification_rate"])
        self.assertEqual(total["devises_non_converties"], consolide["unconverted_currencies"])
        self.assertEqual(consolide["unconverted_currencies"], ["USD"])

    def test_l_arrondi_au_pair_comme_decimal(self):
        (vue,) = lignes("SELECT * FROM bi.enveloppes WHERE id = %s", [self.budget_rdc.pk])
        # 0,10 × 0,25 = 0,025 : au pair, 0,02.
        self.assertEqual(vue["montant_xof"], Decimal("0.02"))
        (ligne,) = lignes("SELECT * FROM bi.lignes WHERE pays_id = %s", [self.rdc.pk])
        self.assertEqual(ligne["montant_xof"], Decimal("0.02"))
        self.assertEqual(ligne["taux_xof"], Decimal("0.25"))

    def test_le_plan_de_charge_du_pilotage(self):
        self.login(self.doo)
        for pays in (self.togo, self.ivoire, self.rdc):
            with self.subTest(pays=pays.name):
                charge = self.client.get(
                    "/api/dashboard/", {"year": self.year, "country": pays.pk}
                ).data["workload"]
                (vue,) = lignes(
                    """SELECT count(*) FILTER (WHERE engagee) AS a_controler,
                              count(*) FILTER (WHERE brouillon) AS brouillons,
                              count(*) FILTER (WHERE statut = 'unjustified') AS non_justifiees
                         FROM bi.lignes WHERE pays_id = %s AND annee = %s""",
                    [pays.pk, self.year],
                )
                (dossiers,) = lignes(
                    "SELECT count(*) AS ouverts FROM bi.dossiers "
                    "WHERE pays_id = %s AND annee = %s AND ouvert",
                    [pays.pk, self.year],
                )
                self.assertEqual(vue["a_controler"], charge["expenses_to_review"])
                self.assertEqual(vue["brouillons"], charge["expenses_draft"])
                self.assertEqual(vue["non_justifiees"], charge["expenses_unjustified"])
                self.assertEqual(dossiers["ouverts"], charge["dossiers_open"])

    def test_la_repartition_mensuelle_du_pilotage(self):
        self.login(self.doo)
        serveur = self.client.get(
            "/api/dashboard/breakdown/", {"year": self.year, "country": self.togo.pk}
        ).data["by_month"]
        vue = lignes(
            """SELECT to_char(mois, 'YYYY-MM') AS mois, sum(montant) AS montant,
                      sum(justifie) AS justifie, count(*) AS lignes
                 FROM bi.lignes
                WHERE pays_id = %s AND annee = %s AND (engagee OR consommee)
                GROUP BY mois ORDER BY mois""",
            [self.togo.pk, self.year],
        )
        self.assertEqual(
            [(r["label"], Decimal(r["amount"]), Decimal(r["justified"]), r["lines"]) for r in serveur],
            [(r["mois"], r["montant"], r["justifie"], r["lignes"]) for r in vue],
        )

    def test_les_alertes_d_enveloppe(self):
        serveur = {
            alerte["key"] for alerte in budget_alerts(self.enveloppes_actives())
        }
        vue = set()
        for v in lignes("SELECT * FROM bi.enveloppes WHERE annee = %s", [self.year]):
            if v["alerte"] == "budget_overrun":
                vue.add(f"budget_overrun:{v['id']}")
            elif v["alerte"] == "budget_threshold":
                vue.add(f"budget_threshold:{v['id']}:{int(v['seuil_atteint'])}")
        self.assertTrue(serveur)
        self.assertEqual(vue, serveur)

    def test_les_alertes_de_justificatif(self):
        serveur = {alerte["key"] for alerte in proof_alerts(Dossier.objects.all())}
        vue = {
            f"{v['alerte']}:{v['id']}"
            for v in lignes("SELECT id, alerte FROM bi.dossiers WHERE alerte IS NOT NULL")
        }
        self.assertTrue(serveur)
        self.assertEqual(vue, serveur)

    def test_le_delai_de_grace_des_justificatifs(self):
        WorkflowConfiguration.objects.update_or_create(
            pk=1, defaults={"unjustified_alert_days": 400}
        )
        from django.core.cache import cache

        cache.clear()
        serveur = {alerte["key"] for alerte in proof_alerts(Dossier.objects.all())}
        vue = {
            f"{v['alerte']}:{v['id']}"
            for v in lignes("SELECT id, alerte FROM bi.dossiers WHERE alerte IS NOT NULL")
        }
        self.assertEqual(vue, serveur)

    def test_les_depenses_inhabituelles(self):
        _jours, instants = bornes_periode(self.year, tz=ZoneInfo(self.togo.timezone))
        serveur = {
            alerte["key"]
            for alerte in unusual_expense_alerts(
                Expense.objects.filter(country=self.togo, date__range=instants)
            )
        }
        vue = {
            f"unusual_expense:{v['ligne_id']}"
            for v in lignes(
                "SELECT ligne_id FROM bi.inhabituelles WHERE pays_id = %s AND annee = %s",
                [self.togo.pk, self.year],
            )
        }
        self.assertEqual(serveur, {f"unusual_expense:{self.enorme.pk}"})
        self.assertEqual(vue, serveur)

    def test_une_ligne_dit_sa_preuve_et_ses_etapes(self):
        vues = {v["id"]: v for v in lignes("SELECT * FROM bi.lignes")}
        self.assertTrue(vues[self.justifiee.pk]["a_preuve"])
        self.assertFalse(vues[self.soumise.pk]["a_preuve"])
        self.assertEqual(vues[self.en_controle.pk]["libelle_statut"], "En contrôle")
        (delai,) = lignes("SELECT * FROM bi.delais WHERE ligne_id = %s", [self.justifiee.pk])
        self.assertIsNotNone(delai["soumise_le"])
        self.assertNotIn(self.brouillon.pk, {d["ligne_id"] for d in lignes("SELECT ligne_id FROM bi.delais")})


class GabaritTests(TestCase):
    def test_chaque_jeton_a_sa_valeur(self):
        sql = sql_des_vues()
        self.assertNotIn("@@", sql)
        for jeton in re.findall(r"@@([A-Z_]+)@@", GABARIT.read_text(encoding="utf-8")):
            with self.subTest(jeton=jeton):
                self.assertIn(jeton, jetons())

    def test_les_libelles_viennent_des_modeles(self):
        (ligne,) = lignes(
            "SELECT bi.libelle_statut('closed') AS statut, "
            "bi.libelle_paiement('cash') AS paiement, bi.libelle_role('super_admin') AS role"
        )
        self.assertEqual(ligne["statut"], "Clôturé")
        self.assertEqual(ligne["paiement"], "Espèces")
        self.assertEqual(ligne["role"], str(Role.SUPER_ADMIN.label))


#: Ce qu'aucune vue du BI ne doit jamais montrer.
COLONNES_INTERDITES = re.compile(
    r"password|mot_de_passe$|^key$|token|jeton|totp|secret|phone|telephone|email|"
    r"^ip|ip_address|user_agent|session",
)


class SousLeRoleDuBI(DecorBI):
    """Le décor, plus le rôle de ``deploy/creer_role_bi.sql`` et de quoi
    exécuter une requête sous ses droits."""

    ROLE = "justi_bi_test"

    def setUp(self):
        super().setUp()
        texte = SCRIPT_DU_ROLE.read_text(encoding="utf-8")
        droits = texte.split("-- debut des droits")[1].split("-- fin des droits")[0]
        droits = droits.split("\n", 1)[1]
        droits = droits.replace(':"role_bi"', f'"{self.ROLE}"')
        with connection.cursor() as curseur:
            # Dans la transaction du test : le rôle disparaît avec elle.
            curseur.execute(f'CREATE ROLE "{self.ROLE}" NOLOGIN')
            curseur.execute(droits)

    def en_tant_que_bi(self, sql):
        """Exécute ``sql`` sous le rôle du BI ; rend les lignes, ou l'erreur."""
        try:
            with transaction.atomic(), connection.cursor() as curseur:
                curseur.execute(f'SET LOCAL ROLE "{self.ROLE}"')
                curseur.execute("SET LOCAL transaction_read_only = on")
                curseur.execute(sql)
                resultat = curseur.fetchall() if curseur.description else []
                raise _Retour(resultat)
        except _Retour as retour:
            return retour.valeur
        except DatabaseError as erreur:
            return erreur


class RoleDuBITests(SousLeRoleDuBI):
    """Le rôle du BI ne lit que le schéma ``bi``."""

    def test_il_lit_chaque_vue(self):
        vues = [v["viewname"] for v in lignes(
            "SELECT viewname FROM pg_views WHERE schemaname = 'bi' ORDER BY 1"
        )]
        self.assertGreaterEqual(len(vues), 15)
        for vue in vues:
            with self.subTest(vue=vue):
                resultat = self.en_tant_que_bi(f"SELECT count(*) FROM bi.{vue}")
                self.assertNotIsInstance(resultat, Exception, resultat)

    def test_il_ne_lit_aucune_table_de_l_application(self):
        for table in ("auth_user", "authtoken_token", "accounts_userprofile",
                      "expenses_expense", "django_session", "core_workflowconfiguration"):
            with self.subTest(table=table):
                resultat = self.en_tant_que_bi(f"SELECT * FROM public.{table} LIMIT 1")
                self.assertIsInstance(resultat, DatabaseError)
                self.assertIn("permission denied", str(resultat))

    def test_il_n_ecrit_rien(self):
        for sql in (
            "CREATE TABLE bi.essai (a int)",
            "CREATE VIEW bi.essai AS SELECT 1",
            "UPDATE public.expenses_expense SET amount = 0",
        ):
            with self.subTest(sql=sql):
                self.assertIsInstance(self.en_tant_que_bi(sql), DatabaseError)

    def test_aucune_vue_ne_montre_de_secret_ni_de_coordonnee(self):
        colonnes = lignes(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'bi'"
        )
        self.assertTrue(colonnes)
        fautives = [
            f"{c['table_name']}.{c['column_name']}"
            for c in colonnes if COLONNES_INTERDITES.search(c["column_name"])
        ]
        self.assertEqual(fautives, [])


class _Retour(Exception):
    """Sortie d'un bloc atomique en annulant ce qu'il a fait (SET LOCAL)."""

    def __init__(self, valeur):
        self.valeur = valeur


class InstallationTests(TestCase):
    def test_une_vue_cassee_n_empeche_pas_l_application_de_demarrer(self):
        """``migrate`` tourne à chaque démarrage : une vue fautive laisse le
        BI sans données et le dit au journal, mais ne bloque pas le service."""
        from unittest import mock

        from reporting import bi

        with mock.patch.object(bi, "sql_des_vues", return_value="SELECT * FROM table_absente"), \
                self.assertLogs("reporting.bi", level="ERROR"):
            bi.installer_les_vues(connection)
        # La transaction est annulée : les vues d'avant sont toujours là.
        self.assertTrue(lignes("SELECT 1 FROM pg_views WHERE schemaname = 'bi' LIMIT 1"))
        bi.installer_les_vues(connection)
        self.assertTrue(lignes("SELECT 1 FROM pg_views WHERE viewname = 'enveloppes'"))
