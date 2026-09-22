"""La trace ``updated`` d'un brouillon dit tout ce qui a changé.

Une trace qui ne portait que le montant laissait passer, sans avant ni
après, un changement de date, de bénéficiaire, de dossier ou de libellé.
Chaque champ éditable est photographié avant et après l'écriture, et seule
la différence est journalisée (``core.journal.difference``).
"""

from unittest import mock

from rest_framework import status

from expenses import transitions
from expenses.models import AuditLog, Beneficiary, Dossier
from expenses.serializers import DossierSerializer

from .base import ExpenseTestCase


class TraceDeModificationTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)

    def _trace(self):
        return AuditLog.objects.get(action=AuditLog.Action.UPDATED)

    def test_la_ligne_journalise_chaque_champ_modifie(self):
        ligne = self.make_expense(title="Carburant", place="Lomé")
        beneficiaire = Beneficiary.objects.create(country=self.togo, name="Station Total")

        response = self.client.patch(
            f"/api/expenses/{ligne.pk}/",
            {"title": "Péage", "beneficiary": beneficiaire.pk, "place": "Lomé"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        trace = self._trace()
        self.assertEqual(trace.detail["before"], {"title": "Carburant", "beneficiary": None})
        self.assertEqual(trace.detail["after"], {"title": "Péage", "beneficiary": beneficiaire.pk})
        self.assertEqual(sorted(trace.detail["changed_fields"]), ["beneficiary", "title"])

    def test_le_montant_reste_trace(self):
        ligne = self.make_expense(amount="100000.00")

        self.client.patch(f"/api/expenses/{ligne.pk}/", {"amount": "120000.00"}, format="json")

        trace = self._trace()
        self.assertEqual(trace.detail["before"]["amount"], "100000.00")
        self.assertEqual(trace.detail["after"]["amount"], "120000.00")

    def test_le_dossier_journalise_avant_et_apres(self):
        response = self.client.patch(
            f"/api/dossiers/{self.dossier.pk}/",
            {"label": "Mission Kara", "date": f"{self.year}-04-01"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        trace = self._trace()
        self.assertEqual(
            trace.detail["before"], {"label": "Mission Lomé", "date": f"{self.year}-03-15"}
        )
        self.assertEqual(
            trace.detail["after"], {"label": "Mission Kara", "date": f"{self.year}-04-01"}
        )

    def test_remettre_les_memes_valeurs_ne_trace_rien(self):
        response = self.client.patch(
            f"/api/dossiers/{self.dossier.pk}/", {"label": "Mission Lomé"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.UPDATED).exists())


class DeplacementSousVerrouTests(ExpenseTestCase):
    """Le déplacement d'un dossier est rejugé une fois le dossier verrouillé.

    Validé sur une lecture sans verrou, il pouvait laisser derrière lui une
    ligne ajoutée entre la validation et l'écriture. À défaut d'une course à
    deux connexions, l'ordre des appels est vérifié : le verrou d'abord, la
    vérification ensuite.
    """

    def test_la_verification_rejoue_apres_le_verrou(self):
        self.login(self.owner)
        temoin = mock.Mock()
        verrouiller = mock.patch.object(
            transitions, "verrouiller", wraps=transitions.verrouiller
        )
        verifier = mock.patch.object(
            DossierSerializer, "_verifier_le_deplacement",
            autospec=True, side_effect=DossierSerializer._verifier_le_deplacement,
        )
        with verrouiller as verrou, verifier as verification:
            temoin.attach_mock(verrou, "verrouiller")
            temoin.attach_mock(verification, "verifier")
            response = self.client.patch(
                f"/api/dossiers/{self.dossier.pk}/", {"team": None}, format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        noms = [appel[0] for appel in temoin.mock_calls]
        self.assertIn("verrouiller", noms)
        # La validation appelle la vérification une première fois, sans
        # verrou ; elle doit être rejouée après le verrou.
        self.assertEqual(noms[-1], "verifier")
        self.assertLess(noms.index("verrouiller"), len(noms) - 1)
        self.assertEqual(noms.count("verifier"), 2)
