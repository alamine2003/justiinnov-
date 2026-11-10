"""La règle de conversion d'un décaissement (§5.3), hors de toute requête.

La saisie (``ExpenseSerializer``) et l'import d'un classeur
(``reporting.imports``) la partagent : ``test_devise`` et ``test_import``
l'éprouvent par leurs portes, avec leurs messages ; ici, la règle seule.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from budget.models import ExchangeRate
from expenses.devises import (
    Decaissement,
    TauxInconnu,
    convertir_le_decaissement,
    decaissement_incomplet,
)
from expenses.workflow import Status, accepte_des_lignes, hors_de_l_equipe_du_dossier


class ConvertirLeDecaissementTests(TestCase):
    """Le Togo compte en francs CFA ; une mission peut payer en euros."""

    @classmethod
    def setUpTestData(cls):
        # 1 EUR = 655,957 XOF depuis le 1er janvier 2026.
        ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("655.957000"), valid_from=date(2026, 1, 1)
        )

    def test_dans_la_devise_du_pays_le_montant_est_repris_sans_origine(self):
        """La conversion serait l'identité : rien d'étranger n'est conservé."""
        resultat = convertir_le_decaissement(
            " xof ", Decimal("15000.00"), "XOF", date(2026, 3, 15)
        )

        self.assertEqual(resultat, Decaissement(amount=Decimal("15000.00")))
        self.assertEqual(resultat.original_currency, "")
        self.assertIsNone(resultat.original_amount)
        self.assertIsNone(resultat.original_rate)

    def test_une_autre_devise_est_convertie_au_taux_du_jour_et_le_fige(self):
        resultat = convertir_le_decaissement(
            "eur", Decimal("100.00"), "XOF", date(2026, 3, 15)
        )

        self.assertEqual(
            resultat,
            Decaissement(
                amount=Decimal("65595.70"),
                original_currency="EUR",
                original_amount=Decimal("100.00"),
                original_rate=Decimal("655.957000"),
            ),
        )

    def test_une_devise_sans_taux_a_cette_date_leve_taux_inconnu(self):
        """Avant le premier taux publié, rien ne convertit — jamais zéro."""
        with self.assertRaises(TauxInconnu) as refus:
            convertir_le_decaissement("EUR", Decimal("100.00"), "XOF", date(2025, 12, 31))

        self.assertEqual(
            (refus.exception.devise, refus.exception.cible, refus.exception.jour),
            ("EUR", "XOF", date(2025, 12, 31)),
        )

    def test_une_devise_jamais_publiee_leve_taux_inconnu(self):
        with self.assertRaises(TauxInconnu):
            convertir_le_decaissement("USD", Decimal("100.00"), "XOF", date(2026, 3, 15))


class DecaissementIncompletTests(SimpleTestCase):
    """« Les deux ou aucun » : une devise sans montant, ou l'inverse."""

    def test_les_deux_ou_aucun(self):
        self.assertFalse(decaissement_incomplet("", None))
        self.assertFalse(decaissement_incomplet(None, None))
        self.assertFalse(decaissement_incomplet("EUR", Decimal("10")))
        self.assertTrue(decaissement_incomplet("EUR", None))
        self.assertTrue(decaissement_incomplet("", Decimal("10")))
        self.assertTrue(decaissement_incomplet(None, Decimal("0")))


class PredicatsDeSaisieTests(SimpleTestCase):
    """Les prédicats que la saisie et l'import partagent."""

    def test_seul_un_brouillon_accepte_des_lignes(self):
        for statut in Status:
            with self.subTest(statut=statut):
                self.assertEqual(
                    accepte_des_lignes(SimpleNamespace(status=statut)),
                    statut == Status.DRAFT,
                )

    def test_une_ligne_porte_l_equipe_de_son_dossier(self):
        avec_equipe = SimpleNamespace(team_id=7)
        sans_equipe = SimpleNamespace(team_id=None)

        self.assertFalse(hors_de_l_equipe_du_dossier(avec_equipe, 7))
        self.assertTrue(hors_de_l_equipe_du_dossier(avec_equipe, 8))
        # Une équipe que l'import n'a pas encore créée est une autre équipe.
        self.assertTrue(hors_de_l_equipe_du_dossier(avec_equipe, None))
        self.assertFalse(hors_de_l_equipe_du_dossier(sans_equipe, 8))
        self.assertFalse(hors_de_l_equipe_du_dossier(sans_equipe, None))
