"""Le N°ORDRE est unique par pays, pas globalement.

Le classeur du client numérote ses dossiers de 1 à n dans chaque pays : le
« 12 » du Togo et le « 12 » de la Côte d'Ivoire sont deux dossiers. Une
unicité globale refusait le second — et son message trahissait l'existence
du premier à qui n'avait pas à le connaître.
"""

from datetime import date

from django.db import IntegrityError, transaction
from rest_framework import status

from expenses.models import Dossier

from .base import ExpenseTestCase


class NumeroParPaysTests(ExpenseTestCase):
    def _dossier(self, **extra):
        data = {
            "number": "N-0001", "label": "Salon", "country": self.togo.pk,
            "date": f"{self.year}-04-01",
        }
        data.update(extra)
        return self.client.post("/api/dossiers/", data)

    def test_deux_pays_peuvent_porter_le_meme_numero(self):
        voisin = Dossier.objects.create(
            number="N-0001", label="Mission Abidjan", country=self.ivoire,
            date=date(self.year, 3, 15),
        )

        self.assertNotEqual(voisin.pk, self.dossier.pk)
        self.assertEqual(Dossier.objects.filter(number="N-0001").count(), 2)

    def test_la_base_refuse_un_doublon_dans_le_meme_pays(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Dossier.objects.create(
                number="N-0001", label="Doublon", country=self.togo,
                date=date(self.year, 3, 16),
            )

    def test_l_api_refuse_un_doublon_dans_le_pays_avec_un_message_clair(self):
        self.login(self.owner)

        response = self._dossier()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("existe déjà pour ce pays", str(response.data))
        self.assertEqual(Dossier.objects.filter(country=self.togo).count(), 1)

    def test_l_api_accepte_le_numero_deja_pris_par_un_autre_pays(self):
        """Le responsable ivoirien ne voit pas le N-0001 togolais : il doit
        pouvoir ouvrir le sien, sans qu'aucun message n'évoque le voisin."""
        self.login(self.rep_ivoire)

        response = self._dossier(country=self.ivoire.pk)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Dossier.objects.filter(number="N-0001").count(), 2)

    def test_renommer_un_brouillon_vers_un_numero_pris_est_refuse(self):
        autre = Dossier.objects.create(
            number="N-0002", label="Autre", country=self.togo,
            date=date(self.year, 3, 16), created_by=self.owner.username,
        )
        self.login(self.owner)

        response = self.client.patch(f"/api/dossiers/{autre.pk}/", {"number": "N-0001"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("existe déjà pour ce pays", str(response.data))
        autre.refresh_from_db()
        self.assertEqual(autre.number, "N-0002")

    def test_renommer_un_brouillon_vers_son_propre_numero_passe(self):
        """La validation d'unicité ne doit pas compter le dossier modifié."""
        self.login(self.owner)

        response = self.client.patch(
            f"/api/dossiers/{self.dossier.pk}/",
            {"number": "N-0001", "label": "Mission Lomé — corrigée"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
