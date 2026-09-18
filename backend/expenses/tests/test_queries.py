"""Le coût des listes et des soumissions ne doit pas croître avec le nombre
de lignes."""

from datetime import date
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from budget.models import Budget
from core.models import Project, WorkflowConfiguration
from expenses.models import Beneficiary, Dossier, Expense

from .base import ExpenseTestCase, in_memory_storage


@in_memory_storage
class QueryCountTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.doo)
        # ``allowed_actions`` lit la politique du circuit, une fois par
        # requête, via le cache — vidé avant chaque test : la première
        # lecture la crée et la met en cache, ce qui coûte quelques requêtes
        # de plus — un amorçage, pas un N+1. Les mesures comparent des
        # requêtes en régime établi.
        WorkflowConfiguration.charger()

    def _make_dossiers(self, count, offset=0):
        for index in range(offset, offset + count):
            dossier = Dossier.objects.create(
                number=f"Q-{index:03d}",
                label=f"Dossier {index}",
                country=self.togo,
                date=date(self.year, 2, 1),
            )
            for line in range(2):
                Expense.objects.create(
                    dossier=dossier,
                    country=self.togo,
                    date=f"{self.year}-02-01T10:00:00Z",
                    title=f"Ligne {line}",
                    amount=Decimal("1000.00"),
                )

    def _count_queries(self, url):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(captured.captured_queries)

    def test_la_liste_des_dossiers_ne_depend_pas_du_nombre_de_dossiers(self):
        """Sans annotations préparées, chaque dossier coûtait trois requêtes
        supplémentaires (totaux, lignes, preuves)."""
        self._make_dossiers(3)
        few = self._count_queries("/api/dossiers/")

        self._make_dossiers(12, offset=3)
        many = self._count_queries("/api/dossiers/")

        self.assertEqual(few, many)

    def test_la_liste_des_budgets_ne_depend_pas_du_nombre_d_enveloppes(self):
        few = self._count_queries("/api/budgets/")

        for index in range(10):
            projet = Project.objects.create(country=self.togo, name=f"Projet {index}")
            Budget.objects.create(
                country=self.togo,
                year=self.year,
                project=projet,
                amount=Decimal("1000.00"),
            )
        many = self._count_queries("/api/budgets/")

        self.assertEqual(few, many)

    def _ligne_complete(self, index, dossier=None, projet=None):
        """Une ligne portant toutes ses relations : c'est là que le N+1
        se cache."""
        projet = projet or Project.objects.create(
            country=self.togo, name=f"Projet {index}"
        )
        beneficiaire = Beneficiary.objects.create(
            country=self.togo, name=f"Fournisseur {index}"
        )
        return Expense.objects.create(
            dossier=dossier or self.dossier, country=self.togo, team=self.team,
            owner=self.manager, project=projet, beneficiary=beneficiaire,
            date=f"{self.year}-02-01T10:00:00Z",
            title=f"Ligne {index}", amount=Decimal("100.00"),
        )

    def test_le_detail_ne_depend_pas_du_nombre_de_lignes(self):
        for index in range(2):
            self._ligne_complete(index)
        few = self._count_queries(f"/api/dossiers/{self.dossier.pk}/")

        for index in range(2, 12):
            self._ligne_complete(index)
        many = self._count_queries(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(few, many)

    def test_la_liste_et_le_registre_ne_dependent_pas_du_nombre_de_lignes(self):
        for index in range(2):
            self._ligne_complete(index)
        liste_peu = self._count_queries("/api/expenses/")
        registre_peu = self._count_queries("/api/expenses/register/")

        for index in range(2, 12):
            self._ligne_complete(index)
        liste_beaucoup = self._count_queries("/api/expenses/")
        registre_beaucoup = self._count_queries("/api/expenses/register/")

        self.assertEqual(liste_peu, liste_beaucoup)
        self.assertEqual(registre_peu, registre_beaucoup)

    def test_la_soumission_ne_depend_pas_du_nombre_de_lignes(self):
        """Soumettre un dossier résolvait, verrouillait et totalisait
        l'enveloppe pour chaque ligne, puis écrivait ligne et trace une à
        une : vingt lignes, cent requêtes."""
        peu = Dossier.objects.create(
            number="S-001", label="Peu", country=self.togo, date=date(self.year, 2, 1),
        )
        beaucoup = Dossier.objects.create(
            number="S-002", label="Beaucoup", country=self.togo, date=date(self.year, 2, 1),
        )
        # Même projet pour toutes les lignes : une seule clé d'imputation.
        # Des projets distincts se résolvent chacun, c'est le prix du
        # découpage en sous-enveloppes, pas un N+1.
        projet = Project.objects.create(country=self.togo, name="Campagne")
        for index in range(2):
            self._ligne_complete(index, dossier=peu, projet=projet)
        for index in range(2, 14):
            self._ligne_complete(index, dossier=beaucoup, projet=projet)
        self.login(self.owner)
        # Première requête à blanc : elle amorce les caches (configuration
        # du circuit, destinataires) que les mesures ne doivent pas payer.
        chauffe = Dossier.objects.create(
            number="S-000", label="Chauffe", country=self.togo, date=date(self.year, 2, 1),
        )
        self._ligne_complete(99, dossier=chauffe, projet=projet)
        self.assertEqual(self.client.post(f"/api/dossiers/{chauffe.pk}/submit/").status_code, 200)

        with CaptureQueriesContext(connection) as avec_peu:
            response = self.client.post(f"/api/dossiers/{peu.pk}/submit/")
        self.assertEqual(response.status_code, 200)
        with CaptureQueriesContext(connection) as avec_beaucoup:
            response = self.client.post(f"/api/dossiers/{beaucoup.pk}/submit/")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            len(avec_peu.captured_queries), len(avec_beaucoup.captured_queries)
        )
        self.assertEqual(beaucoup.expenses.filter(status="submitted").count(), 12)

    def test_les_totaux_restent_justes_avec_plusieurs_preuves(self):
        """Régression : agréger les montants en joignant aussi les preuves
        les multiplierait par le nombre de preuves du dossier."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from expenses.models import Proof

        Expense.objects.create(
            dossier=self.dossier, country=self.togo,
            date=f"{self.year}-02-01T10:00:00Z", title="Unique",
            amount=Decimal("100.00"), justified_amount=Decimal("60.00"),
        )
        for index in range(3):
            Proof.objects.create(
                dossier=self.dossier,
                file=SimpleUploadedFile(f"p{index}.pdf", b"x"),
                sha256=f"{index:064d}",
            )

        response = self.client.get(f"/api/dossiers/{self.dossier.pk}/")

        self.assertEqual(response.data["totals"]["amount"], "100.00")
        self.assertEqual(response.data["totals"]["gap"], "40.00")
        self.assertEqual(response.data["proof_count"], 3)
        self.assertEqual(response.data["expense_count"], 1)


@in_memory_storage
class RelationsSansJointureTests(ExpenseTestCase):
    """Les relations du sérialiseur se préchargent ; elles ne se joignent pas.

    Trouvé par l'audit de résilience. ``select_related`` sur les douze
    relations de ``EXPENSE_RELATIONS`` produit une requête à **quatorze
    tables**, et Postgres la replanifie à chaque appel : Django ne prépare
    aucune requête (``prepare_threshold`` vaut ``None``), donc rien ne
    s'amortit d'un appel au suivant.

    Mesuré sur 6 009 lignes : **91 ms de planification pour 43 ms
    d'exécution**, à chaque requête — et le même prix pour lire une seule
    ligne. Le coût suit le nombre de relations, pas le nombre de lignes :
    0,6 ms à trois relations, 60 ms à neuf, 91 ms à quatorze. Le
    préchargement (``avec_les_relations``) ramène le SQL d'une page de 140 ms
    à 9 ms, pour un corps de réponse identique.

    Le compte de requêtes est gardé ailleurs, par ``QueryCountTests`` : ces
    deux garde-fous se tiennent l'un l'autre. Sans celui-ci, on revient au
    ``select_related`` et le coût réapparaît sans qu'aucun test ne bouge ;
    sans celui-là, on retire le préchargement et c'est un N+1.
    """

    #: Au-delà, la planification décolle — mesuré. La liste n'a besoin
    #: d'aucune jointure ; cette marge couvre un filtre sur une relation.
    LIMITE = 4

    def setUp(self):
        super().setUp()
        self.login(self.doo)
        WorkflowConfiguration.charger()
        # Sans lignes, le compte de la pagination rend zéro et DRF
        # n'exécute jamais la requête que ce test mesure : elle passerait
        # à vide.
        for index in range(3):
            Expense.objects.create(
                dossier=self.dossier, country=self.togo, team=self.team,
                owner=self.manager, date=f"{self.year}-02-01T10:00:00Z",
                title=f"Ligne {index}", amount=Decimal("100.00"),
            )

    def _jointures_de_la_requete_principale(self, url):
        """Nombre de tables jointes dans la requête qui ramène les lignes."""
        with CaptureQueriesContext(connection) as captured:
            reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200)

        principales = [
            q["sql"] for q in captured.captured_queries
            if 'FROM "expenses_expense"' in q["sql"] and "COUNT(*)" not in q["sql"]
        ]
        self.assertTrue(principales, f"aucune requête de lignes pour {url}")
        return max(sql.count(" JOIN ") for sql in principales)

    def test_la_liste_ne_joint_pas_les_relations_du_serialiseur(self):
        self.assertLessEqual(
            self._jointures_de_la_requete_principale("/api/expenses/"),
            self.LIMITE,
            "la liste rejoint les relations du sérialiseur : Postgres "
            "replanifie une jointure à quatorze tables à chaque appel",
        )

    def test_le_registre_ne_joint_pas_davantage(self):
        self.assertLessEqual(
            self._jointures_de_la_requete_principale("/api/expenses/register/"),
            self.LIMITE,
        )
