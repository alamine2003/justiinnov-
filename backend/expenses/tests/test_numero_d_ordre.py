"""Le N°ORDRE est unique par pays, pas globalement.

Le classeur du client numérote ses dossiers de 1 à n dans chaque pays : le
« 12 » du Togo et le « 12 » de la Côte d'Ivoire sont deux dossiers. Une
unicité globale refusait le second — et son message trahissait l'existence
du premier à qui n'avait pas à le connaître.

Depuis la 2.0 (décisions 102 et 106), le numéro d'un nouveau dossier est
calculé — ``TG-P-2026-001-D001`` — à la création de son projet, et ne se
modifie pas.
"""

from datetime import date

from django.db import IntegrityError, transaction
from rest_framework import status

from expenses.models import Dossier

from .base import ExpenseTestCase


class NumeroParPaysTests(ExpenseTestCase):
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

    def test_les_dossiers_predefinis_portent_le_numero_calcule(self):
        """Le N-0001 existe déjà au Togo : peu importe, le numéro d'un
        nouveau dossier est celui que le serveur calcule (décision 106)."""
        self.login(self.owner)

        response = self.client.post(
            "/api/projects/",
            {"country": self.togo.pk, "name": "Congrès de Kara", "kind": "congres"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        numeros = list(
            Dossier.objects.filter(project_id=response.data["id"]).values_list("number", flat=True)
        )
        self.assertTrue(numeros)
        self.assertTrue(all(n.startswith(response.data["reference"] + "-D") for n in numeros))

    def test_le_numero_d_un_brouillon_ne_se_modifie_pas(self):
        autre = Dossier.objects.create(
            number="N-0002", label="Autre", country=self.togo, project=self.projet,
            date=date(self.year, 3, 16), created_by=self.owner.username,
        )
        self.login(self.owner)

        response = self.client.patch(f"/api/dossiers/{autre.pk}/", {"number": "N-0001"})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
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
