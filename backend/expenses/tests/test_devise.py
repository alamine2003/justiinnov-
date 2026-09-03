"""Décaissement dans une autre devise que celle du pays (§5.3)."""

from datetime import date
from decimal import Decimal

from budget.models import ExchangeRate
from rest_framework import status

from expenses.models import Expense

from .base import ExpenseTestCase


class DeviseDuDecaissementTests(ExpenseTestCase):
    """Le Togo compte en francs CFA ; une mission peut payer en euros."""

    def setUp(self):
        super().setUp()
        # 1 EUR = 655,957 XOF depuis le 1er janvier.
        ExchangeRate.objects.create(
            currency="EUR",
            rate_to_xof=Decimal("655.957000"),
            valid_from=date(self.year, 1, 1),
        )
        self.login(self.owner)

    def payload(self, **overrides):
        data = {
            "dossier": self.dossier.pk,
            "country": self.togo.pk,
            "date": f"{self.year}-03-15T10:00:00Z",
            "title": "Hôtel",
            "amount": "10000.00",
        }
        data.update(overrides)
        return data

    def test_une_depense_dans_la_devise_du_pays_reste_inchangee(self):
        response = self.client.post("/api/expenses/", self.payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["amount"], "10000.00")
        self.assertEqual(response.data["original_currency"], "")
        self.assertIsNone(response.data["original_amount"])

    def test_un_decaissement_en_euros_est_converti(self):
        response = self.client.post(
            "/api/expenses/",
            self.payload(original_currency="EUR", original_amount="120.00"),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # 120 × 655,957 = 78 714,84
        self.assertEqual(response.data["amount"], "78714.84")
        self.assertEqual(response.data["original_amount"], "120.00")
        self.assertEqual(response.data["original_currency"], "EUR")

    def test_le_montant_d_origine_est_conserve(self):
        """Le contrôleur doit retrouver sur la pièce le chiffre qu'il lit à
        l'écran : la seule conversion ne se rapproche d'aucun justificatif."""
        self.client.post(
            "/api/expenses/",
            self.payload(original_currency="EUR", original_amount="120.00"),
        )

        depense = Expense.objects.get(title="Hôtel")
        self.assertEqual(depense.original_amount, Decimal("120.00"))
        self.assertEqual(depense.original_currency, "EUR")
        self.assertEqual(depense.original_rate, Decimal("655.957000"))

    def test_le_taux_est_fige_a_la_saisie(self):
        """Un rapport tiré l'an prochain doit donner le même chiffre
        qu'aujourd'hui, même si le taux a changé depuis."""
        self.client.post(
            "/api/expenses/",
            self.payload(original_currency="EUR", original_amount="100.00"),
        )
        avant = Expense.objects.get(title="Hôtel").amount

        ExchangeRate.objects.create(
            currency="EUR",
            rate_to_xof=Decimal("900.000000"),
            valid_from=date(self.year, 6, 1),
        )

        self.assertEqual(Expense.objects.get(title="Hôtel").amount, avant)

    def test_le_taux_est_celui_du_jour_de_la_depense(self):
        ExchangeRate.objects.create(
            currency="EUR",
            rate_to_xof=Decimal("700.000000"),
            valid_from=date(self.year, 6, 1),
        )

        response = self.client.post(
            "/api/expenses/",
            self.payload(
                title="Hôtel septembre",
                date=f"{self.year}-09-15T10:00:00Z",
                original_currency="EUR",
                original_amount="100.00",
            ),
        )

        self.assertEqual(response.data["amount"], "70000.00")

    def test_une_devise_sans_taux_est_refusee(self):
        """Refuser plutôt que convertir à zéro : une dépense qui disparaît
        d'un total est pire qu'une dépense qu'on ne peut pas saisir."""
        response = self.client.post(
            "/api/expenses/",
            self.payload(original_currency="USD", original_amount="100.00"),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Taux de change", str(response.data))
        self.assertFalse(Expense.objects.filter(title="Hôtel").exists())

    def test_la_devise_du_pays_ne_compte_pas_comme_devise_etrangere(self):
        """Saisir « XOF » au Togo ne doit pas laisser croire à un
        décaissement étranger."""
        response = self.client.post(
            "/api/expenses/",
            self.payload(original_currency="xof", original_amount="5000.00"),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["amount"], "5000.00")
        self.assertEqual(response.data["original_currency"], "")

    def test_devise_sans_montant_refusee(self):
        response = self.client.post(
            "/api/expenses/", self.payload(original_currency="EUR")
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_la_conversion_pese_sur_l_enveloppe(self):
        """C'est le montant converti, non celui de la pièce, qui consomme
        l'enveloppe du pays."""
        self.client.post(
            "/api/expenses/",
            self.payload(original_currency="EUR", original_amount="100.00"),
        )
        # Le dossier emporte ses lignes : c'est le chemin réel du pays.
        self.client.post(f"/api/dossiers/{self.dossier.pk}/submit/")

        response = self.client.get(f"/api/budgets/{self.budget.pk}/")

        self.assertEqual(response.data["figures"]["engaged"], "65595.70")
